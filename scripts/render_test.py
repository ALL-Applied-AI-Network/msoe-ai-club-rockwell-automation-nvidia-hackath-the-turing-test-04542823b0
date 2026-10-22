"""Render test images from the digital twin's vial_fill camera.

Runs on the Brev Isaac launchable with /isaac-sim/python.sh.

Reads:
- Twin stage: /workspace/project/twin/csi_digital_twin_v1/csi_line.usda
- Camera config: /workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json

Writes:
- 10 rendered PNG images saved immediately to /workspace/project/renders/ (frames 1, 50, 150, 250, 301, 360, 450, 600, 660, 686)
- Run timing, GPU name, and image count appended to /workspace/project/repo/outputs/run_log.csv

Execution (on Brev Isaac launchable):
    /isaac-sim/python.sh /workspace/project/repo/scripts/render_test.py
"""

import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback


def get_gpu_name() -> str:
    """Query the GPU model name using nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip().splitlines()[0]
    except Exception:
        return "Unknown GPU"


def main():
    parser = argparse.ArgumentParser(description="Render 10 test frames from twin's vial_fill camera.")
    parser.add_argument(
        "--stage",
        default="/workspace/project/twin/csi_digital_twin_v1/csi_line.usda",
        help="Path to USD stage file",
    )
    parser.add_argument(
        "--camera-config",
        default="/workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json",
        help="Path to camera JSON settings",
    )
    parser.add_argument(
        "--out-dir",
        default="/workspace/project/renders",
        help="Directory to save rendered images",
    )
    parser.add_argument(
        "--log-file",
        default="/workspace/project/repo/outputs/run_log.csv",
        help="Path to run_log.csv",
    )
    parser.add_argument(
        "--subframes",
        type=int,
        default=32,
        help="Path-tracing subframes (samples per pixel)",
    )
    args = parser.parse_args()

    # Record start time and GPU
    start_time = datetime.now()
    gpu_name = get_gpu_name()
    print("=" * 60, flush=True)
    print("Starting Card 6 Twin Render Test", flush=True)
    print(f"GPU: {gpu_name}", flush=True)
    print(f"Start time: {start_time.isoformat(timespec='seconds')}", flush=True)
    print("=" * 60, flush=True)

    # Validate paths
    stage_path = Path(args.stage).resolve()
    cam_config_path = Path(args.camera_config).resolve()
    out_dir = Path(args.out_dir).resolve()
    log_file = Path(args.log_file).resolve()

    if not stage_path.is_file():
        raise FileNotFoundError(f"USD stage not found: {stage_path}")
    if not cam_config_path.is_file():
        raise FileNotFoundError(f"Camera config not found: {cam_config_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 10 frames spanning the 1-686 filling animation sequence
    frames_to_render = [1, 50, 150, 250, 301, 360, 450, 600, 660, 686]
    print(f"Target frames to render ({len(frames_to_render)} total): {frames_to_render}", flush=True)

    with open(cam_config_path, "r", encoding="utf-8") as f:
        cam_meta = json.load(f)

    rw, rh = cam_meta.get("render_px", [640, 480])
    fps = cam_meta.get("fps", 30)

    # Launch headless Isaac Sim SimulationApp
    print(f"Initializing Isaac Sim (resolution {rw}x{rh}, renderer=PathTracing)...", flush=True)
    from isaacsim import SimulationApp

    kit = SimulationApp({"headless": True, "renderer": "PathTracing", "width": rw, "height": rh})

    rendered_count = 0
    try:
        from isaacsim.core.utils.extensions import enable_extension
        enable_extension("omni.replicator.core")

        import cv2
        import numpy as np
        import omni.timeline
        import omni.usd
        import omni.replicator.core as rep
        from pxr import Gf, UsdGeom

        ctx = omni.usd.get_context()
        print(f"Opening stage: {stage_path}...", flush=True)
        if not ctx.open_stage(str(stage_path)):
            raise RuntimeError(f"Could not open USD stage: {stage_path}")

        # Wait for stage and assets to fully load
        while ctx.get_stage_loading_status()[2] > 0:
            kit.update()
        for _ in range(10):
            kit.update()

        stage = ctx.get_stage()

        # Locate the FillCam prim
        candidates = [cam_meta.get("prim_in_csi_line"), cam_meta.get("prim_in_station_file")]
        prim_path = next((p for p in candidates if p and stage.GetPrimAtPath(p).IsValid()), None)
        if prim_path is None:
            raise RuntimeError(f"Camera prim not found in stage. Checked: {candidates}")

        print(f"Found camera prim at: {prim_path}", flush=True)

        tl = omni.timeline.get_timeline_interface()
        time_codes_per_sec = stage.GetTimeCodesPerSecond() or fps

        # Create render product and attach RGB annotator
        rp = rep.create.render_product(prim_path, (rw, rh))
        rgb_annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb_annotator.attach([rp])
        rep.orchestrator.set_capture_on_play(False)
        kit.update()

        # Camera clipping range resync fix to prevent black renders
        cam_prim = stage.GetPrimAtPath(prim_path)
        clip_attr = UsdGeom.Camera(cam_prim).GetClippingRangeAttr()
        near_far = clip_attr.Get()
        if near_far is not None:
            stage.SetEditTarget(stage.GetSessionLayer())
            clip_attr.Set(Gf.Vec2f(near_far[0] * 0.5, near_far[1]))
            kit.update()
            clip_attr.Set(near_far)
            kit.update()

        # Render each frame and save immediately to disk
        for idx, frame_num in enumerate(frames_to_render, start=1):
            target_time = frame_num / time_codes_per_sec
            tl.set_current_time(target_time)
            kit.update()

            # Orchestrator steps to converge path tracing
            for _ in range(2):
                rep.orchestrator.step(rt_subframes=args.subframes, delta_time=0.0)

            data = np.asarray(rgb_annotator.get_data())
            if data.ndim != 3 or data.shape[:2] != (rh, rw) or data.shape[2] < 3:
                raise RuntimeError(
                    f"Unexpected RGB buffer shape {data.shape} for frame {frame_num} (expected {rh}x{rw}x3+)"
                )

            # Convert RGB to BGR for OpenCV
            img_bgr = data[..., :3][..., ::-1].copy()
            out_file = out_dir / f"fill_frame_{frame_num:03d}.png"

            if not cv2.imwrite(str(out_file), img_bgr):
                raise OSError(f"Failed to write image to disk: {out_file}")

            rendered_count += 1
            print(
                f"[{rendered_count}/{len(frames_to_render)}] Saved frame {frame_num:03d} -> {out_file}",
                flush=True,
            )

    except BaseException:
        print("Exception occurred during rendering:", file=sys.stderr, flush=True)
        traceback.print_exc()
        raise
    finally:
        # Calculate elapsed time and log run statistics before Isaac Sim shuts down
        end_time = datetime.now()
        job_minutes = round((end_time - start_time).total_seconds() / 60.0, 2)

        print("=" * 60, flush=True)
        print("Card 6 Twin Render Summary", flush=True)
        print(f"End time: {end_time.isoformat(timespec='seconds')}", flush=True)
        print(f"Job duration: {job_minutes:.2f} minutes", flush=True)
        print(f"Rendered images: {rendered_count} of {len(frames_to_render)}", flush=True)
        print("=" * 60, flush=True)

        try:
            write_header = not log_file.exists() or log_file.stat().st_size == 0
            with open(log_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow(["timestamp", "gpu", "job", "job_minutes", "output_count", "notes"])
                writer.writerow([
                    start_time.isoformat(timespec="seconds"),
                    gpu_name,
                    "Card 6 twin render test",
                    f"{job_minutes:.2f}",
                    rendered_count,
                    f"Rendered {rendered_count} FillCam frames to {out_dir}",
                ])
            print(f"Appended run record to {log_file}", flush=True)
        except Exception as log_err:
            print(f"Warning: Failed to update run_log.csv: {log_err}", file=sys.stderr, flush=True)

        # Close SimulationApp
        kit.close()


if __name__ == "__main__":
    main()

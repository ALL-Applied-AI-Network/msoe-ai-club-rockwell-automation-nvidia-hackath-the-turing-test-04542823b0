"""Match twin liquid dye strengths to the real camera via automatic calibration loop.

One job: calibrates the twin's 6 dye absorption coefficients (k_orange, k_blue per RGB channel)
against the blank-normalized colors of the 10 real clean 3rd vials.
Held-out recipes (Recipe 5 and Recipe 11) are NEVER used to adjust strengths and are
evaluated strictly after calibration converges.

Reads:
- Real vial targets: outputs/card7/vials_30_transmittance.csv
- Initial dye strengths: outputs/card7/twin_dye_strengths.json
- Calibrated fill height: outputs/card7/twin_fill_height.json
- Twin stage: /workspace/project/twin/csi_digital_twin_v1/csi_line.usda

Writes:
- Updated dye strengths: outputs/card7/twin_dye_strengths.json
- Calibration progress table: outputs/card7/calibration.csv

Execution:
    /isaac-sim/python.sh scripts/calibrate_colors.py
"""

import argparse
import csv
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple
import colour
import numpy as np

from scripts.measure_patches import measure_image
from scripts.set_liquid import (
    DEFAULT_DYE_STRENGTHS_JSON,
    load_dye_strengths,
    set_liquid_and_render_frame,
)

# 10 recipe definitions: (recipe_id, 3rd_vial, orange_share, blue_share, total_ml, patch)
RECIPES = {
    5: {"vial": 3, "orange": 0.3333, "blue": 0.3333, "ml": 30.0, "patch": "LOW", "held_out": True},
    6: {"vial": 6, "orange": 0.2500, "blue": 0.0000, "ml": 40.0, "patch": "LOW", "held_out": False},
    7: {"vial": 9, "orange": 0.0000, "blue": 0.7143, "ml": 70.0, "patch": "HIGH", "held_out": False},
    8: {"vial": 12, "orange": 0.3333, "blue": 0.3333, "ml": 60.0, "patch": "HIGH", "held_out": False},
    9: {"vial": 15, "orange": 0.4375, "blue": 0.4375, "ml": 80.0, "patch": "HIGH", "held_out": False},
    10: {"vial": 18, "orange": 0.2000, "blue": 0.2000, "ml": 75.0, "patch": "HIGH", "held_out": False},
    11: {"vial": 21, "orange": 0.1429, "blue": 0.7143, "ml": 70.0, "patch": "HIGH", "held_out": True},
    12: {"vial": 24, "orange": 0.7143, "blue": 0.1429, "ml": 70.0, "patch": "HIGH", "held_out": False},
    13: {"vial": 27, "orange": 0.7143, "blue": 0.2857, "ml": 70.0, "patch": "HIGH", "held_out": False},
    14: {"vial": 30, "orange": 0.0000, "blue": 0.1429, "ml": 70.0, "patch": "HIGH", "held_out": False},
}

CALIBRATION_RECIPES = [r for r, d in RECIPES.items() if not d["held_out"]]  # 8 recipes
HELD_OUT_RECIPES = [r for r, d in RECIPES.items() if d["held_out"]]         # Recipes 5, 11


def load_real_targets(transmittance_csv: Path) -> Dict[int, Dict[str, Any]]:
    """Load real blank-normalized Lab targets from vials_30_transmittance.csv for 3rd vials."""
    med_blank_h_lin = np.array([0.17144110073282259, 0.19120168274079138, 0.17464740365558504])
    med_blank_l_lin = np.array([0.020288563056652397, 0.021219010376003555, 0.015208514422912708])

    targets = {}
    vial_to_rec = {d["vial"]: r for r, d in RECIPES.items()}

    with open(transmittance_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = int(row["vial"])
            if v in vial_to_rec:
                rec = vial_to_rec[v]
                target_patch = RECIPES[rec]["patch"]

                if target_patch == "LOW":
                    t_lin = np.array([float(row["T_low_R"]), float(row["T_low_G"]), float(row["T_low_B"])])
                    norm_lin = t_lin * med_blank_l_lin
                else:
                    t_lin = np.array([float(row["T_high_R"]), float(row["T_high_G"]), float(row["T_high_B"])])
                    norm_lin = t_lin * med_blank_h_lin

                srgb = colour.models.eotf_inverse_sRGB(np.clip(norm_lin, 0.0, 1.0))
                xyz = colour.sRGB_to_XYZ(srgb)
                target_lab = colour.XYZ_to_Lab(xyz)

                # Optical absorbance A = -log10(clamp(T, 1e-5, 1.0))
                A_meas = -np.log10(np.clip(t_lin, 1e-5, 10.0))

                targets[rec] = {
                    "vial": v,
                    "recipe_id": rec,
                    "target_patch": target_patch,
                    "target_lab": target_lab,
                    "target_lin": norm_lin,
                    "target_transmittance": t_lin,
                    "target_absorbance": A_meas,
                }
    return targets


def save_dye_strengths(k_orange: np.ndarray, k_blue: np.ndarray, json_path: Path):
    """Save current 6 dye absorption coefficients to JSON."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "k_orange": {"R": float(k_orange[0]), "G": float(k_orange[1]), "B": float(k_orange[2])},
        "k_blue": {"R": float(k_blue[0]), "G": float(k_blue[1]), "B": float(k_blue[2])},
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Calibrate twin liquid dye strengths against real clean 3rd vials.")
    parser.add_argument("--transmittance-csv", default=Path("/workspace/project/repo/outputs/card7/vials_30_transmittance.csv"), type=Path)
    parser.add_argument("--dye-strengths", default=DEFAULT_DYE_STRENGTHS_JSON, type=Path)
    parser.add_argument("--out-csv", default=Path("/workspace/project/repo/outputs/card7/calibration.csv"), type=Path)
    parser.add_argument("--stage", default="/workspace/project/twin/csi_digital_twin_v1/csi_line.usda")
    parser.add_argument("--camera-config", default="/workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json")
    parser.add_argument("--max-rounds", type=int, default=4, help="Maximum calibration rounds (at most 4)")
    parser.add_argument("--learning-rate", type=float, default=0.7, help="Gradient step damping factor")
    parser.add_argument("--render-dir", default=Path("/workspace/project/renders/card7_calib"), type=Path)
    args = parser.parse_args()

    args.render_dir.mkdir(parents=True, exist_ok=True)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70, flush=True)
    print("CARD 7 STEP 4: TWIN COLOR CALIBRATION LOOP", flush=True)
    print(f"8 Calibration recipes: {CALIBRATION_RECIPES}", flush=True)
    print(f"2 Held-out recipes (never adjusted): {HELD_OUT_RECIPES}", flush=True)
    print(f"Max rounds: {args.max_rounds}, Learning rate: {args.learning_rate}", flush=True)
    print("=" * 70, flush=True)

    targets = load_real_targets(args.transmittance_csv)
    k_orange, k_blue = load_dye_strengths(args.dye_strengths)

    with open(args.camera_config, "r", encoding="utf-8") as f:
        cam_meta = json.load(f)

    rw, rh = cam_meta.get("render_px", [640, 480])
    fps = cam_meta.get("fps", 30)

    print(f"Starting Isaac Sim SimulationApp ({rw}x{rh}, PathTracing)...", flush=True)
    from isaacsim import SimulationApp

    kit = SimulationApp({"headless": True, "renderer": "PathTracing", "width": rw, "height": rh})

    history_rows = []
    best_median_dE = float("inf")
    best_k_orange = k_orange.copy()
    best_k_blue = k_blue.copy()

    try:
        from isaacsim.core.utils.extensions import enable_extension
        enable_extension("omni.replicator.core")

        import omni.timeline
        import omni.usd
        import omni.replicator.core as rep
        from pxr import Gf, UsdGeom

        ctx = omni.usd.get_context()
        if not ctx.open_stage(args.stage):
            raise RuntimeError(f"Could not open USD stage: {args.stage}")

        while ctx.get_stage_loading_status()[2] > 0:
            kit.update()
        for _ in range(5):
            kit.update()

        stage = ctx.get_stage()

        candidates = [cam_meta.get("prim_in_csi_line"), cam_meta.get("prim_in_station_file")]
        prim_path = next((p for p in candidates if p and stage.GetPrimAtPath(p).IsValid()), None)
        if prim_path is None:
            raise RuntimeError("Camera prim not found.")

        tl = omni.timeline.get_timeline_interface()
        time_codes_per_sec = stage.GetTimeCodesPerSecond() or fps

        rp = rep.create.render_product(prim_path, (rw, rh))
        rgb_annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb_annotator.attach([rp])
        rep.orchestrator.set_capture_on_play(False)
        kit.update()

        cam_p = stage.GetPrimAtPath(prim_path)
        clip_attr = UsdGeom.Camera(cam_p).GetClippingRangeAttr()
        near_far = clip_attr.Get()
        if near_far is not None:
            stage.SetEditTarget(stage.GetSessionLayer())
            clip_attr.Set(Gf.Vec2f(near_far[0] * 0.5, near_far[1]))
            kit.update()
            clip_attr.Set(near_far)
            kit.update()

        # Calibration loop across rounds
        for round_idx in range(1, args.max_rounds + 1):
            print(f"\n" + "-" * 50, flush=True)
            print(f"ROUND {round_idx} / {args.max_rounds}", flush=True)
            print(f"Current strengths:", flush=True)
            print(f"  k_orange: R={k_orange[0]:+.4f}, G={k_orange[1]:+.4f}, B={k_orange[2]:+.4f}", flush=True)
            print(f"  k_blue:   R={k_blue[0]:+.4f}, G={k_blue[1]:+.4f}, B={k_blue[2]:+.4f}", flush=True)
            print("-" * 50, flush=True)

            round_dEs = []
            A_rendered_list = []
            A_target_list = []
            X_list = []

            for rec in CALIBRATION_RECIPES:
                meta = RECIPES[rec]
                out_png = args.render_dir / f"r{round_idx}_rec{rec:02d}.png"

                set_liquid_and_render_frame(
                    stage=stage,
                    kit=kit,
                    tl=tl,
                    rep=rep,
                    rgb_annotator=rgb_annotator,
                    time_codes_per_sec=time_codes_per_sec,
                    orange_share=meta["orange"],
                    blue_share=meta["blue"],
                    volume_ml=meta["ml"],
                    mixing=0.0,
                    out_png_path=out_png,
                    k_orange=k_orange,
                    k_blue=k_blue,
                    frame_num=686,
                    subframes=32,
                )

                meas = measure_image(out_png)
                target_patch = meta["patch"]
                twin_norm_lab = np.array(meas["normalized"][target_patch]["Lab"])
                real_target_lab = targets[rec]["target_lab"]

                dE = float(colour.delta_E(twin_norm_lab, real_target_lab, method="CIE 2000"))
                round_dEs.append(dE)

                print(
                    f"  Recipe {rec:2d} ({meta['ml']:2.0f}mL, {target_patch:4s}): "
                    f"twin Lab={np.round(twin_norm_lab, 2)} | real Lab={np.round(real_target_lab, 2)} | "
                    f"dE2000={dE:5.2f}",
                    flush=True,
                )

                history_rows.append({
                    "recipe_id": rec,
                    "round": round_idx,
                    "orange_share": meta["orange"],
                    "blue_share": meta["blue"],
                    "total_ml": meta["ml"],
                    "patch": target_patch,
                    "dE2000": round(dE, 2),
                    "twin_L": round(float(twin_norm_lab[0]), 2),
                    "twin_a": round(float(twin_norm_lab[1]), 2),
                    "twin_b": round(float(twin_norm_lab[2]), 2),
                    "target_L": round(float(real_target_lab[0]), 2),
                    "target_a": round(float(real_target_lab[1]), 2),
                    "target_b": round(float(real_target_lab[2]), 2),
                })

                # Transmittance and absorbance for gradient update
                t_twin = np.array(meas["transmittance"][target_patch])
                A_twin = -np.log10(np.clip(t_twin, 1e-5, 10.0))
                A_rendered_list.append(A_twin)
                A_target_list.append(targets[rec]["target_absorbance"])
                X_list.append([meta["orange"], meta["blue"]])

            med_dE = float(np.median(round_dEs))
            mean_dE = float(np.mean(round_dEs))
            max_dE = float(np.max(round_dEs))
            print(f"\nRound {round_idx} Summary: median dE={med_dE:.2f}, mean dE={mean_dE:.2f}, max dE={max_dE:.2f}", flush=True)

            if med_dE < best_median_dE:
                best_median_dE = med_dE
                best_k_orange = k_orange.copy()
                best_k_blue = k_blue.copy()
                save_dye_strengths(best_k_orange, best_k_blue, args.dye_strengths)
                print(f"-> Saved new best dye strengths to {args.dye_strengths} (median dE={best_median_dE:.2f})", flush=True)
            else:
                print(f"-> Median dE did not improve ({med_dE:.2f} >= {best_median_dE:.2f}). Stopping early!", flush=True)
                k_orange = best_k_orange.copy()
                k_blue = best_k_blue.copy()
                break

            if round_idx < args.max_rounds:
                # Update dye strengths along anchored gradient using Beer-Lambert residual
                X = np.array(X_list)                    # (8, 2)
                A_rend = np.array(A_rendered_list)       # (8, 3)
                A_targ = np.array(A_target_list)         # (8, 3)
                delta_A = A_targ - A_rend                # (8, 3)

                # Solve delta_K = (X^T X)^(-1) X^T delta_A
                delta_K, _, _, _ = np.linalg.lstsq(X, delta_A, rcond=None)  # (2, 3)

                # Damped step
                step = args.learning_rate * delta_K
                k_orange = k_orange + step[0]
                k_blue = k_blue + step[1]

        # Final evaluation of the 2 HELD-OUT recipes (Recipes 5 and 11)
        print("\n" + "=" * 70, flush=True)
        print("EVALUATION OF HELD-OUT RECIPES (Recipes 5 and 11)", flush=True)
        print("These recipes were NEVER used to adjust any dye strengths.", flush=True)
        print("=" * 70, flush=True)

        held_out_results = []
        for rec in HELD_OUT_RECIPES:
            meta = RECIPES[rec]
            out_png = args.render_dir / f"held_out_rec{rec:02d}.png"

            set_liquid_and_render_frame(
                stage=stage,
                kit=kit,
                tl=tl,
                rep=rep,
                rgb_annotator=rgb_annotator,
                time_codes_per_sec=time_codes_per_sec,
                orange_share=meta["orange"],
                blue_share=meta["blue"],
                volume_ml=meta["ml"],
                mixing=0.0,
                out_png_path=out_png,
                k_orange=best_k_orange,
                k_blue=best_k_blue,
                frame_num=686,
                subframes=32,
            )

            meas = measure_image(out_png)
            target_patch = meta["patch"]
            twin_norm_lab = np.array(meas["normalized"][target_patch]["Lab"])
            real_target_lab = targets[rec]["target_lab"]

            dE = float(colour.delta_E(twin_norm_lab, real_target_lab, method="CIE 2000"))
            held_out_results.append((rec, meta["ml"], target_patch, dE, twin_norm_lab, real_target_lab))

            print(
                f"HELD-OUT Recipe {rec:2d} ({meta['ml']:2.0f}mL, {target_patch:4s}): "
                f"twin Lab={np.round(twin_norm_lab, 2)} | real Lab={np.round(real_target_lab, 2)} | "
                f"dE2000={dE:5.2f}",
                flush=True,
            )

            history_rows.append({
                "recipe_id": rec,
                "round": "held_out",
                "orange_share": meta["orange"],
                "blue_share": meta["blue"],
                "total_ml": meta["ml"],
                "patch": target_patch,
                "dE2000": round(dE, 2),
                "twin_L": round(float(twin_norm_lab[0]), 2),
                "twin_a": round(float(twin_norm_lab[1]), 2),
                "twin_b": round(float(twin_norm_lab[2]), 2),
                "target_L": round(float(real_target_lab[0]), 2),
                "target_a": round(float(real_target_lab[1]), 2),
                "target_b": round(float(real_target_lab[2]), 2),
            })

        # Save calibration CSV
        with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(history_rows[0].keys()))
            writer.writeheader()
            writer.writerows(history_rows)
        print(f"\nSaved full calibration history to {args.out_csv}", flush=True)

    finally:
        kit.close()


if __name__ == "__main__":
    main()

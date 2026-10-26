"""Generate labeled synthetic training images using Isaac Sim twin with appearance variation.

Card 7 Step 6:
Renders diverse, physically calibrated training images of vials with varying dye shares,
fill volumes (concentrated in the small vial range 25-45 mL), vertical mixing states,
lighting brightness, color temperature, specular glare, camera jitter, and neighbour presence.

Dataset composition per batch of 200 (and across 1,000 images):
- Exactly 30% clean recipes (6 of each recipe 5..14 per batch; 30 of each overall) at real volume +/- a little.
  Includes pure orange (Recipe 6: blue = 0.0) and strongest blue (Recipe 7: blue = 0.714).
- 45% contaminated carryover mixtures between recipe pairs (alpha in [0.04, 0.45]).
- 25% continuous exploration across orange [0..0.72] and blue [0..0.72] with orange + blue <= 1.0.
- Fill volumes: >= 40% concentrated in small vial range [25, 45] mL.

Reads:
- Twin stage: /workspace/project/twin/csi_digital_twin_v1/csi_line.usda
- Camera config: /workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json
- Dye strengths: outputs/card7/twin_dye_strengths.json
- Fill height model: outputs/card7/twin_fill_height.json

Writes:
- Rendered PNG images in batches of 200: /workspace/project/renders/card7_dataset/batch_000/img_000000.png ...
- labels.csv per batch recording parameters and patch color measurements (measure_patches.py)
- Timing entry appended to outputs/run_log.csv

Execution:
    nohup /isaac-sim/python.sh scripts/generate_dataset.py --num-images 1000 --batch-size 200 > /workspace/project/logs/dataset_1000.log 2>&1 &
"""

import argparse
from collections import Counter
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import random
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from scripts.measure_patches import measure_image
from scripts.set_liquid import (
    DEFAULT_DYE_STRENGTHS_JSON,
    DEFAULT_FILL_HEIGHT_JSON,
    LIQUID_RADIUS_IN,
    VIAL_INNER_BOTTOM_Z_IN,
    build_cylinder_geometry,
    compute_fill_height_in,
    compute_transmittance,
    configure_liquid_material,
    generate_mixing_gradient_texture,
    load_dye_strengths,
)

# Reference recipe specifications from real plant
PLANT_RECIPES = [
    {"recipe": 5, "orange": 0.3333, "blue": 0.3333, "real_ml": 30.0},
    {"recipe": 6, "orange": 0.2500, "blue": 0.0000, "real_ml": 40.0},  # Pure orange (blue = 0)
    {"recipe": 7, "orange": 0.0000, "blue": 0.7143, "real_ml": 70.0},  # Strongest blue (orange = 0)
    {"recipe": 8, "orange": 0.3333, "blue": 0.3333, "real_ml": 60.0},
    {"recipe": 9, "orange": 0.4375, "blue": 0.4375, "real_ml": 80.0},
    {"recipe": 10, "orange": 0.2000, "blue": 0.2000, "real_ml": 75.0},
    {"recipe": 11, "orange": 0.1429, "blue": 0.7143, "real_ml": 70.0},
    {"recipe": 12, "orange": 0.7143, "blue": 0.1429, "real_ml": 70.0},
    {"recipe": 13, "orange": 0.7143, "blue": 0.2857, "real_ml": 70.0},
    {"recipe": 14, "orange": 0.0000, "blue": 0.1429, "real_ml": 70.0},  # Pale blue (orange = 0)
]

# USD Units conversion for FillCam jitter: 1 px = aperture_mm / res_px in USD units
# 640x480 resolution, horizontal aperture = 0.360, vertical = 0.270
USD_PER_PIXEL_X = 0.360 / 640.0  # 0.0005625
USD_PER_PIXEL_Y = 0.270 / 480.0  # 0.0005625

# Base intensities of the 3 primary station lights
LIGHT_BASES = {
    "/CSI_Line/FillStation/FillStation_LocalRoot/Fill_overhead_panel/Fill_overhead_panel": 557.04,
    "/CSI_Line/FillStation/FillStation_LocalRoot/Fill_front_softbox/Fill_front_softbox": 206.90,
    "/CSI_Line/FillStation/FillStation_LocalRoot/Fill_right_reflection/Fill_right_reflection": 143.24,
}


def get_gpu_name() -> str:
    """Query GPU model name."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip().splitlines()[0]
    except Exception:
        return "Unknown GPU"


def build_batch_plan(batch_idx: int, batch_size: int, rng: random.Random) -> List[Dict[str, Any]]:
    """Build randomized parameter plan for one batch with guaranteed recipe distributions."""
    items: List[Dict[str, Any]] = []

    # 1. Exactly 30% Clean Recipes (in equal numbers across all 10 recipes)
    # E.g. for batch_size=200, 60 clean images = 6 of each of the 10 recipes
    num_clean_per_rec = max(1, int(round(batch_size * 0.30 / len(PLANT_RECIPES))))
    for rec in PLANT_RECIPES:
        for _ in range(num_clean_per_rec):
            vol = round(float(np.clip(rec["real_ml"] + rng.uniform(-3.0, 3.0), 10.0, 80.0)), 1)
            # Orange share
            if rec["orange"] == 0.0:
                o_share = 0.0  # Strictly 0 for R7 and R14
            else:
                o_share = float(np.clip(rec["orange"] + rng.uniform(-0.01, 0.01), 0.001, 0.720))
            # Blue share
            if rec["blue"] == 0.0:
                b_share = 0.0  # Strictly 0 for R6 (pure orange)
            else:
                b_share = float(np.clip(rec["blue"] + rng.uniform(-0.01, 0.01), 0.001, 0.720))

            items.append({
                "category": "clean",
                "clean_recipe_id": rec["recipe"],
                "mix_type": f"clean_R{rec['recipe']:02d}",
                "orange_share": round(o_share, 4),
                "blue_share": round(b_share, 4),
                "fill_ml": vol,
                "mixing": 0.0 if rng.random() < 0.65 else round(rng.uniform(0.05, 0.35), 2),
            })

    # 2. Remaining items (70%): Contaminated mixes (45%) and Free exploration (25%)
    rem_count = batch_size - len(items)
    num_contam = int(round(batch_size * 0.45))
    num_explore = rem_count - num_contam

    # Guarantee >= 40% small vials ([25, 45] mL) across the batch
    # Clean recipes R5 (30 mL) and R6 (40 mL) provide 2 * num_clean_per_rec small vials.
    clean_small = 2 * num_clean_per_rec
    needed_small = max(0, int(round(batch_size * 0.42)) - clean_small)
    is_small_flags = [True] * needed_small + [False] * (rem_count - needed_small)
    rng.shuffle(is_small_flags)

    for i in range(rem_count):
        is_small = is_small_flags[i]
        vol = round(rng.uniform(25.0, 45.0) if is_small else rng.uniform(10.0, 80.0), 1)

        if i < num_contam:
            # Contaminated mix between two recipes
            rec_b = rng.choice(PLANT_RECIPES)
            rec_a = rng.choice([r for r in PLANT_RECIPES if r["recipe"] != rec_b["recipe"]])
            alpha = rng.uniform(0.04, 0.45)
            o_s = (1.0 - alpha) * rec_b["orange"] + alpha * rec_a["orange"] + rng.uniform(-0.008, 0.008)
            b_s = (1.0 - alpha) * rec_b["blue"] + alpha * rec_a["blue"] + rng.uniform(-0.008, 0.008)
            o_s = float(np.clip(o_s, 0.0, 0.720))
            b_s = float(np.clip(b_s, 0.0, 0.720))
            if o_s + b_s > 1.0:
                scale = 0.98 / (o_s + b_s)
                o_s *= scale
                b_s *= scale
            items.append({
                "category": "contaminated",
                "clean_recipe_id": None,
                "mix_type": f"carryover_R{rec_a['recipe']:02d}->R{rec_b['recipe']:02d}_a{alpha:.2f}",
                "orange_share": round(o_s, 4),
                "blue_share": round(b_s, 4),
                "fill_ml": vol,
                "mixing": 0.0 if rng.random() < 0.20 else round(rng.uniform(0.10, 1.00), 2),
            })
        else:
            # Free exploration across orange 0..0.72 and blue 0..0.72 with orange + blue <= 1.0
            while True:
                o_s = rng.uniform(0.0, 0.720)
                b_s = rng.uniform(0.0, 0.720)
                if o_s + b_s <= 1.0:
                    break
            items.append({
                "category": "exploration",
                "clean_recipe_id": None,
                "mix_type": "random_mix",
                "orange_share": round(o_s, 4),
                "blue_share": round(b_s, 4),
                "fill_ml": vol,
                "mixing": 0.0 if rng.random() < 0.25 else round(rng.uniform(0.10, 1.00), 2),
            })

    # Shuffle so batch items are well interweaved
    rng.shuffle(items)

    # Add environment appearance parameters to each item
    for item in items:
        # Light brightness (+/- 30%) and color temperature (4800K - 7500K)
        item["light_mult"] = round(rng.uniform(0.70, 1.30), 3)
        item["color_temp_k"] = round(rng.uniform(4800.0, 7500.0), 1)

        # Glare light: 50% chance
        has_glare = rng.random() < 0.50
        glare_x = round(rng.uniform(2.5, 5.5), 2)
        glare_y = round(rng.uniform(-5.5, -2.5), 2)
        glare_z = round(rng.uniform(3.5, 7.5), 2)
        glare_intensity = round(rng.uniform(150.0, 350.0), 1) if has_glare else 0.0
        item["has_glare"] = has_glare
        item["glare_pos"] = (glare_x, glare_y, glare_z)
        item["glare_intensity"] = glare_intensity

        # Camera Jitter: 1-2 pixels
        item["jitter_x_px"] = round(rng.uniform(-2.0, 2.0), 2)
        item["jitter_y_px"] = round(rng.uniform(-2.0, 2.0), 2)

        # Neighbour vial present: 90% present, 10% absent
        item["neighbour_present"] = rng.random() >= 0.10

    return items


def print_batch_metrics(batch_name: str, items: List[Dict[str, Any]]):
    """Print detailed summary statistics and clean recipe counts for a batch."""
    clean_items = [it for it in items if it["category"] == "clean"]
    counts = Counter(it["clean_recipe_id"] for it in clean_items)

    mls = [it["fill_ml"] for it in items]
    o_shares = [it["orange_share"] for it in items]
    b_shares = [it["blue_share"] for it in items]
    mixings = [it["mixing"] for it in items]
    l_mults = [it["light_mult"] for it in items]
    cts = [it["color_temp_k"] for it in items]
    glares = [it["has_glare"] for it in items]
    jx = [it["jitter_x_px"] for it in items]
    jy = [it["jitter_y_px"] for it in items]
    neighs = [it["neighbour_present"] for it in items]

    small_count = sum(1 for m in mls if 25.0 <= m <= 45.0)

    print("=" * 65, flush=True)
    print(f"BATCH SPECIFICATION SUMMARY: {batch_name} ({len(items)} images)", flush=True)
    print("=" * 65, flush=True)
    print("1. Clean Recipes (30% of batch):")
    print(f"   Total clean images: {len(clean_items)}/{len(items)} ({len(clean_items)/len(items)*100:.1f}%)")
    print("   Count per clean recipe:")
    for r in sorted(counts.keys()):
        nominal = next(rec for rec in PLANT_RECIPES if rec["recipe"] == r)
        r_instances = [it for it in clean_items if it["clean_recipe_id"] == r]
        o_rng = (min(it["orange_share"] for it in r_instances), max(it["orange_share"] for it in r_instances))
        b_rng = (min(it["blue_share"] for it in r_instances), max(it["blue_share"] for it in r_instances))
        v_rng = (min(it["fill_ml"] for it in r_instances), max(it["fill_ml"] for it in r_instances))
        print(f"     Recipe {r:02d}: count={counts[r]} | O=[{o_rng[0]:.4f}, {o_rng[1]:.4f}] B=[{b_rng[0]:.4f}, {b_rng[1]:.4f}] | Vol=[{v_rng[0]:.1f}, {v_rng[1]:.1f}] mL (nom: {nominal['real_ml']}mL)")

    print("\n2. Full Batch Parameter Ranges:")
    print(f"   Orange Share: [{min(o_shares):.4f}, {max(o_shares):.4f}] (mean={sum(o_shares)/len(o_shares):.4f})")
    print(f"   Blue Share:   [{min(b_shares):.4f}, {max(b_shares):.4f}] (mean={sum(b_shares)/len(b_shares):.4f})")
    print(f"   Fill Volume:  [{min(mls):.1f}, {max(mls):.1f}] mL (mean={sum(mls)/len(mls):.1f} mL)")
    print(f"   Small Vials [25, 45] mL: {small_count}/{len(items)} ({small_count/len(items)*100:.1f}%) [Requirement >= 40%]")
    print(f"   Mixing:       [{min(mixings):.2f}, {max(mixings):.2f}] (unmixed={sum(1 for m in mixings if m == 0.0)}, stratified={sum(1 for m in mixings if m > 0.0)})")
    print(f"   Lighting:     [{min(l_mults):.3f}, {max(l_mults):.3f}] (+/- 30%)")
    print(f"   Color Temp:   [{min(cts):.1f}, {max(cts):.1f}] K")
    print(f"   Glare Light:  {sum(glares)}/{len(items)} ({sum(glares)/len(items)*100:.1f}%)")
    print(f"   Camera Jitter X: [{min(jx):.2f}, {max(jx):.2f}] px")
    print(f"   Camera Jitter Y: [{min(jy):.2f}, {max(jy):.2f}] px")
    print(f"   Neighbour Absent: {sum(not n for n in neighs)}/{len(items)} ({sum(not n for n in neighs)/len(items)*100:.1f}%)")
    print("=" * 65, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Generate labeled synthetic twin training dataset.")
    parser.add_argument("--num-images", type=int, default=1000, help="Total number of images to generate")
    parser.add_argument("--batch-size", type=int, default=200, help="Number of images per batch folder")
    parser.add_argument("--smoke-test", action="store_true", help="Run 30-image smoke test")
    parser.add_argument("--out-dir", type=Path, default=Path("/workspace/project/renders/card7_dataset"), help="Base output directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--subframes", type=int, default=32, help="Path tracing subframes per frame")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from last completed batch")
    parser.add_argument("--dye-strengths", type=Path, default=DEFAULT_DYE_STRENGTHS_JSON, help="twin_dye_strengths.json")
    parser.add_argument("--fill-height", type=Path, default=DEFAULT_FILL_HEIGHT_JSON, help="twin_fill_height.json")
    parser.add_argument("--stage", default="/workspace/project/twin/csi_digital_twin_v1/csi_line.usda", help="USD stage")
    parser.add_argument("--camera-config", default="/workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json", help="Camera JSON")
    parser.add_argument("--log-file", type=Path, default=Path("/workspace/project/repo/outputs/run_log.csv"), help="run_log.csv")
    args = parser.parse_args()

    if args.smoke_test:
        args.num_images = 30
        args.batch_size = 30
        batch_names = ["smoke_test"]
    else:
        num_batches = math.ceil(args.num_images / args.batch_size)
        batch_names = [f"batch_{b:03d}" for b in range(num_batches)]

    base_out_dir = args.out_dir.resolve()
    base_out_dir.mkdir(parents=True, exist_ok=True)
    args.log_file.parent.mkdir(parents=True, exist_ok=True)

    gpu_name = get_gpu_name()
    k_orange, k_blue = load_dye_strengths(args.dye_strengths)

    with open(args.camera_config, "r", encoding="utf-8") as f:
        cam_meta = json.load(f)

    rw, rh = cam_meta.get("render_px", [640, 480])
    fps = cam_meta.get("fps", 30)

    print("=" * 65, flush=True)
    print("CARD 7 STEP 6: SYNTHETIC DATASET GENERATION", flush=True)
    print(f"GPU: {gpu_name}", flush=True)
    print(f"Mode: {'SMOKE TEST' if args.smoke_test else f'FULL DATASET ({args.num_images} images, {len(batch_names)} batches of {args.batch_size})'}", flush=True)
    print(f"Target directory: {base_out_dir}", flush=True)
    print("=" * 65, flush=True)

    rng = random.Random(args.seed)

    # Pre-generate plans for all batches
    all_batch_plans = []
    global_img_idx = 0
    for b_idx, b_name in enumerate(batch_names):
        curr_batch_size = min(args.batch_size, args.num_images - global_img_idx)
        b_items = build_batch_plan(b_idx, curr_batch_size, rng)
        for it in b_items:
            it["image_idx"] = global_img_idx
            global_img_idx += 1
        all_batch_plans.append((b_name, b_items))

    # Print First Batch (batch_000) Metrics
    print_batch_metrics(all_batch_plans[0][0], all_batch_plans[0][1])

    t_start_all = time.time()
    total_rendered_count = 0

    print(f"\nInitializing SimulationApp ({rw}x{rh}, PathTracing)...", flush=True)
    from isaacsim import SimulationApp

    kit = SimulationApp({"headless": True, "renderer": "PathTracing", "width": rw, "height": rh})

    try:
        from isaacsim.core.utils.extensions import enable_extension
        enable_extension("omni.replicator.core")

        import omni.timeline
        import omni.usd
        import omni.replicator.core as rep
        from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade

        ctx = omni.usd.get_context()
        if not ctx.open_stage(args.stage):
            raise RuntimeError(f"Could not open USD stage: {args.stage}")

        while ctx.get_stage_loading_status()[2] > 0:
            kit.update()
        for _ in range(5):
            kit.update()

        stage = ctx.get_stage()

        candidates = [cam_meta.get("prim_in_csi_line"), cam_meta.get("prim_in_station_file")]
        cam_prim_path = next((p for p in candidates if p and stage.GetPrimAtPath(p).IsValid()), None)
        if cam_prim_path is None:
            raise RuntimeError("Camera prim not found.")

        cam_prim = stage.GetPrimAtPath(cam_prim_path)
        camera_api = UsdGeom.Camera(cam_prim)

        # Timeline and replicator
        tl = omni.timeline.get_timeline_interface()
        time_codes_per_sec = stage.GetTimeCodesPerSecond() or fps
        frame_num = 686
        target_time = frame_num / time_codes_per_sec

        rp = rep.create.render_product(cam_prim_path, (rw, rh))
        rgb_annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb_annotator.attach([rp])
        rep.orchestrator.set_capture_on_play(False)
        kit.update()

        # Camera clipping fix
        clip_attr = camera_api.GetClippingRangeAttr()
        near_far = clip_attr.Get()
        if near_far is not None:
            stage.SetEditTarget(stage.GetSessionLayer())
            clip_attr.Set(Gf.Vec2f(near_far[0] * 0.5, near_far[1]))
            kit.update()
            clip_attr.Set(near_far)
            kit.update()

        # Hide original animated liquid
        old_prim = stage.GetPrimAtPath("/CSI_Line/FillStation/FillStation_LocalRoot/Fill_liquid/Fill_liquid")
        if old_prim.IsValid():
            UsdGeom.Imageable(old_prim).MakeInvisible()

        # Cache light prims
        light_prims = {}
        for lp in LIGHT_BASES:
            p = stage.GetPrimAtPath(lp)
            if p.IsValid():
                light_prims[lp] = UsdLux.RectLight(p)

        # Extra Glare Light prim
        glare_path = Sdf.Path("/CSI_Line/FillStation/FillStation_LocalRoot/Extra_GlareLight")
        glare_prim = stage.GetPrimAtPath(glare_path)
        if not glare_prim.IsValid():
            glare_light = UsdLux.SphereLight.Define(stage, glare_path)
            glare_light.CreateRadiusAttr().Set(0.5)
            glare_xform = UsdGeom.Xformable(glare_light.GetPrim())
            glare_trans_op = glare_xform.AddTranslateOp()
        else:
            glare_light = UsdLux.SphereLight(glare_prim)
            glare_xform = UsdGeom.Xformable(glare_prim)
            glare_trans_op = glare_xform.GetOrderedXformOps()[0]

        # Neighbour vial prim
        neighbour_prim = stage.GetPrimAtPath("/CSI_Line/FillStation/FillStation_LocalRoot/Fill_vial_neighbour_1")
        neighbour_imgbl = UsdGeom.Imageable(neighbour_prim) if neighbour_prim.IsValid() else None

        # Liquid cylinder prim
        cyl_prim_path = Sdf.Path("/CSI_Line/FillStation/FillStation_LocalRoot/Custom_Liquid")

        # Process each batch
        for b_idx, (b_name, batch_items) in enumerate(all_batch_plans):
            batch_dir = base_out_dir / b_name
            batch_labels_csv = batch_dir / "labels.csv"

            if args.resume and batch_labels_csv.is_file():
                # Check if batch is already fully completed
                with open(batch_labels_csv, "r", encoding="utf-8") as f:
                    completed_count = sum(1 for _ in f) - 1
                if completed_count == len(batch_items):
                    print(f"Skipping already completed batch: {b_name} ({completed_count} images)", flush=True)
                    continue

            batch_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n--- Starting Batch {b_idx + 1}/{len(all_batch_plans)}: {b_name} ({len(batch_items)} images) ---", flush=True)

            batch_records = []
            t_batch_start = time.time()

            for item_idx, item in enumerate(batch_items):
                idx = item["image_idx"]
                img_filename = f"img_{idx:06d}.png"
                out_png_path = batch_dir / img_filename

                t0 = time.time()

                # A. Apply Camera Jitter
                dx_usd = item["jitter_x_px"] * USD_PER_PIXEL_X
                dy_usd = item["jitter_y_px"] * USD_PER_PIXEL_Y
                camera_api.GetHorizontalApertureOffsetAttr().Set(dx_usd)
                camera_api.GetVerticalApertureOffsetAttr().Set(dy_usd)

                # B. Apply Neighbour Vial Visibility
                if neighbour_imgbl is not None:
                    if item["neighbour_present"]:
                        neighbour_imgbl.MakeVisible()
                    else:
                        neighbour_imgbl.MakeInvisible()

                # C. Apply Light Brightness and Color Temperature
                l_mult = item["light_mult"]
                ct = item["color_temp_k"]
                for lp, base_intensity in LIGHT_BASES.items():
                    if lp in light_prims:
                        light_prims[lp].GetIntensityAttr().Set(base_intensity * l_mult)
                        light_prims[lp].GetEnableColorTemperatureAttr().Set(True)
                        light_prims[lp].GetColorTemperatureAttr().Set(ct)

                # D. Apply Glare Light
                if item["has_glare"]:
                    gx, gy, gz = item["glare_pos"]
                    glare_trans_op.Set(Gf.Vec3d(gx, gy, gz))
                    glare_light.GetIntensityAttr().Set(item["glare_intensity"])
                    UsdGeom.Imageable(glare_light.GetPrim()).MakeVisible()
                else:
                    glare_light.GetIntensityAttr().Set(0.0)
                    UsdGeom.Imageable(glare_light.GetPrim()).MakeInvisible()

                # E. Build Cylinder Geometry (Calibrated Fill Height)
                h_in = compute_fill_height_in(item["fill_ml"], args.fill_height)
                z_bottom_in = VIAL_INNER_BOTTOM_Z_IN
                z_top_in = z_bottom_in + h_in
                mesh = build_cylinder_geometry(
                    stage, cyl_prim_path, LIQUID_RADIUS_IN, z_bottom_in, z_top_in, num_segments=64
                )

                # F. Configure Volumetric Material (OmniSurface MDL)
                T = compute_transmittance(item["orange_share"], item["blue_share"], k_orange, k_blue)
                texture_path = None
                if item["mixing"] > 0.0:
                    grad_png = batch_dir / f"grad_{idx:06d}.png"
                    texture_path = generate_mixing_gradient_texture(
                        item["orange_share"], item["blue_share"], item["mixing"], k_orange, k_blue, grad_png
                    )

                mat_prim_path = Sdf.Path(f"/CSI_Line/FillStation/FillStation_LocalRoot/Mat_{b_name}_{idx:06d}")
                mat = configure_liquid_material(stage, mat_prim_path, T, item["mixing"], texture_path)
                UsdShade.MaterialBindingAPI(mesh).Bind(mat)

                # G. Advance timeline and render
                tl.set_current_time(target_time)
                kit.update()

                for _ in range(2):
                    rep.orchestrator.step(rt_subframes=args.subframes, delta_time=0.0)

                data = np.asarray(rgb_annotator.get_data())
                img_bgr = data[..., :3][..., ::-1].copy()

                if not cv2.imwrite(str(out_png_path), img_bgr):
                    raise OSError(f"Failed to write image: {out_png_path}")

                # Clean up gradient texture file to save disk space
                if texture_path is not None and texture_path.is_file():
                    try:
                        texture_path.unlink()
                    except Exception:
                        pass

                # H. Measure Patches (raw and blank-normalized Lab)
                meas = measure_image(
                    out_png_path,
                    neighbour_present=item["neighbour_present"],
                )

                p_high = meas["patches"]["HIGH"]
                p_low = meas["patches"]["LOW"]
                n_high = meas["normalized"]["HIGH"]
                n_low = meas["normalized"]["LOW"]
                p_bhigh = meas["patches"]["BLANK_HIGH"]
                p_blow = meas["patches"]["BLANK_LOW"]

                dt = time.time() - t0
                total_rendered_count += 1

                batch_records.append({
                    "file": img_filename,
                    "image_id": idx,
                    "category": item["category"],
                    "clean_recipe_id": item["clean_recipe_id"] if item["clean_recipe_id"] is not None else "",
                    "mix_type": item["mix_type"],
                    "orange_share": item["orange_share"],
                    "blue_share": item["blue_share"],
                    "fill_ml": item["fill_ml"],
                    "mixing": item["mixing"],
                    "light_brightness": item["light_mult"],
                    "color_temp_k": item["color_temp_k"],
                    "glare": item["has_glare"],
                    "camera_jitter_x_px": item["jitter_x_px"],
                    "camera_jitter_y_px": item["jitter_y_px"],
                    "neighbour_present": item["neighbour_present"],
                    "raw_high_L": p_high["Lab"][0],
                    "raw_high_a": p_high["Lab"][1],
                    "raw_high_b": p_high["Lab"][2],
                    "raw_low_L": p_low["Lab"][0],
                    "raw_low_a": p_low["Lab"][1],
                    "raw_low_b": p_low["Lab"][2],
                    "norm_high_L": n_high["Lab"][0],
                    "norm_high_a": n_high["Lab"][1],
                    "norm_high_b": n_high["Lab"][2],
                    "norm_low_L": n_low["Lab"][0],
                    "norm_low_a": n_low["Lab"][1],
                    "norm_low_b": n_low["Lab"][2],
                    "blank_high_L": p_bhigh["Lab"][0],
                    "blank_low_L": p_blow["Lab"][0],
                })

                if ((item_idx + 1) % 20 == 0) or (item_idx + 1 == len(batch_items)):
                    elapsed_batch = time.time() - t_batch_start
                    fps_eff = (item_idx + 1) / max(elapsed_batch, 0.001)
                    eta_mins = (len(batch_items) - (item_idx + 1)) / (fps_eff * 60.0)
                    print(f"  [{item_idx + 1:3d}/{len(batch_items)}] {img_filename}: V={item['fill_ml']:4.1f}mL, O={item['orange_share']:.3f}, B={item['blue_share']:.3f}, mix={item['mixing']:.2f} ({fps_eff:.2f} img/s, ETA: {eta_mins:.1f}m)", flush=True)

            # Write batch labels.csv
            with open(batch_labels_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(batch_records[0].keys()))
                writer.writeheader()
                writer.writerows(batch_records)

            batch_mins = (time.time() - t_batch_start) / 60.0
            print(f"Completed {b_name}: {len(batch_records)} images in {batch_mins:.2f} min -> {batch_labels_csv}\n", flush=True)

        # Record total run to outputs/run_log.csv
        total_mins = (time.time() - t_start_all) / 60.0
        job_name = "card7_step6_smoke_test" if args.smoke_test else f"card7_step6_dataset_{args.num_images}"
        with open(args.log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                gpu_name,
                job_name,
                f"{total_mins:.2f}",
                total_rendered_count,
            ])

        print("=" * 65, flush=True)
        print(f"Dataset generation finished! Total {total_rendered_count} images rendered in {total_mins:.2f} min.", flush=True)
        print(f"Logged to {args.log_file}", flush=True)
        print("=" * 65, flush=True)

    finally:
        kit.close()


if __name__ == "__main__":
    main()

"""Card 7 Step 7: Lighting robustness test (raw vs blank-normalized color checks).

One job: Renders Recipes 7, 9, 12, and 14 in both clean and carryover-tinted states
(tinted with 15% of the preceding recipe's mix) under 5 lighting setups:
1. Normal lighting (1.0x baseline)
2. 30% Dimmer (0.70x baseline)
3. 30% Brighter (1.30x baseline)
4. Side light only (right reflection light only, overhead and front softbox off)
5. Normal plus extra specular glare spot

Measures HIGH patch raw Lab and blank-normalized Lab with measure_patches.py.
Computes Delta E 2000 against the normal clean baseline for each recipe and determines
verdicts (PASS < 2.0 / UNSURE 2.0-5.0 / FAIL > 5.0).
Quantifies how often verdicts change under lighting perturbations for raw vs normalized checks.

Reads:
- Twin stage: /workspace/project/twin/csi_digital_twin_v1/csi_line.usda
- Camera config: /workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json
- Dye strengths: outputs/card7/twin_dye_strengths.json
- Fill height: outputs/card7/twin_fill_height.json

Writes:
- 40 rendered images in /workspace/project/renders/card7_lighting/
- outputs/card7/lighting_test.csv
"""

import argparse
import csv
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Tuple
import colour
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
    load_dye_strengths,
)

# Test recipes (all tall vials evaluated on HIGH patch)
# Preceding recipes in Video 5 sequence:
# Before R7 was R6 (orange 0.25, blue 0.0)
# Before R9 was R8 (orange 0.3333, blue 0.3333)
# Before R12 was R11 (orange 0.1429, blue 0.7143)
# Before R14 was R13 (orange 0.7143, blue 0.2857)
RECIPES_TEST = [
    {
        "recipe": 7,
        "ml": 70.0,
        "clean": {"orange": 0.0000, "blue": 0.7143},
        "tinted_15": {"orange": 0.85 * 0.0000 + 0.15 * 0.2500, "blue": 0.85 * 0.7143 + 0.15 * 0.0000},
        "prev_recipe": 6,
    },
    {
        "recipe": 9,
        "ml": 80.0,
        "clean": {"orange": 0.4375, "blue": 0.4375},
        "tinted_15": {"orange": 0.85 * 0.4375 + 0.15 * 0.3333, "blue": 0.85 * 0.4375 + 0.15 * 0.3333},
        "prev_recipe": 8,
    },
    {
        "recipe": 12,
        "ml": 70.0,
        "clean": {"orange": 0.7143, "blue": 0.1429},
        "tinted_15": {"orange": 0.85 * 0.7143 + 0.15 * 0.1429, "blue": 0.85 * 0.1429 + 0.15 * 0.7143},
        "prev_recipe": 11,
    },
    {
        "recipe": 14,
        "ml": 70.0,
        "clean": {"orange": 0.0000, "blue": 0.1429},
        "tinted_15": {"orange": 0.85 * 0.0000 + 0.15 * 0.7143, "blue": 0.85 * 0.1429 + 0.15 * 0.2857},
        "prev_recipe": 13,
    },
]

# Base light intensities
LIGHT_PATHS = {
    "overhead": "/CSI_Line/FillStation/FillStation_LocalRoot/Fill_overhead_panel/Fill_overhead_panel",
    "softbox": "/CSI_Line/FillStation/FillStation_LocalRoot/Fill_front_softbox/Fill_front_softbox",
    "right": "/CSI_Line/FillStation/FillStation_LocalRoot/Fill_right_reflection/Fill_right_reflection",
}
BASE_INTENSITIES = {
    "overhead": 557.04,
    "softbox": 206.90,
    "right": 143.24,
}

LIGHTING_SETUPS = [
    {"name": "normal", "scale_overhead": 1.0, "scale_softbox": 1.0, "scale_right": 1.0, "glare": False},
    {"name": "dimmer_30", "scale_overhead": 0.70, "scale_softbox": 0.70, "scale_right": 0.70, "glare": False},
    {"name": "brighter_30", "scale_overhead": 1.30, "scale_softbox": 1.30, "scale_right": 1.30, "glare": False},
    {"name": "side_only", "scale_overhead": 0.0, "scale_softbox": 0.0, "scale_right": 1.0, "glare": False},
    {"name": "glare", "scale_overhead": 1.0, "scale_softbox": 1.0, "scale_right": 1.0, "glare": True},
]


def get_verdict(delta_e: float) -> str:
    """Classify Delta E 2000 into standard project verdicts."""
    if delta_e < 2.0:
        return "PASS"
    elif delta_e <= 5.0:
        return "UNSURE"
    else:
        return "FAIL"


def main():
    parser = argparse.ArgumentParser(description="Card 7 Step 7 lighting robustness test.")
    parser.add_argument("--out-dir", type=Path, default=Path("/workspace/project/renders/card7_lighting"), help="Output renders dir")
    parser.add_argument("--csv-out", type=Path, default=Path("/workspace/project/repo/outputs/card7/lighting_test.csv"), help="Output CSV")
    parser.add_argument("--stage", default="/workspace/project/twin/csi_digital_twin_v1/csi_line.usda", help="USD stage file")
    parser.add_argument("--camera-config", default="/workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json", help="Camera JSON")
    parser.add_argument("--dye-strengths", type=Path, default=DEFAULT_DYE_STRENGTHS_JSON, help="twin_dye_strengths.json")
    parser.add_argument("--fill-height", type=Path, default=DEFAULT_FILL_HEIGHT_JSON, help="twin_fill_height.json")
    parser.add_argument("--subframes", type=int, default=32, help="Path tracing subframes")
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    args.csv_out.parent.mkdir(parents=True, exist_ok=True)

    k_orange, k_blue = load_dye_strengths(args.dye_strengths)

    with open(args.camera_config, "r", encoding="utf-8") as f:
        cam_meta = json.load(f)

    rw, rh = cam_meta.get("render_px", [640, 480])
    fps = cam_meta.get("fps", 30)

    print("=" * 70, flush=True)
    print("CARD 7 STEP 7: LIGHTING ROBUSTNESS TEST (RAW VS BLANK-NORMALIZED)", flush=True)
    print(f"Recipes: {[r['recipe'] for r in RECIPES_TEST]} (Clean + 15% Tinted)")
    print(f"Lighting Setups: {[s['name'] for s in LIGHTING_SETUPS]}")
    print(f"Total Renders: {len(RECIPES_TEST) * 2 * len(LIGHTING_SETUPS)}")
    print(f"Destination: {out_dir}", flush=True)
    print("=" * 70, flush=True)

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

        # Station lights
        light_prims = {k: UsdLux.RectLight(stage.GetPrimAtPath(p)) for k, p in LIGHT_PATHS.items()}

        # Glare light
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

        glare_trans_op.Set(Gf.Vec3d(3.5, -4.0, 5.0))

        # Liquid cylinder prim
        cyl_prim_path = Sdf.Path("/CSI_Line/FillStation/FillStation_LocalRoot/Custom_Liquid")

        raw_results: List[Dict[str, Any]] = []

        # Render loop
        t_start = time.time()
        for r_info in RECIPES_TEST:
            rec = r_info["recipe"]
            vol_ml = r_info["ml"]

            # Height geometry
            h_in = compute_fill_height_in(vol_ml, args.fill_height)
            z_bottom_in = VIAL_INNER_BOTTOM_Z_IN
            z_top_in = z_bottom_in + h_in
            mesh = build_cylinder_geometry(stage, cyl_prim_path, LIQUID_RADIUS_IN, z_bottom_in, z_top_in, num_segments=64)

            for state in ["clean", "tinted_15"]:
                dyes = r_info[state]
                o_share = dyes["orange"]
                b_share = dyes["blue"]

                T = compute_transmittance(o_share, b_share, k_orange, k_blue)
                mat_prim_path = Sdf.Path(f"/CSI_Line/FillStation/FillStation_LocalRoot/Mat_R{rec:02d}_{state}")
                mat = configure_liquid_material(stage, mat_prim_path, T, mixing=0.0, texture_path=None)
                UsdShade.MaterialBindingAPI(mesh).Bind(mat)

                for setup in LIGHTING_SETUPS:
                    s_name = setup["name"]
                    filename = f"rec{rec:02d}_{state}_{s_name}.png"
                    out_png = out_dir / filename

                    # Configure lights
                    for l_key, l_prim in light_prims.items():
                        scale = setup[f"scale_{l_key}"]
                        l_prim.GetIntensityAttr().Set(BASE_INTENSITIES[l_key] * scale)
                        l_prim.GetEnableColorTemperatureAttr().Set(False)

                    if setup["glare"]:
                        glare_light.GetIntensityAttr().Set(250.0)
                        UsdGeom.Imageable(glare_light.GetPrim()).MakeVisible()
                    else:
                        glare_light.GetIntensityAttr().Set(0.0)
                        UsdGeom.Imageable(glare_light.GetPrim()).MakeInvisible()

                    # Render
                    tl.set_current_time(target_time)
                    kit.update()

                    for _ in range(2):
                        rep.orchestrator.step(rt_subframes=args.subframes, delta_time=0.0)

                    data = np.asarray(rgb_annotator.get_data())
                    img_bgr = data[..., :3][..., ::-1].copy()
                    cv2.imwrite(str(out_png), img_bgr)

                    # Measure patches
                    meas = measure_image(out_png, neighbour_present=True)
                    p_high = meas["patches"]["HIGH"]
                    n_high = meas["normalized"]["HIGH"]

                    raw_results.append({
                        "recipe": rec,
                        "state": state,
                        "setup": s_name,
                        "filename": filename,
                        "orange_share": round(o_share, 4),
                        "blue_share": round(b_share, 4),
                        "fill_ml": vol_ml,
                        "raw_high_Lab": np.array(p_high["Lab"]),
                        "norm_high_Lab": np.array(n_high["Lab"]),
                    })

                    print(f"  Rendered {filename} -> raw Lab={p_high['Lab']}, norm Lab={n_high['Lab']}", flush=True)

        # Baseline reference: clean render under normal light for each recipe
        ref_colors = {}
        for row in raw_results:
            if row["state"] == "clean" and row["setup"] == "normal":
                ref_colors[row["recipe"]] = {
                    "raw_Lab": row["raw_high_Lab"],
                    "norm_Lab": row["norm_high_Lab"],
                }

        # Analyze Delta E and verdicts
        output_rows = []
        for row in raw_results:
            rec = row["recipe"]
            ref = ref_colors[rec]

            dE_raw = float(colour.delta_E(ref["raw_Lab"], row["raw_high_Lab"], method="CIE 2000"))
            dE_norm = float(colour.delta_E(ref["norm_Lab"], row["norm_high_Lab"], method="CIE 2000"))

            verdict_raw = get_verdict(dE_raw)
            verdict_norm = get_verdict(dE_norm)

            output_rows.append({
                "recipe": rec,
                "state": row["state"],
                "setup": row["setup"],
                "filename": row["filename"],
                "orange_share": row["orange_share"],
                "blue_share": row["blue_share"],
                "fill_ml": row["fill_ml"],
                "raw_L": round(row["raw_high_Lab"][0], 2),
                "raw_a": round(row["raw_high_Lab"][1], 2),
                "raw_b": round(row["raw_high_Lab"][2], 2),
                "deltaE_raw": round(dE_raw, 2),
                "verdict_raw": verdict_raw,
                "norm_L": round(row["norm_high_Lab"][0], 2),
                "norm_a": round(row["norm_high_Lab"][1], 2),
                "norm_b": round(row["norm_high_Lab"][2], 2),
                "deltaE_norm": round(dE_norm, 2),
                "verdict_norm": verdict_norm,
            })

        # Save to CSV
        with open(args.csv_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(output_rows[0].keys()))
            writer.writeheader()
            writer.writerows(output_rows)

        print(f"\nSaved lighting robustness results to: {args.csv_out} ({time.time() - t_start:.2f}s total)", flush=True)

    finally:
        kit.close()


if __name__ == "__main__":
    main()

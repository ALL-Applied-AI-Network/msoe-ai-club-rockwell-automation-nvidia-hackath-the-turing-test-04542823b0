"""Set controllable liquid in the CSI digital twin and render one frame.

One job: hides the twin's pre-recorded animated liquid, creates a clean volumetric
liquid cylinder scaled to the exact physical fill volume (mL) and inner vial radius,
and sets a volumetric absorption material (OmniSurface MDL, Beer-Lambert attenuation)
parameterized by orange share, blue share, and vertical mixing stratification.

Reads:
- Twin stage: /workspace/project/twin/csi_digital_twin_v1/csi_line.usda
- Camera config: /workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json
- Dye strengths: outputs/card7/twin_dye_strengths.json

Writes:
- Rendered PNG image to path specified by --out

Execution:
    /isaac-sim/python.sh scripts/set_liquid.py --orange 0.0 --blue 0.714 --ml 70 --mixing 0.0 --out outputs/card7/test_recipe7_70ml.png
"""

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Optional, Tuple
import cv2
import numpy as np

# Physical constants and geometry (in parent space FillStation_LocalRoot, units = inches)
# Glass inner radius: 13.183 mm (0.51902 in)
# Liquid radius set 0.05 mm smaller to avoid coplanar surface z-fighting: 13.133 mm (0.51705 in)
VIAL_INNER_RADIUS_MM = 13.183
LIQUID_RADIUS_MM = VIAL_INNER_RADIUS_MM - 0.05  # 13.133 mm
LIQUID_RADIUS_IN = LIQUID_RADIUS_MM / 25.4      # ~0.51705 inches
LIQUID_RADIUS_M = LIQUID_RADIUS_MM / 1000.0     # ~0.013133 meters

# Bottom floor of inner vial cavity in FillStation_LocalRoot space (inches)
VIAL_INNER_BOTTOM_Z_IN = 3.33 / 25.4  # ~0.13110 inches

# Height per mL: h = V / (pi * r^2)
# Area = pi * (1.3133 cm)^2 = 5.4187 cm^2
# h_cm = V_ml / 5.4187 => h_in = h_cm / 2.54 => V * 0.072656 inches/mL
INCHES_PER_ML = (1.0 / (math.pi * (LIQUID_RADIUS_MM / 10.0) ** 2)) / 2.54

# Reference transmission thickness = inner diameter in scene units (meters)
REFERENCE_DEPTH_M = 2.0 * LIQUID_RADIUS_M  # ~0.026266 m

DEFAULT_DYE_STRENGTHS_JSON = Path("/workspace/project/repo/outputs/card7/twin_dye_strengths.json")


# Calibrated fill height model: outputs/card7/twin_fill_height.json
DEFAULT_FILL_HEIGHT_JSON = Path("/workspace/project/repo/outputs/card7/twin_fill_height.json")


def compute_fill_height_in(volume_ml: float, fill_height_json: Path = DEFAULT_FILL_HEIGHT_JSON) -> float:
    """Compute liquid column height in inches from mL using calibrated fit."""
    if fill_height_json.is_file():
        try:
            with open(fill_height_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            a = float(data.get("a", 0.065710))
            b = float(data.get("b", 0.518027))
            return a * volume_ml + b
        except Exception:
            pass
    return 0.065710 * volume_ml + 0.518027


def load_dye_strengths(json_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load the 6 fitted dye absorption coefficients (k_orange, k_blue per RGB channel)."""
    if not json_path.is_file():
        # Fallback to defaults from real video 5 anchored gradient fit
        k_orange = np.array([-0.059087, 1.617181, 3.198114], dtype=np.float64)
        k_blue = np.array([3.298431, 0.699553, 0.174334], dtype=np.float64)
        return k_orange, k_blue

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ko = data.get("k_orange", {})
    kb = data.get("k_blue", {})
    k_orange = np.array([ko.get("R", -0.059), ko.get("G", 1.617), ko.get("B", 3.198)], dtype=np.float64)
    k_blue = np.array([kb.get("R", 3.298), kb.get("G", 0.700), kb.get("B", 0.174)], dtype=np.float64)
    return k_orange, k_blue


def compute_transmittance(orange_share: float, blue_share: float, k_orange: np.ndarray, k_blue: np.ndarray) -> np.ndarray:
    """Compute Beer-Lambert transmittance T = 10^(-A) across the vial diameter."""
    A = k_orange * orange_share + k_blue * blue_share
    # Optical transmittance across reference diameter cannot exceed 1.0
    T = np.clip(10.0 ** (-A), 1e-5, 1.0)
    return T


def generate_mixing_gradient_texture(
    orange_share: float,
    blue_share: float,
    mixing: float,
    k_orange: np.ndarray,
    k_blue: np.ndarray,
    texture_path: Path,
) -> Path:
    """Generate a vertical 256x16 gradient texture representing layered concentration.

    Concentration c(v) = 1 + mixing * (1 - 2*v) where v=0 (bottom) is darker and v=1 (top) is lighter.
    """
    texture_path.parent.mkdir(parents=True, exist_ok=True)
    num_rows = 256
    num_cols = 16
    A_avg = k_orange * orange_share + k_blue * blue_share

    # In images, row 0 is top (v=1), row 255 is bottom (v=0)
    v_norm = 1.0 - np.linspace(0.0, 1.0, num_rows, endpoint=True)[:, None]  # (256, 1)
    c_factor = 1.0 + float(mixing) * (1.0 - 2.0 * v_norm)  # (256, 1)
    A_profile = A_avg * c_factor  # (256, 3)

    T_profile = np.clip(10.0 ** (-A_profile), 1e-5, 1.0)
    img_rgb = np.tile(np.clip(T_profile * 255.0, 0, 255).astype(np.uint8)[:, None, :], (1, num_cols, 1))
    img_bgr = img_rgb[..., ::-1]

    if not cv2.imwrite(str(texture_path), img_bgr):
        raise OSError(f"Failed to write mixing texture to: {texture_path}")

    return texture_path


def build_cylinder_geometry(
    stage,
    prim_path,
    radius_in: float,
    z_bottom_in: float,
    z_top_in: float,
    num_segments: int = 64,
):
    """Build a watertight cylinder mesh with outward normals and faceVarying UV coordinates."""
    from pxr import Gf, Sdf, UsdGeom

    mesh = UsdGeom.Mesh.Define(stage, prim_path)

    angles = np.linspace(0.0, 2.0 * math.pi, num_segments, endpoint=False)
    x = radius_in * np.cos(angles)
    y = radius_in * np.sin(angles)

    pts = []
    # Ring 0: bottom vertices
    for i in range(num_segments):
        pts.append(Gf.Vec3f(float(x[i]), float(y[i]), float(z_bottom_in)))
    # Ring 1: top vertices
    for i in range(num_segments):
        pts.append(Gf.Vec3f(float(x[i]), float(y[i]), float(z_top_in)))
    # Centers
    pts.append(Gf.Vec3f(0.0, 0.0, float(z_bottom_in)))  # index 2*num_segments
    pts.append(Gf.Vec3f(0.0, 0.0, float(z_top_in)))     # index 2*num_segments + 1

    bottom_center = 2 * num_segments
    top_center = 2 * num_segments + 1

    face_counts = []
    face_indices = []
    st_values = []

    # 1. Side wall quads (outward facing)
    for i in range(num_segments):
        nxt = (i + 1) % num_segments
        u0 = float(i) / num_segments
        u1 = float(i + 1) / num_segments
        face_counts.append(4)
        face_indices.extend([i, nxt, num_segments + nxt, num_segments + i])
        st_values.extend([
            Gf.Vec2f(u0, 0.0),
            Gf.Vec2f(u1, 0.0),
            Gf.Vec2f(u1, 1.0),
            Gf.Vec2f(u0, 1.0),
        ])

    # 2. Bottom cap (downward facing)
    for i in range(num_segments):
        nxt = (i + 1) % num_segments
        face_counts.append(3)
        face_indices.extend([bottom_center, nxt, i])
        st_values.extend([
            Gf.Vec2f(0.5, 0.0),
            Gf.Vec2f(float(nxt) / num_segments, 0.0),
            Gf.Vec2f(float(i) / num_segments, 0.0),
        ])

    # 3. Top cap (upward facing)
    for i in range(num_segments):
        nxt = (i + 1) % num_segments
        face_counts.append(3)
        face_indices.extend([top_center, num_segments + i, num_segments + nxt])
        st_values.extend([
            Gf.Vec2f(0.5, 1.0),
            Gf.Vec2f(float(i) / num_segments, 1.0),
            Gf.Vec2f(float(nxt) / num_segments, 1.0),
        ])

    mesh.GetPointsAttr().Set(pts)
    mesh.GetFaceVertexCountsAttr().Set(face_counts)
    mesh.GetFaceVertexIndicesAttr().Set(face_indices)
    mesh.GetSubdivisionSchemeAttr().Set("none")
    mesh.GetDoubleSidedAttr().Set(False)

    primvars = UsdGeom.PrimvarsAPI(mesh)
    st_primvar = primvars.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
    st_primvar.Set(st_values)

    return mesh


def configure_liquid_material(
    stage,
    mat_path,
    transmittance: np.ndarray,
    mixing: float,
    texture_path: Optional[Path] = None,
):
    """Configure OmniSurface MDL material with volumetric transmission and Beer-Lambert absorption."""
    from pxr import Gf, Sdf, UsdShade

    mat = UsdShade.Material.Define(stage, mat_path)
    shader_path = mat_path.AppendChild("Shader")
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.SetSourceAsset("OmniSurface.mdl", "mdl")
    shader.SetSourceAssetSubIdentifier("OmniSurface", "mdl")

    # Pure transmission, no surface diffuse reflection
    shader.CreateInput("enable_specular_transmission", Sdf.ValueTypeNames.Bool).Set(True)
    shader.CreateInput("specular_transmission_weight", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("specular_transmission_scattering_depth", Sdf.ValueTypeNames.Float).Set(float(REFERENCE_DEPTH_M))
    shader.CreateInput("specular_transmission_scattering_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.0, 0.0, 0.0))
    shader.CreateInput("diffuse_reflection_weight", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("specular_reflection_weight", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("thin_walled", Sdf.ValueTypeNames.Bool).Set(False)

    # Water IOR
    shader.CreateInput("specular_reflection_ior", Sdf.ValueTypeNames.Float).Set(1.333)

    if mixing > 0.0 and texture_path is not None and texture_path.is_file():
        # Stratified / layered absorption via texture lookup
        shader.CreateInput("specular_transmission_color_image", Sdf.ValueTypeNames.Asset).Set(str(texture_path.resolve()))
    else:
        # Uniform volumetric absorption: ensure any prior texture input is removed
        if shader.GetPrim().HasProperty("inputs:specular_transmission_color_image"):
            shader.GetPrim().RemoveProperty("inputs:specular_transmission_color_image")
        col = Gf.Vec3f(float(transmittance[0]), float(transmittance[1]), float(transmittance[2]))
        shader.CreateInput("specular_transmission_color", Sdf.ValueTypeNames.Color3f).Set(col)

    mat.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "surface")
    mat.CreateVolumeOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "volume")

    return mat


def set_liquid_and_render_frame(
    stage,
    kit,
    tl,
    rep,
    rgb_annotator,
    time_codes_per_sec: float,
    orange_share: float,
    blue_share: float,
    volume_ml: float,
    mixing: float,
    out_png_path: Path,
    k_orange: np.ndarray,
    k_blue: np.ndarray,
    frame_num: int = 686,
    subframes: int = 32,
) -> Path:
    """Set liquid geometry and material on open stage, advance to frame, render, and save PNG."""
    from pxr import Sdf, UsdGeom, UsdShade

    out_png_path = Path(out_png_path).resolve()
    out_png_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Hide the twin's animated liquid mesh
    old_prim_path = Sdf.Path("/CSI_Line/FillStation/FillStation_LocalRoot/Fill_liquid/Fill_liquid")
    old_prim = stage.GetPrimAtPath(old_prim_path)
    if old_prim.IsValid():
        UsdGeom.Imageable(old_prim).MakeInvisible()

    # 2. Compute calibrated fill height from volume
    volume_ml = max(10.0, min(80.0, float(volume_ml)))
    h_in = compute_fill_height_in(volume_ml)
    z_bottom_in = VIAL_INNER_BOTTOM_Z_IN
    z_top_in = z_bottom_in + h_in

    # 3. Create or update smooth cylinder geometry
    cyl_prim_path = Sdf.Path("/CSI_Line/FillStation/FillStation_LocalRoot/Custom_Liquid")
    mesh = build_cylinder_geometry(
        stage, cyl_prim_path, LIQUID_RADIUS_IN, z_bottom_in, z_top_in, num_segments=64
    )

    # 4. Compute transmittance and material
    T = compute_transmittance(orange_share, blue_share, k_orange, k_blue)
    texture_path = None
    if mixing > 0.0:
        grad_png = out_png_path.parent / f"{out_png_path.stem}_gradient.png"
        texture_path = generate_mixing_gradient_texture(
            orange_share, blue_share, mixing, k_orange, k_blue, grad_png
        )

    mat_prim_path = Sdf.Path(f"/CSI_Line/FillStation/FillStation_LocalRoot/Mat_{out_png_path.stem}")
    mat = configure_liquid_material(stage, mat_prim_path, T, mixing, texture_path)
    UsdShade.MaterialBindingAPI(mesh).Bind(mat)

    # 5. Position timeline and render
    target_time = frame_num / time_codes_per_sec
    tl.set_current_time(target_time)
    kit.update()

    for _ in range(2):
        rep.orchestrator.step(rt_subframes=subframes, delta_time=0.0)

    data = np.asarray(rgb_annotator.get_data())
    img_bgr = data[..., :3][..., ::-1].copy()

    if not cv2.imwrite(str(out_png_path), img_bgr):
        raise OSError(f"Failed to write rendered frame to: {out_png_path}")

    print(f"Rendered: V={volume_ml:.1f}mL, orange={orange_share:.3f}, blue={blue_share:.3f}, mix={mixing:.1f} -> {out_png_path}", flush=True)
    return out_png_path


def main():
    parser = argparse.ArgumentParser(description="Set liquid in twin and render one frame.")
    parser.add_argument("--orange", type=float, default=0.0, help="Orange dye share [0..1]")
    parser.add_argument("--blue", type=float, default=0.714, help="Blue dye share [0..1]")
    parser.add_argument("--ml", type=float, default=70.0, help="Liquid volume in mL [10..80]")
    parser.add_argument("--mixing", type=float, default=0.0, help="Mixing state [0=mixed, 1=layered]")
    parser.add_argument("--out", type=str, default="/workspace/project/renders/test_liquid.png", help="Output PNG path")
    parser.add_argument("--subframes", type=int, default=32, help="Path tracing subframes per step")
    parser.add_argument("--frame", type=int, default=686, help="Timeline frame number")
    parser.add_argument("--dye-strengths", type=Path, default=DEFAULT_DYE_STRENGTHS_JSON, help="Path to twin_dye_strengths.json")
    parser.add_argument("--stage", default="/workspace/project/twin/csi_digital_twin_v1/csi_line.usda", help="USD stage file")
    parser.add_argument("--camera-config", default="/workspace/project/twin/csi_digital_twin_v1/cameras/FillCam.json", help="Camera config JSON")
    args = parser.parse_args()

    k_orange, k_blue = load_dye_strengths(args.dye_strengths)

    with open(args.camera_config, "r", encoding="utf-8") as f:
        cam_meta = json.load(f)

    rw, rh = cam_meta.get("render_px", [640, 480])
    fps = cam_meta.get("fps", 30)

    print(f"Initializing SimulationApp ({rw}x{rh}, PathTracing)...", flush=True)
    from isaacsim import SimulationApp

    kit = SimulationApp({"headless": True, "renderer": "PathTracing", "width": rw, "height": rh})

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
            raise RuntimeError("Camera prim not found in stage.")

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

        set_liquid_and_render_frame(
            stage=stage,
            kit=kit,
            tl=tl,
            rep=rep,
            rgb_annotator=rgb_annotator,
            time_codes_per_sec=time_codes_per_sec,
            orange_share=args.orange,
            blue_share=args.blue,
            volume_ml=args.ml,
            mixing=args.mixing,
            out_png_path=Path(args.out),
            k_orange=k_orange,
            k_blue=k_blue,
            frame_num=args.frame,
            subframes=args.subframes,
        )

    finally:
        kit.close()


if __name__ == "__main__":
    main()

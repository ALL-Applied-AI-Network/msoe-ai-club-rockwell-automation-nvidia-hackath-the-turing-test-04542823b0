"""Measure vial and blank patches in a single camera frame or twin render.

One job: measures the median color of HIGH, LOW, BLANK_HIGH, and BLANK_LOW patches,
and computes both raw Lab and blank-normalized Lab colors using the run's median blank.
Runs with /isaac-sim/python.sh on Brev and standard Python on laptop.

Reads:
- Input image (real vial frame or twin render, 640x480 BGR)

Writes:
- Annotated visualization image with patch boxes (optional, e.g. /workspace/project/renders/card7_step2_patches.png)
- Color metrics (raw Lab and blank-normalized Lab) to stdout or as a dictionary

Execution:
    /isaac-sim/python.sh scripts/measure_patches.py --image /workspace/project/renders/card7_step1_more_samples.png --draw-out /workspace/project/renders/card7_step2_patches.png
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple, Union
import cv2
import numpy as np

# Try importing colour-science; fall back to exact standard formulas if missing
try:
    import colour

    HAS_COLOUR = True
except ImportError:
    HAS_COLOUR = False

# Default patch coordinates in 640x480 frame (x_min, x_max, y_min, y_max)
PATCHES = {
    "HIGH": {"x_min": 302, "x_max": 318, "y_min": 268, "y_max": 288, "color": (0, 255, 0)},       # Green
    "LOW": {"x_min": 302, "x_max": 318, "y_min": 352, "y_max": 372, "color": (255, 0, 0)},       # Blue
    "BLANK_HIGH": {"x_min": 410, "x_max": 426, "y_min": 268, "y_max": 288, "color": (0, 255, 255)}, # Yellow
    "BLANK_LOW": {"x_min": 410, "x_max": 426, "y_min": 352, "y_max": 372, "color": (255, 255, 0)}, # Cyan
}

# Run median blank linear RGB (derived from 27 valid glass frames in video 5, scripts/blank_check.py)
DEFAULT_MEDIAN_BLANK_HIGH_LIN = np.array([0.17144110073282259, 0.19120168274079138, 0.17464740365558504])
DEFAULT_MEDIAN_BLANK_LOW_LIN = np.array([0.020288563056652397, 0.021219010376003555, 0.015208514422912708])


def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """Convert sRGB in [0, 1] to linear RGB."""
    if HAS_COLOUR:
        return colour.models.eotf_sRGB(srgb)
    srgb = np.asarray(srgb, dtype=np.float64)
    return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    """Convert linear RGB in [0, 1] to sRGB."""
    lin = np.clip(lin, 0.0, 1.0)
    if HAS_COLOUR:
        return colour.models.eotf_inverse_sRGB(lin)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * (lin ** (1.0 / 2.4)) - 0.055)


def srgb_to_lab(srgb: np.ndarray) -> np.ndarray:
    """Convert sRGB in [0, 1] to CIELAB (D65)."""
    if HAS_COLOUR:
        xyz = colour.sRGB_to_XYZ(srgb)
        return colour.XYZ_to_Lab(xyz)
    lin = srgb_to_linear(srgb)
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = lin @ M.T
    d65 = np.array([0.95047, 1.00000, 1.08883])
    r = xyz / d65
    delta = 6.0 / 29.0
    f = np.where(r > delta**3, r ** (1.0 / 3.0), (r / (3.0 * delta**2)) + (4.0 / 29.0))
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def linear_to_lab(lin: np.ndarray) -> np.ndarray:
    """Convert linear RGB to CIELAB."""
    srgb = linear_to_srgb(lin)
    return srgb_to_lab(srgb)


def measure_patch(frame: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract median sRGB [0..1], linear RGB [0..1], and Lab for a bounding box."""
    crop_bgr = frame[y_min:y_max, x_min:x_max]
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(crop_rgb, axis=(0, 1)) / 255.0
    lin_rgb = srgb_to_linear(med_srgb)
    lab = srgb_to_lab(med_srgb)
    return med_srgb, lin_rgb, lab


def measure_image(
    image_or_path: Union[str, Path, np.ndarray],
    draw_output_path: Optional[Union[str, Path]] = None,
    med_blank_h_lin: np.ndarray = DEFAULT_MEDIAN_BLANK_HIGH_LIN,
    med_blank_l_lin: np.ndarray = DEFAULT_MEDIAN_BLANK_LOW_LIN,
    neighbour_present: bool = True,
) -> Dict[str, Any]:
    """Measure raw and blank-normalized colors for HIGH, LOW, BLANK_HIGH, and BLANK_LOW patches.

    When neighbour_present is False, uses run median blank as fallback (lin_blank = med_blank).
    Returns dictionary with all metrics and optionally saves annotated image.
    """
    if isinstance(image_or_path, (str, Path)):
        img_path = Path(image_or_path).resolve()
        if not img_path.is_file():
            raise FileNotFoundError(f"Image file not found: {img_path}")
        frame = cv2.imread(str(img_path))
        if frame is None:
            raise RuntimeError(f"Could not load image: {img_path}")
    else:
        frame = image_or_path

    results: Dict[str, Any] = {"patches": {}, "neighbour_present": neighbour_present}

    # Measure each of the 4 patches
    for patch_name, coords in PATCHES.items():
        srgb, lin, lab = measure_patch(
            frame, coords["x_min"], coords["x_max"], coords["y_min"], coords["y_max"]
        )
        results["patches"][patch_name] = {
            "coords": {
                "x_min": coords["x_min"],
                "x_max": coords["x_max"],
                "y_min": coords["y_min"],
                "y_max": coords["y_max"],
            },
            "sRGB_255": [round(float(v * 255.0), 1) for v in srgb],
            "linear_RGB": [round(float(v), 5) for v in lin],
            "Lab": [round(float(v), 2) for v in lab],
        }

    # Transmittance T = linear RGB(vial) / linear RGB(blank)
    lin_vh = np.array(results["patches"]["HIGH"]["linear_RGB"])
    lin_vl = np.array(results["patches"]["LOW"]["linear_RGB"])

    if neighbour_present:
        lin_bh = np.array(results["patches"]["BLANK_HIGH"]["linear_RGB"])
        lin_bl = np.array(results["patches"]["BLANK_LOW"]["linear_RGB"])
    else:
        # Fallback to run median blank when neighbour is absent
        lin_bh = med_blank_h_lin
        lin_bl = med_blank_l_lin

    t_high = lin_vh / np.maximum(lin_bh, 1e-6)
    t_low = lin_vl / np.maximum(lin_bl, 1e-6)

    # Blank-normalized linear RGB = T * run_median_blank
    norm_lin_h = t_high * med_blank_h_lin
    norm_lin_l = t_low * med_blank_l_lin

    norm_lab_h = linear_to_lab(norm_lin_h)
    norm_lab_l = linear_to_lab(norm_lin_l)

    results["transmittance"] = {
        "HIGH": [round(float(v), 5) for v in t_high],
        "LOW": [round(float(v), 5) for v in t_low],
    }

    results["normalized"] = {
        "HIGH": {
            "linear_RGB": [round(float(v), 5) for v in norm_lin_h],
            "Lab": [round(float(v), 2) for v in norm_lab_h],
        },
        "LOW": {
            "linear_RGB": [round(float(v), 5) for v in norm_lin_l],
            "Lab": [round(float(v), 2) for v in norm_lab_l],
        },
    }

    # Optional drawing
    if draw_output_path is not None:
        draw_path = Path(draw_output_path).resolve()
        draw_path.parent.mkdir(parents=True, exist_ok=True)
        annotated = frame.copy()

        for patch_name, coords in PATCHES.items():
            pt1 = (coords["x_min"], coords["y_min"])
            pt2 = (coords["x_max"], coords["y_max"])
            col = coords["color"]
            cv2.rectangle(annotated, pt1, pt2, col, 1)

            # Text label
            label = patch_name
            text_pos = (coords["x_min"] - 10, coords["y_min"] - 5 if coords["y_min"] > 20 else coords["y_max"] + 15)
            cv2.putText(annotated, label, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)

        if not cv2.imwrite(str(draw_path), annotated):
            raise OSError(f"Failed to write annotated image to: {draw_path}")
        results["drawn_image"] = str(draw_path)

    return results


def main():
    parser = argparse.ArgumentParser(description="Measure vial patches in a single camera frame or twin render.")
    parser.add_argument(
        "--image",
        default="/workspace/project/renders/card7_step1_more_samples.png",
        help="Path to input image",
    )
    parser.add_argument(
        "--draw-out",
        default="/workspace/project/renders/card7_step2_patches.png",
        help="Path to save image with drawn patch boxes",
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    results = measure_image(args.image, draw_output_path=args.draw_out)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print("=" * 65)
    print("CARD 7 STEP 2: PATCH COLOR MEASUREMENT")
    print(f"Input image: {args.image}")
    if args.draw_out:
        print(f"Annotated output: {args.draw_out}")
    print("=" * 65)

    print("\n1. RAW MEASUREMENTS (Patch Median):")
    for name in ["HIGH", "LOW", "BLANK_HIGH", "BLANK_LOW"]:
        p = results["patches"][name]
        c = p["coords"]
        print(f"  {name:11s} (x {c['x_min']}-{c['x_max']}, y {c['y_min']}-{c['y_max']}):")
        print(f"    sRGB: {p['sRGB_255']}")
        print(f"    lin:  {p['linear_RGB']}")
        print(f"    Lab:  L*={p['Lab'][0]:.2f}, a*={p['Lab'][1]:+.2f}, b*={p['Lab'][2]:+.2f}")

    print("\n2. OPTICAL TRANSMITTANCE (T = lin_vial / lin_blank):")
    print(f"  HIGH: R={results['transmittance']['HIGH'][0]:.4f}, G={results['transmittance']['HIGH'][1]:.4f}, B={results['transmittance']['HIGH'][2]:.4f}")
    print(f"  LOW:  R={results['transmittance']['LOW'][0]:.4f}, G={results['transmittance']['LOW'][1]:.4f}, B={results['transmittance']['LOW'][2]:.4f}")

    print("\n3. BLANK-NORMALIZED COLORS (T * Run Median Blank -> Lab):")
    nh = results["normalized"]["HIGH"]
    nl = results["normalized"]["LOW"]
    print(f"  HIGH: Lab: L*={nh['Lab'][0]:.2f}, a*={nh['Lab'][1]:+.2f}, b*={nh['Lab'][2]:+.2f} (lin: {nh['linear_RGB']})")
    print(f"  LOW:  Lab: L*={nl['Lab'][0]:.2f}, a*={nl['Lab'][1]:+.2f}, b*={nl['Lab'][2]:+.2f} (lin: {nl['linear_RGB']})")
    print("=" * 65)


if __name__ == "__main__":
    main()

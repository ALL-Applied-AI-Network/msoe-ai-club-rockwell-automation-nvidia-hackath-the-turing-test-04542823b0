"""
scripts/vial_check.py
Card 10, Step 1: Reusable one-vial color check function and CLI verification.

Checks a single filled vial against its recipe's clean 3rd-vial reference.
Uses HIGH patch (meniscus >= 60 mL, y in [268, 288]) with "normal" confidence,
or LOW patch (y in [352, 372]) with "low" confidence for short vials (< 60 mL).

Fixed thresholds:
- pass:   dE < 2.0
- unsure: 2.0 <= dE <= 5.0
- fail:   dE > 5.0

Reads:
- annotations/video5_vial_times_corrected.csv
- data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4
- outputs/card3/baseline_results.csv (for --all verification)

CLI:
- python scripts/vial_check.py --vial 7
- python scripts/vial_check.py --all
"""

import argparse
from pathlib import Path
import sys
import colour
import cv2
import numpy as np
import pandas as pd

# Portable encoding support for stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Fixed patch coordinates from scripts/crop_vial.py and baseline_check.py
LOW_PATCH = {
    "x_min": 302,
    "x_max": 318,
    "y_min": 352,
    "y_max": 372,
    "name": "LOW",
}

HIGH_PATCH = {
    "x_min": 302,
    "x_max": 318,
    "y_min": 268,
    "y_max": 288,
    "name": "HIGH",
}

DEFAULT_TIMES_CSV = Path("annotations/video5_vial_times_corrected.csv")
DEFAULT_VIDEO_MP4 = Path("data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4")
DEFAULT_BASELINE_CSV = Path("outputs/card3/baseline_results.csv")


def extract_patch_lab(frame: np.ndarray, patch_def: dict) -> np.ndarray:
    """Computes median sRGB of patch and converts to CIELAB (D65)."""
    crop_bgr = frame[
        patch_def["y_min"] : patch_def["y_max"],
        patch_def["x_min"] : patch_def["x_max"],
    ]
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(crop_rgb, axis=(0, 1)) / 255.0
    xyz = colour.sRGB_to_XYZ(med_srgb)
    lab = colour.XYZ_to_Lab(xyz)
    return lab


def load_references(
    times_csv: Path = DEFAULT_TIMES_CSV,
    video_mp4: Path = DEFAULT_VIDEO_MP4,
) -> dict:
    """
    Builds clean reference Lab colors from the 3rd vial of each recipe.
    Returns:
        dict: recipe_id -> {"LOW": lab_low, "HIGH": lab_high_or_None, "reference_vial": vial_num}
    """
    df_times = pd.read_csv(times_csv).set_index("vial")
    cap = cv2.VideoCapture(str(video_mp4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_mp4}")

    references = {}
    # 3rd vial of each recipe batch in Video 5 (recipes 5 to 14)
    ref_vials = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30]

    for v in ref_vials:
        if v not in df_times.index:
            continue
        row = df_times.loc[v]
        f = int(row["last_parked_frame"])
        rec_id = int(row["recipe_id"])
        tot_ml = int(row["total_ml"])

        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Could not read frame {f} for reference vial {v}")

        lab_low = extract_patch_lab(frame, LOW_PATCH)
        lab_high = extract_patch_lab(frame, HIGH_PATCH) if tot_ml >= 60 else None

        references[rec_id] = {
            "LOW": lab_low,
            "HIGH": lab_high,
            "reference_vial": v,
        }

    cap.release()
    return references


def check_vial(
    frame: np.ndarray,
    recipe_id: int,
    total_ml: int,
    references: dict,
    is_reference: bool = False,
) -> dict:
    """
    Checks one vial against its recipe's clean reference color.

    Parameters:
        frame: BGR image of the vial parked under the camera
        recipe_id: Target recipe ID (5 to 14)
        total_ml: Total liquid volume in mL
        references: Reference dict from load_references()
        is_reference: True if this vial is itself the clean 3rd reference vial

    Returns:
        dict with:
            patch (str): "HIGH" or "LOW"
            measured_lab (np.ndarray): [L, a, b]
            reference_lab (np.ndarray): [L, a, b]
            delta_e (float): CIELAB dE2000 distance
            verdict (str): "pass" (dE < 2), "unsure" (2 <= dE <= 5), or "fail" (dE > 5)
            confidence (str): "normal" (HIGH patch) or "low" (LOW patch)
            is_reference (bool): Whether this is the reference vial
    """
    if recipe_id not in references:
        raise KeyError(f"Recipe {recipe_id} not found in references.")

    patch_name = "HIGH" if total_ml >= 60 else "LOW"
    confidence = "normal" if total_ml >= 60 else "low"
    patch_def = HIGH_PATCH if patch_name == "HIGH" else LOW_PATCH

    measured_lab = extract_patch_lab(frame, patch_def)
    ref_lab = references[recipe_id][patch_name]

    if is_reference:
        delta_e = 0.0
    else:
        delta_e = float(colour.delta_E(measured_lab, ref_lab, method="CIE 2000"))

    if delta_e < 2.0:
        verdict = "pass"
    elif delta_e <= 5.0:
        verdict = "unsure"
    else:
        verdict = "fail"

    return {
        "patch": patch_name,
        "measured_lab": measured_lab,
        "reference_lab": ref_lab,
        "delta_e": delta_e,
        "verdict": verdict,
        "confidence": confidence,
        "is_reference": is_reference,
    }


def run_single_vial(vial_num: int):
    """CLI helper to check a single vial."""
    print("Loading references from 3rd vials...")
    refs = load_references()

    df_times = pd.read_csv(DEFAULT_TIMES_CSV).set_index("vial")
    if vial_num not in df_times.index:
        raise ValueError(f"Vial {vial_num} not found in {DEFAULT_TIMES_CSV}")

    row = df_times.loc[vial_num]
    f = int(row["last_parked_frame"])
    rec_id = int(row["recipe_id"])
    tot_ml = int(row["total_ml"])
    is_ref = (vial_num % 3 == 0)

    cap = cv2.VideoCapture(str(DEFAULT_VIDEO_MP4))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise RuntimeError(f"Could not read frame {f} for vial {vial_num}")

    res = check_vial(frame, rec_id, tot_ml, refs, is_reference=is_ref)

    ref_vial = refs[rec_id]["reference_vial"]
    print("=" * 60)
    print(f"VIAL CHECK: Vial {vial_num} (Recipe {rec_id}, {tot_ml} mL)")
    print("=" * 60)
    print(f"Reference Vial  : Vial {ref_vial} (Recipe {rec_id} 3rd vial)")
    print(f"Patch Used      : {res['patch']} ({res['confidence']} confidence)")
    print(f"Measured Lab    : L={res['measured_lab'][0]:.2f}, a={res['measured_lab'][1]:.2f}, b={res['measured_lab'][2]:.2f}")
    print(f"Reference Lab   : L={res['reference_lab'][0]:.2f}, a={res['reference_lab'][1]:.2f}, b={res['reference_lab'][2]:.2f}")
    print(f"dE2000 Distance : {res['delta_e']:.4f}")
    if res["is_reference"]:
        print(f"Verdict         : {res['verdict'].upper()} (reference vial)")
    else:
        threshold_rule = "dE < 2" if res["verdict"] == "pass" else ("2 <= dE <= 5" if res["verdict"] == "unsure" else "dE > 5")
        print(f"Verdict         : {res['verdict'].upper()} ({threshold_rule})")
    print("=" * 60)


def run_all_vials():
    """CLI helper to check all 30 vials and benchmark against baseline_results.csv."""
    print("Loading references from 3rd vials...")
    refs = load_references()

    df_times = pd.read_csv(DEFAULT_TIMES_CSV).set_index("vial")
    if not DEFAULT_BASELINE_CSV.exists():
        raise FileNotFoundError(f"Missing {DEFAULT_BASELINE_CSV}. Run scripts/baseline_check.py first.")
    df_base = pd.read_csv(DEFAULT_BASELINE_CSV).set_index("vial")

    cap = cv2.VideoCapture(str(DEFAULT_VIDEO_MP4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {DEFAULT_VIDEO_MP4}")

    print("\n" + "=" * 95)
    print(f"{'Vial':<5} {'Rec':<4} {'Vol':<5} {'Patch':<6} {'Conf':<7} {'Meas dE':<9} {'Base dE':<9} {'Diff':<8} {'Verdict':<10} {'Notes'}")
    print("=" * 95)

    max_diff = 0.0
    all_matched = True

    for v in range(1, 31):
        row = df_times.loc[v]
        f = int(row["last_parked_frame"])
        rec_id = int(row["recipe_id"])
        tot_ml = int(row["total_ml"])
        is_ref = (v % 3 == 0)

        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Could not read frame {f} for vial {v}")

        res = check_vial(frame, rec_id, tot_ml, refs, is_reference=is_ref)

        patch = res["patch"]
        meas_de = res["delta_e"]
        expected_de = float(df_base.loc[v, "delta_e_high"] if patch == "HIGH" else df_base.loc[v, "delta_e_low"])
        diff = abs(meas_de - expected_de)

        if diff > max_diff:
            max_diff = diff
        if diff >= 0.01:
            all_matched = False

        notes = "reference vial" if is_ref else ""
        print(
            f"{v:<5d} {rec_id:<4d} {tot_ml:<5d} {patch:<6} {res['confidence']:<7} "
            f"{meas_de:<9.4f} {expected_de:<9.4f} {diff:<8.4f} {res['verdict']:<10} {notes}"
        )

    cap.release()
    print("=" * 95)
    print(f"Max difference from baseline_results.csv: {max_diff:.6f} dE")
    if all_matched:
        print("Verification PASSED: All 30 vials match baseline_results.csv within 0.01 dE!")
    else:
        print("Verification FAILED: One or more vials deviate by >= 0.01 dE.")


def main():
    parser = argparse.ArgumentParser(description="Check one vial or all 30 vials against clean recipe references.")
    parser.add_argument("--vial", type=int, default=None, help="Check a specific vial number (1 to 30)")
    parser.add_argument("--all", action="store_true", help="Check all 30 vials and compare with baseline_results.csv")
    args = parser.parse_args()

    if args.vial is not None:
        run_single_vial(args.vial)
    elif args.all:
        run_all_vials()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

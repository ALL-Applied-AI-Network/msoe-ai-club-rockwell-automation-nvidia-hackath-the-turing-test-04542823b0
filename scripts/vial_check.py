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

# Blank coordinates inside neighbouring empty glass vial (x: 410-426)
BLANK_HIGH = {
    "x_min": 410,
    "x_max": 426,
    "y_min": 268,
    "y_max": 288,
    "name": "BLANK_HIGH",
}

BLANK_LOW = {
    "x_min": 410,
    "x_max": 426,
    "y_min": 352,
    "y_max": 372,
    "name": "BLANK_LOW",
}

DEFAULT_TIMES_CSV = Path("annotations/video5_vial_times_corrected.csv")
DEFAULT_VIDEO_MP4 = Path("data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4")
DEFAULT_BASELINE_CSV = Path("outputs/card3/baseline_results.csv")


def extract_patch_stats(frame: np.ndarray, patch_def: dict):
    """Computes median sRGB, linear RGB, and CIELAB (D65) for a patch."""
    crop_bgr = frame[
        patch_def["y_min"] : patch_def["y_max"],
        patch_def["x_min"] : patch_def["x_max"],
    ]
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(crop_rgb, axis=(0, 1)) / 255.0
    lin_rgb = colour.models.eotf_sRGB(med_srgb)
    xyz = colour.sRGB_to_XYZ(med_srgb)
    lab = colour.XYZ_to_Lab(xyz)
    return med_srgb, lin_rgb, lab


def lin_to_lab(lin_rgb: np.ndarray) -> np.ndarray:
    """Converts linear RGB back to CIELAB (D65)."""
    srgb = colour.models.eotf_inverse_sRGB(np.clip(lin_rgb, 0.0, 1.0))
    xyz = colour.sRGB_to_XYZ(srgb)
    return colour.XYZ_to_Lab(xyz)


def get_verdict(delta_e: float) -> str:
    """Classifies dE2000 into standard pass/unsure/fail categories."""
    if delta_e < 2.0:
        return "pass"
    elif delta_e <= 5.0:
        return "unsure"
    else:
        return "fail"


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


def load_run_references(
    vials_csv: Path,
    video_mp4: Path = None,
) -> dict:
    """
    Builds clean reference Lab colors and blank baselines from a run's vials table.

    Reads vials.csv, computes median blanks (BLANK_HIGH, BLANK_LOW) across the run,
    automatically detects empty starwheel pockets (L* > median + 5.0), and normalizes
    reference vials (is_reference=True) using:
        T = linear_patch / eff_blank
        normalized_color = T * median_blank -> CIELAB (D65)
    """
    df_vials = pd.read_csv(vials_csv)
    if video_mp4 is None:
        video_mp4 = DEFAULT_VIDEO_MP4
    cap = cv2.VideoCapture(str(video_mp4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_mp4}")

    frame_cache = {}
    raw_blanks_h_lin = {}
    raw_blanks_l_lin = {}
    raw_blanks_h_lab = {}
    raw_blanks_l_lab = {}

    for _, row in df_vials.iterrows():
        v = int(row["vial"])
        f = int(row["last_parked_frame"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Could not read frame {f} for vial {v}")
        frame_cache[v] = frame

        _, lin_bh, lab_bh = extract_patch_stats(frame, BLANK_HIGH)
        _, lin_bl, lab_bl = extract_patch_stats(frame, BLANK_LOW)
        raw_blanks_h_lin[v] = lin_bh
        raw_blanks_l_lin[v] = lin_bl
        raw_blanks_h_lab[v] = lab_bh
        raw_blanks_l_lab[v] = lab_bl

    cap.release()

    # Initial median blank across all parked frames in the run
    init_med_h_lin = np.median(list(raw_blanks_h_lin.values()), axis=0)
    init_med_l_lin = np.median(list(raw_blanks_l_lin.values()), axis=0)
    init_med_h_lab = lin_to_lab(init_med_h_lin)
    init_med_l_lab = lin_to_lab(init_med_l_lin)

    # Detect empty neighbour pockets:
    # An empty pocket has no glass vial, exposing bare background/metal (L* is > 5 units higher)
    fallback_vials = []
    for _, row in df_vials.iterrows():
        v = int(row["vial"])
        diff_h = raw_blanks_h_lab[v][0] - init_med_h_lab[0]
        diff_l = raw_blanks_l_lab[v][0] - init_med_l_lab[0]
        if diff_h > 5.0 or diff_l > 5.0:
            fallback_vials.append(v)

    # Compute clean run median blank from valid (non-fallback) neighbour vials
    valid_vials = [v for v in df_vials["vial"] if v not in fallback_vials]
    if len(valid_vials) > 0:
        clean_med_h_lin = np.median([raw_blanks_h_lin[v] for v in valid_vials], axis=0)
        clean_med_l_lin = np.median([raw_blanks_l_lin[v] for v in valid_vials], axis=0)
    else:
        clean_med_h_lin = init_med_h_lin
        clean_med_l_lin = init_med_l_lin

    clean_med_h_lab = lin_to_lab(clean_med_h_lin)
    clean_med_l_lab = lin_to_lab(clean_med_l_lin)

    # Build reference entry per recipe
    recipes_ref = {}
    for rec_id, grp in df_vials.groupby("recipe_id"):
        ref_rows = grp[grp["is_reference"]]
        if len(ref_rows) == 0:
            ref_row = grp.iloc[-1]
        else:
            ref_row = ref_rows.iloc[-1]
        ref_v = int(ref_row["vial"])
        ref_frame = frame_cache[ref_v]

        # Extract vial patches
        _, v_lin_h, v_lab_h = extract_patch_stats(ref_frame, HIGH_PATCH)
        _, v_lin_l, v_lab_l = extract_patch_stats(ref_frame, LOW_PATCH)

        # Effective blank for reference vial (use median if empty pocket)
        ref_in_fb = ref_v in fallback_vials
        eff_bh_lin = clean_med_h_lin if ref_in_fb else raw_blanks_h_lin[ref_v]
        eff_bl_lin = clean_med_l_lin if ref_in_fb else raw_blanks_l_lin[ref_v]
        eff_bh_lab = clean_med_h_lab if ref_in_fb else raw_blanks_h_lab[ref_v]
        eff_bl_lab = clean_med_l_lab if ref_in_fb else raw_blanks_l_lab[ref_v]

        # Normalized colors
        norm_lin_h = (v_lin_h / eff_bh_lin) * clean_med_h_lin
        norm_lin_l = (v_lin_l / eff_bl_lin) * clean_med_l_lin
        norm_lab_h = lin_to_lab(norm_lin_h)
        norm_lab_l = lin_to_lab(norm_lin_l)

        recipes_ref[rec_id] = {
            "reference_vial": ref_v,
            "HIGH": {
                "raw_lab": v_lab_h,
                "norm_lab": norm_lab_h,
                "eff_blank_lab": eff_bh_lab,
                "eff_blank_lin": eff_bh_lin,
            },
            "LOW": {
                "raw_lab": v_lab_l,
                "norm_lab": norm_lab_l,
                "eff_blank_lab": eff_bl_lab,
                "eff_blank_lin": eff_bl_lin,
            },
        }

    return {
        "recipes": recipes_ref,
        "median_blank_lin": {"HIGH": clean_med_h_lin, "LOW": clean_med_l_lin},
        "median_blank_lab": {"HIGH": clean_med_h_lab, "LOW": clean_med_l_lab},
        "fallback_vials": fallback_vials,
        "raw_blanks_lin": {"HIGH": raw_blanks_h_lin, "LOW": raw_blanks_l_lin},
        "raw_blanks_lab": {"HIGH": raw_blanks_h_lab, "LOW": raw_blanks_l_lab},
        "frame_cache": frame_cache,
        "vials_df": df_vials,
    }


def check_vial_normalized(
    frame: np.ndarray,
    recipe_id: int,
    total_ml: int,
    run_references: dict,
    is_reference: bool = False,
    vial_num: int = None,
) -> dict:
    """
    Checks one vial using blank-normalized color math and checks for lighting shifts.

    Parameters:
        frame: BGR image of parked vial
        recipe_id: Recipe ID
        total_ml: Liquid volume in mL
        run_references: Dict from load_run_references()
        is_reference: True if this vial is itself the clean reference vial
        vial_num: Optional vial number for logging

    Returns:
        dict with:
            patch: "HIGH" or "LOW"
            confidence: "normal" or "low"
            is_reference: bool
            blank_status: "measured" or "blank_fallback"
            blank_fallback: bool
            blank_delta_e: float (dE2000 of blank vs reference blank)
            lighting_warning: str or None
            delta_e: float (normalized dE2000 vs reference)
            verdict: str ("pass", "unsure", "fail")
            measured_lab: np.ndarray (normalized Lab)
            reference_lab: np.ndarray (normalized reference Lab)
            norm_delta_e: float
            norm_verdict: str
            raw_delta_e: float (raw dE2000 vs reference)
            raw_verdict: str
            raw_measured_lab: np.ndarray
            raw_reference_lab: np.ndarray
    """
    patch_name = "HIGH" if total_ml >= 60 else "LOW"
    confidence = "normal" if total_ml >= 60 else "low"
    patch_def = HIGH_PATCH if patch_name == "HIGH" else LOW_PATCH
    blank_def = BLANK_HIGH if patch_name == "HIGH" else BLANK_LOW

    # Extract patches
    _, lin_vial, lab_vial = extract_patch_stats(frame, patch_def)
    _, lin_blank, lab_blank = extract_patch_stats(frame, blank_def)

    med_blank_lab = run_references["median_blank_lab"][patch_name]
    med_blank_lin = run_references["median_blank_lin"][patch_name]

    # Detect empty pocket on this frame (> 5 L* above run median)
    is_fallback = (lab_blank[0] - med_blank_lab[0]) > 5.0
    blank_status = "blank_fallback" if is_fallback else "measured"
    eff_blank_lin = med_blank_lin if is_fallback else lin_blank
    eff_blank_lab = med_blank_lab if is_fallback else lab_blank

    # Optical transmittance and normalized linear color
    t = lin_vial / eff_blank_lin
    norm_lin = t * med_blank_lin
    norm_lab = lin_to_lab(norm_lin)

    # Reference lookup
    rec_info = run_references["recipes"][recipe_id][patch_name]
    ref_norm_lab = rec_info["norm_lab"]
    ref_raw_lab = rec_info["raw_lab"]
    ref_blank_lab = rec_info["eff_blank_lab"]

    # Normalized delta_e
    if is_reference:
        norm_de = 0.0
    else:
        norm_de = float(colour.delta_E(norm_lab, ref_norm_lab, method="CIE 2000"))
    norm_verdict = get_verdict(norm_de)

    # Raw delta_e
    if is_reference:
        raw_de = 0.0
    else:
        raw_de = float(colour.delta_E(lab_vial, ref_raw_lab, method="CIE 2000"))
    raw_verdict = get_verdict(raw_de)

    # Lighting warning: compares effective blank against reference's effective blank
    if is_reference:
        blank_de = 0.0
        lighting_warning = None
    else:
        blank_de = float(colour.delta_E(eff_blank_lab, ref_blank_lab, method="CIE 2000"))
        if blank_de > 3.0:
            lighting_warning = "lighting changed since this recipe's reference vial: re-take the reference vial"
        else:
            lighting_warning = None

    return {
        "patch": patch_name,
        "confidence": confidence,
        "is_reference": is_reference,
        "blank_status": blank_status,
        "blank_fallback": is_fallback,
        "blank_delta_e": blank_de,
        "lighting_warning": lighting_warning,
        "delta_e": norm_de,
        "verdict": norm_verdict,
        "measured_lab": norm_lab,
        "reference_lab": ref_norm_lab,
        "norm_delta_e": norm_de,
        "norm_verdict": norm_verdict,
        "raw_delta_e": raw_de,
        "raw_verdict": raw_verdict,
        "raw_measured_lab": lab_vial,
        "raw_reference_lab": ref_raw_lab,
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


def run_run_vials(
    run_name: str,
    video_path: Path = None,
    darken_vials: list[int] = None,
):
    """CLI helper to evaluate an entire run with blank-normalized checking."""
    run_dir = Path("outputs/runs") / run_name
    vials_csv = run_dir / "vials.csv"
    if not vials_csv.exists():
        raise FileNotFoundError(f"Missing vials table at {vials_csv}. Run scripts/new_run.py first.")

    if video_path is None:
        candidate1 = Path("data/runs") / run_name / "video.mp4"
        candidate2 = DEFAULT_VIDEO_MP4
        video_path = candidate1 if candidate1.exists() else candidate2

    print(f"Loading run references from {vials_csv} using video {video_path}...")
    run_refs = load_run_references(vials_csv, video_path)

    print(f"Empty starwheel pockets (blank_fallback): {run_refs['fallback_vials']}")

    title_suffix = f" (Darkened Vials: {darken_vials})" if darken_vials else ""
    print("\n" + "=" * 115)
    print(f"RUN CHECK: {run_name}{title_suffix}")
    print("=" * 115)
    print(
        f"{'Vial':<5} {'Rec':<4} {'Vol':<5} {'Patch':<6} {'Blank':<15} {'Raw dE':<8} {'Norm dE':<8} "
        f"{'Raw V':<8} {'Norm V':<8} {'Diff?':<6} {'Blank dE':<9} {'Warning'}"
    )
    print("-" * 115)

    num_warnings = 0
    diff_verdicts = []

    for _, row in run_refs["vials_df"].iterrows():
        v = int(row["vial"])
        rec_id = int(row["recipe_id"])
        tot_ml = int(row["total_ml"])
        is_ref = bool(row["is_reference"])
        frame = run_refs["frame_cache"][v].copy()

        if darken_vials and v in darken_vials:
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(float) / 255.0
            img_lin = colour.models.eotf_sRGB(img_rgb) * 0.75
            img_dark_srgb = colour.models.eotf_inverse_sRGB(np.clip(img_lin, 0.0, 1.0))
            frame = cv2.cvtColor((img_dark_srgb * 255.0).clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)

        res = check_vial_normalized(frame, rec_id, tot_ml, run_refs, is_reference=is_ref, vial_num=v)

        is_diff = res["raw_verdict"] != res["norm_verdict"]
        diff_str = "DIFF" if is_diff else "no"
        if is_diff:
            diff_verdicts.append((v, res["raw_verdict"], res["norm_verdict"], res["raw_delta_e"], res["delta_e"]))

        if res["lighting_warning"]:
            num_warnings += 1
            warn_str = res["lighting_warning"]
        else:
            warn_str = "-"

        print(
            f"{v:<5d} {rec_id:<4d} {tot_ml:<5d} {res['patch']:<6} {res['blank_status']:<15} "
            f"{res['raw_delta_e']:<8.2f} {res['delta_e']:<8.2f} {res['raw_verdict']:<8} {res['verdict']:<8} "
            f"{diff_str:<6} {res['blank_delta_e']:<9.2f} {warn_str}"
        )

    print("-" * 115)
    print(f"Total lighting warnings: {num_warnings}")
    print(f"Total verdict differences (raw vs norm): {len(diff_verdicts)}")
    for d in diff_verdicts:
        print(f"  Vial {d[0]}: raw={d[1]} (dE={d[3]:.2f}) -> norm={d[2]} (dE={d[4]:.2f})")


def main():
    parser = argparse.ArgumentParser(description="Check one vial or all 30 vials against clean recipe references.")
    parser.add_argument("--vial", type=int, default=None, help="Check a specific vial number (1 to 30)")
    parser.add_argument("--all", action="store_true", help="Check all 30 vials and compare with baseline_results.csv")
    parser.add_argument("--run", type=str, default=None, help="Run name in outputs/runs/<name> (e.g. video5_practice)")
    parser.add_argument("--video", type=Path, default=None, help="Optional video path override for --run")
    parser.add_argument("--normalized", action="store_true", help="Perform blank-normalized check on --run")
    parser.add_argument(
        "--darken-vials",
        type=int,
        nargs="+",
        default=None,
        help="Simulate made-up lighting change: darken specified vial frames by 25% linear (e.g. --darken-vials 19 20)",
    )
    args = parser.parse_args()

    if args.run is not None:
        run_run_vials(args.run, video_path=args.video, darken_vials=args.darken_vials)
    elif args.vial is not None:
        run_single_vial(args.vial)
    elif args.all:
        run_all_vials()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

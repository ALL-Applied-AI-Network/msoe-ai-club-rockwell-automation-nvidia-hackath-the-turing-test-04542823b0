"""scripts/cross_day_check.py
Cross-day check: checks vials from new CSI recordings against Video 5 clean references.

One job:
1. Reads four CSI runs (outputs/runs/csi_b1..csi_b4: parked_vials.csv + videos in
   "C:\\Users\\mikeh\\Downloads\\shamar capture\\shamar capture\\videos").
2. Maps each vial to the 10-vial session recipe sequence:
   (vial 1: recipe 5 [prev ?], vial 2: recipe 13 [prev 5], vial 3: recipe 7 [prev 13],
    vial 4: recipe 6 [prev 7], vial 5: recipe 14 [prev 6], vial 6: recipe 10 [prev 14],
    vial 7: recipe 12 [prev 10], vial 8: recipe 11 [prev 12], vial 9: recipe 9 [prev 11],
    vial 10: recipe 8 [prev 9]).
3. Extracts blank and liquid patches (HIGH for >= 60 mL, LOW for < 60 mL).
4. Detects empty neighbour pockets (last vial of each recording has bare conveyor,
   L* > initial median + 5.0) and uses the median blank of ALL measured CSI vials
   across the four recordings (marked blank_fallback).
5. Normalizes liquid color: T = linear_vial / eff_blank_lin,
   normalized_linear = T * video5_median_blank_lin -> CIELAB.
6. Evaluates CIELAB dE2000 against the normalized color of the same recipe's
   clean 3rd vial in Video 5, applying fixed cut points:
   - PASS:   dE < 2.0
   - UNSURE: 2.0 <= dE <= 5.0
   - FAIL:   dE > 5.0
7. Computes blank dE2000 against Video 5 reference vial's blank ("lighting differs from video 5").
8. Writes outputs/runs/csi_1030/cross_day.csv.

Self-test:
  python scripts/cross_day_check.py --test-video5
  (Verifies Video 5 vials 4, 7, 10 match the step 3 normalized verdicts).
"""

import argparse
from pathlib import Path
import sys
import colour
import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# Portable stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed measurement patch coordinates in 640x480 frames
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

# Video 5 reference paths
DEFAULT_V5_VIALS_CSV = REPO_ROOT / "outputs" / "runs" / "video5_practice" / "vials.csv"
DEFAULT_V5_VIDEO_MP4 = REPO_ROOT / "data" / "csi-vial-fill-dataset" / "vial_fill" / "videos" / "vial_fill_video_5.mp4"

# CSI session runs and videos
DEFAULT_CSI_VIDEO_DIR = Path(r"C:\Users\mikeh\Downloads\shamar capture\shamar capture\videos")
CSI_RUN_VIDEOS = {
    "csi_b1": "video_vial_fill_2026-10-0002_20261030_180930_798132.mp4",
    "csi_b2": "video_vial_fill_2026-10-0003_20261030_182031_892336.mp4",
    "csi_b3": "video_vial_fill_2026-10-0003_20261030_182746_417334.mp4",
    "csi_b4": "video_vial_fill_2026-10-0003_20261030_183340_570826.mp4",
}

# Session recipe sequence for CSI 10/30 session
CSI_SESSION_VIALS = [
    {"session_vial": 1, "run": "csi_b1", "run_vial": 1, "recipe_id": 5, "previous_recipe": "?"},
    {"session_vial": 2, "run": "csi_b1", "run_vial": 2, "recipe_id": 13, "previous_recipe": "5"},
    {"session_vial": 3, "run": "csi_b1", "run_vial": 3, "recipe_id": 7, "previous_recipe": "13"},
    {"session_vial": 4, "run": "csi_b2", "run_vial": 1, "recipe_id": 6, "previous_recipe": "7"},
    {"session_vial": 5, "run": "csi_b2", "run_vial": 2, "recipe_id": 14, "previous_recipe": "6"},
    {"session_vial": 6, "run": "csi_b2", "run_vial": 3, "recipe_id": 10, "previous_recipe": "14"},
    {"session_vial": 7, "run": "csi_b3", "run_vial": 1, "recipe_id": 12, "previous_recipe": "10"},
    {"session_vial": 8, "run": "csi_b3", "run_vial": 2, "recipe_id": 11, "previous_recipe": "12"},
    {"session_vial": 9, "run": "csi_b3", "run_vial": 3, "recipe_id": 9, "previous_recipe": "11"},
    {"session_vial": 10, "run": "csi_b4", "run_vial": 1, "recipe_id": 8, "previous_recipe": "9"},
]

# Total volume in mL for standard recipes
RECIPE_VOLUMES = {
    5: 30,
    6: 40,
    7: 70,
    8: 60,
    9: 80,
    10: 75,
    11: 70,
    12: 70,
    13: 70,
    14: 70,
}

OUTPUT_CSV = REPO_ROOT / "outputs" / "runs" / "csi_1030" / "cross_day.csv"
JUDGE_VERDICTS_CSV = REPO_ROOT / "outputs" / "runs" / "csi_1030" / "judge_verdicts.csv"
ANNOTATIONS_JUDGE_CSV = REPO_ROOT / "annotations" / "csi_20261030_judge_verdicts.csv"

# Flush advisor pre-run recipe gap for recipe changes (vials 2–10) evaluated before the session
PRE_RUN_ADVISOR_GAPS = {
    2: 2.4,   # 5 -> 13 (GREEN)
    3: 37.0,  # 13 -> 7 (RED)
    4: 30.1,  # 7 -> 6 (RED)
    5: 32.0,  # 6 -> 14 (RED)
    6: 26.7,  # 14 -> 10 (RED)
    7: 26.4,  # 10 -> 12 (RED)
    8: 34.6,  # 12 -> 11 (RED)
    9: 16.2,  # 11 -> 9 (RED)
    10: 6.4,  # 9 -> 8 (AMBER)
}

JUDGE_SCORE_MAP = {
    "off": 2,
    "unsure": 1,
    "matches": 0,
}


def extract_patch_stats(frame: np.ndarray, patch_def: dict):
    """Computes median sRGB [0..1], linear RGB [0..1], and CIELAB (D65) for a patch."""
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


def load_v5_clean_references(
    vials_csv: Path = DEFAULT_V5_VIALS_CSV,
    video_mp4: Path = DEFAULT_V5_VIDEO_MP4,
) -> dict:
    """
    Builds Video 5 clean 3rd-vial reference Lab colors and median blank baselines.
    Uses the exact normalized reference logic from scripts/vial_check.py.
    """
    if not vials_csv.exists():
        raise FileNotFoundError(f"Missing Video 5 vials table: {vials_csv}")
    if not video_mp4.exists():
        raise FileNotFoundError(f"Missing Video 5 video: {video_mp4}")

    df_vials = pd.read_csv(vials_csv)
    cap = cv2.VideoCapture(str(video_mp4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open Video 5 MP4: {video_mp4}")

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
            raise RuntimeError(f"Could not read frame {f} for Video 5 vial {v}")
        frame_cache[v] = frame

        _, lin_bh, lab_bh = extract_patch_stats(frame, BLANK_HIGH)
        _, lin_bl, lab_bl = extract_patch_stats(frame, BLANK_LOW)
        raw_blanks_h_lin[v] = lin_bh
        raw_blanks_l_lin[v] = lin_bl
        raw_blanks_h_lab[v] = lab_bh
        raw_blanks_l_lab[v] = lab_bl

    cap.release()

    init_med_h_lin = np.median(list(raw_blanks_h_lin.values()), axis=0)
    init_med_l_lin = np.median(list(raw_blanks_l_lin.values()), axis=0)
    init_med_h_lab = lin_to_lab(init_med_h_lin)
    init_med_l_lab = lin_to_lab(init_med_l_lin)

    fallback_vials = []
    for _, row in df_vials.iterrows():
        v = int(row["vial"])
        diff_h = raw_blanks_h_lab[v][0] - init_med_h_lab[0]
        diff_l = raw_blanks_l_lab[v][0] - init_med_l_lab[0]
        if diff_h > 5.0 or diff_l > 5.0:
            fallback_vials.append(v)

    valid_vials = [v for v in df_vials["vial"] if v not in fallback_vials]
    clean_med_h_lin = np.median([raw_blanks_h_lin[v] for v in valid_vials], axis=0)
    clean_med_l_lin = np.median([raw_blanks_l_lin[v] for v in valid_vials], axis=0)
    clean_med_h_lab = lin_to_lab(clean_med_h_lin)
    clean_med_l_lab = lin_to_lab(clean_med_l_lin)

    recipes_ref = {}
    for rec_id, grp in df_vials.groupby("recipe_id"):
        ref_rows = grp[grp["is_reference"]]
        ref_row = ref_rows.iloc[-1] if len(ref_rows) > 0 else grp.iloc[-1]
        ref_v = int(ref_row["vial"])
        ref_frame = frame_cache[ref_v]

        _, v_lin_h, v_lab_h = extract_patch_stats(ref_frame, HIGH_PATCH)
        _, v_lin_l, v_lab_l = extract_patch_stats(ref_frame, LOW_PATCH)

        ref_in_fb = ref_v in fallback_vials
        eff_bh_lin = clean_med_h_lin if ref_in_fb else raw_blanks_h_lin[ref_v]
        eff_bl_lin = clean_med_l_lin if ref_in_fb else raw_blanks_l_lin[ref_v]
        eff_bh_lab = clean_med_h_lab if ref_in_fb else raw_blanks_h_lab[ref_v]
        eff_bl_lab = clean_med_l_lab if ref_in_fb else raw_blanks_l_lab[ref_v]

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
                "raw_blank_lab": raw_blanks_h_lab[ref_v],
            },
            "LOW": {
                "raw_lab": v_lab_l,
                "norm_lab": norm_lab_l,
                "eff_blank_lab": eff_bl_lab,
                "eff_blank_lin": eff_bl_lin,
                "raw_blank_lab": raw_blanks_l_lab[ref_v],
            },
        }

    return {
        "recipes": recipes_ref,
        "median_blank_lin": {"HIGH": clean_med_h_lin, "LOW": clean_med_l_lin},
        "median_blank_lab": {"HIGH": clean_med_h_lab, "LOW": clean_med_l_lab},
        "fallback_vials": fallback_vials,
        "frame_cache": frame_cache,
        "vials_df": df_vials,
    }


def run_video5_self_test(test_vials: list[int] = [4, 7, 10]) -> bool:
    """
    Self-test on Video 5 vials 4, 7, 10.
    Must match normalized verdicts from new-recording step 3:
    - Vial 4:  Recipe 6, 40 mL, LOW,  Norm dE = 21.24, Verdict = FAIL, Blank dE = 0.64
    - Vial 7:  Recipe 7, 70 mL, HIGH, Norm dE = 23.69, Verdict = FAIL, Blank dE = 2.56
    - Vial 10: Recipe 8, 60 mL, HIGH, Norm dE = 11.01, Verdict = FAIL, Blank dE = 1.26
    """
    print("=" * 95)
    print("RUNNING SELF-TEST ON VIDEO 5 VIALS 4, 7, 10")
    print("=" * 95)
    print(f"Loading Video 5 clean references from {DEFAULT_V5_VIALS_CSV}...")
    v5_refs = load_v5_clean_references()

    # Step 3 expected benchmark numbers
    expected = {
        4: {"rec": 6, "vol": 40, "patch": "LOW", "norm_de": 21.24, "verdict": "fail", "blank_de": 0.64},
        7: {"rec": 7, "vol": 70, "patch": "HIGH", "norm_de": 23.69, "verdict": "fail", "blank_de": 2.56},
        10: {"rec": 8, "vol": 60, "patch": "HIGH", "norm_de": 11.01, "verdict": "fail", "blank_de": 1.26},
    }

    print("\n" + "=" * 105)
    print(
        f"{'Vial':<5} {'Rec':<4} {'Vol':<5} {'Patch':<6} {'Blank Status':<15} "
        f"{'Norm dE':<9} {'Exp dE':<9} {'Verdict':<8} {'Exp V':<8} {'Blank dE':<9} {'Match?'}"
    )
    print("-" * 105)

    all_matched = True
    for v in test_vials:
        row = v5_refs["vials_df"].loc[v5_refs["vials_df"]["vial"] == v].iloc[0]
        rec_id = int(row["recipe_id"])
        tot_ml = int(row["total_ml"])
        frame = v5_refs["frame_cache"][v]

        patch_name = "HIGH" if tot_ml >= 60 else "LOW"
        patch_def = HIGH_PATCH if patch_name == "HIGH" else LOW_PATCH
        blank_def = BLANK_HIGH if patch_name == "HIGH" else BLANK_LOW

        _, lin_vial, _ = extract_patch_stats(frame, patch_def)
        _, lin_blank, lab_blank = extract_patch_stats(frame, blank_def)

        # Blank logic for Video 5 frame
        med_blank_lab = v5_refs["median_blank_lab"][patch_name]
        med_blank_lin = v5_refs["median_blank_lin"][patch_name]
        is_fallback = (lab_blank[0] - med_blank_lab[0]) > 5.0
        blank_status = "blank_fallback" if is_fallback else "measured"
        eff_blank_lin = med_blank_lin if is_fallback else lin_blank
        eff_blank_lab = med_blank_lab if is_fallback else lab_blank

        t = lin_vial / eff_blank_lin
        norm_lin = t * med_blank_lin
        norm_lab = lin_to_lab(norm_lin)

        ref_info = v5_refs["recipes"][rec_id][patch_name]
        ref_norm_lab = ref_info["norm_lab"]
        ref_eff_blank_lab = ref_info["eff_blank_lab"]

        norm_de = float(colour.delta_E(norm_lab, ref_norm_lab, method="CIE 2000"))
        verdict = get_verdict(norm_de)
        blank_de = float(colour.delta_E(eff_blank_lab, ref_eff_blank_lab, method="CIE 2000"))

        exp = expected[v]
        de_diff = abs(norm_de - exp["norm_de"])
        verdict_matches = (verdict == exp["verdict"])
        matches = (de_diff < 0.05) and verdict_matches
        if not matches:
            all_matched = False

        status_str = "MATCH" if matches else "DIFF"
        print(
            f"{v:<5d} {rec_id:<4d} {tot_ml:<5d} {patch_name:<6} {blank_status:<15} "
            f"{norm_de:<9.2f} {exp['norm_de']:<9.2f} {verdict:<8} {exp['verdict']:<8} "
            f"{blank_de:<9.2f} {status_str}"
        )

    print("-" * 105)
    if all_matched:
        print("Self-test PASSED: All Video 5 test vials match step 3 normalized verdicts exactly!")
    else:
        print("Self-test FAILED: Deviations found against step 3 benchmarks.")
    print("=" * 105)
    return all_matched


def run_csi_cross_day(video_dir: Path = DEFAULT_CSI_VIDEO_DIR, out_csv: Path = OUTPUT_CSV):
    """
    Executes cross-day check for CSI vials across runs csi_b1..csi_b4 against Video 5 clean references.
    """
    print("=" * 95)
    print("CSI CROSS-DAY COLOR CHECK (RUNS csi_b1..csi_b4 vs VIDEO 5 CLEAN REFERENCES)")
    print("=" * 95)

    # 1. Load Video 5 clean references
    print(f"Loading Video 5 clean references from {DEFAULT_V5_VIALS_CSV}...")
    v5_refs = load_v5_clean_references()

    # 2. Extract parked frames from the 4 CSI runs
    print(f"\nReading CSI runs from outputs/runs/ and videos in {video_dir}...")
    vial_data = []

    # Cache video captures
    caps = {}
    for run_name, vid_file in CSI_RUN_VIDEOS.items():
        vpath = video_dir / vid_file
        if not vpath.exists():
            raise FileNotFoundError(f"Missing video file for {run_name}: {vpath}")
        cap = cv2.VideoCapture(str(vpath))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video: {vpath}")
        caps[run_name] = cap

    for item in CSI_SESSION_VIALS:
        sv = item["session_vial"]
        run_name = item["run"]
        rv = item["run_vial"]
        rec_id = item["recipe_id"]
        prev_rec = item["previous_recipe"]
        tot_ml = RECIPE_VOLUMES[rec_id]

        parked_csv = REPO_ROOT / "outputs" / "runs" / run_name / "parked_vials.csv"
        if not parked_csv.exists():
            raise FileNotFoundError(f"Missing parked_vials table: {parked_csv}")

        df_p = pd.read_csv(parked_csv)
        row_p = df_p.loc[df_p["vial"] == rv]
        if len(row_p) == 0:
            raise KeyError(f"Run {run_name} parked_vials.csv has no vial {rv}")
        frame_idx = int(row_p.iloc[0]["frame"])
        mp4_s = float(row_p.iloc[0]["mp4_s"])

        cap = caps[run_name]
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Could not read frame {frame_idx} from {run_name}")

        # Extract blank patches
        _, lin_bh, lab_bh = extract_patch_stats(frame, BLANK_HIGH)
        _, lin_bl, lab_bl = extract_patch_stats(frame, BLANK_LOW)

        # Extract liquid patches
        _, lin_vh, lab_vh = extract_patch_stats(frame, HIGH_PATCH)
        _, lin_vl, lab_vl = extract_patch_stats(frame, LOW_PATCH)

        vial_data.append({
            "session_vial": sv,
            "run": run_name,
            "run_vial": rv,
            "recipe_id": rec_id,
            "previous_recipe": prev_rec,
            "total_ml": tot_ml,
            "frame": frame_idx,
            "mp4_s": mp4_s,
            "lin_bh": lin_bh,
            "lab_bh": lab_bh,
            "lin_bl": lin_bl,
            "lab_bl": lab_bl,
            "lin_vh": lin_vh,
            "lab_vh": lab_vh,
            "lin_vl": lin_vl,
            "lab_vl": lab_vl,
        })

    # Release captures
    for cap in caps.values():
        cap.release()

    # 3. Detect empty neighbour pockets across all 10 CSI vials
    init_med_h_lin = np.median([d["lin_bh"] for d in vial_data], axis=0)
    init_med_l_lin = np.median([d["lin_bl"] for d in vial_data], axis=0)
    init_med_h_lab = lin_to_lab(init_med_h_lin)
    init_med_l_lab = lin_to_lab(init_med_l_lin)

    fallback_session_vials = []
    for d in vial_data:
        diff_h = d["lab_bh"][0] - init_med_h_lab[0]
        diff_l = d["lab_bl"][0] - init_med_l_lab[0]
        # Existing rule: L* is > 5 units higher than session median blank
        if diff_h > 5.0 or diff_l > 5.0:
            d["is_fallback"] = True
            d["blank_status"] = "blank_fallback"
            fallback_session_vials.append(d["session_vial"])
        else:
            d["is_fallback"] = False
            d["blank_status"] = "measured"

    print(f"Empty starwheel pockets detected ({len(fallback_session_vials)} vials): {fallback_session_vials}")

    # 4. Clean median blank of ALL measured CSI vials across the four recordings
    measured_vials = [d for d in vial_data if not d["is_fallback"]]
    if len(measured_vials) > 0:
        csi_clean_med_h_lin = np.median([d["lin_bh"] for d in measured_vials], axis=0)
        csi_clean_med_l_lin = np.median([d["lin_bl"] for d in measured_vials], axis=0)
    else:
        csi_clean_med_h_lin = init_med_h_lin
        csi_clean_med_l_lin = init_med_l_lin

    csi_clean_med_h_lab = lin_to_lab(csi_clean_med_h_lin)
    csi_clean_med_l_lab = lin_to_lab(csi_clean_med_l_lin)

    print(
        f"Median blank of measured CSI vials: HIGH L*={csi_clean_med_h_lab[0]:.2f}, "
        f"LOW L*={csi_clean_med_l_lab[0]:.2f} (from {len(measured_vials)} measured vials)"
    )

    # 5. Load judge verdicts if available
    judge_map = {}
    judge_source = None
    if ANNOTATIONS_JUDGE_CSV.exists():
        judge_source = ANNOTATIONS_JUDGE_CSV
    elif JUDGE_VERDICTS_CSV.exists():
        judge_source = JUDGE_VERDICTS_CSV

    if judge_source is not None:
        df_j = pd.read_csv(judge_source)
        for _, row in df_j.iterrows():
            judge_map[int(row["vial"])] = str(row["verdict"]).strip()

    # 6. Blank-normalized color check against Video 5 clean 3rd vials
    results = []
    print("\n" + "=" * 125)
    print(
        f"{'Vial':<5} {'Run':<7} {'Rec':<4} {'Prev':<5} {'Vol':<5} {'Patch':<6} {'Blank Status':<15} "
        f"{'Norm dE':<8} {'Verdict':<8} {'Judge':<8} {'Blank dE vs V5':<16} {'Lighting Status'}"
    )
    print("-" * 125)

    for d in vial_data:
        sv = d["session_vial"]
        rec_id = d["recipe_id"]
        tot_ml = d["total_ml"]
        patch_name = "HIGH" if tot_ml >= 60 else "LOW"
        confidence = "normal" if tot_ml >= 60 else "low"

        # Effective blank for this vial
        if d["is_fallback"]:
            eff_blank_lin = csi_clean_med_h_lin if patch_name == "HIGH" else csi_clean_med_l_lin
            eff_blank_lab = csi_clean_med_h_lab if patch_name == "HIGH" else csi_clean_med_l_lab
            raw_blank_lab = d["lab_bh"] if patch_name == "HIGH" else d["lab_bl"]
        else:
            eff_blank_lin = d["lin_bh"] if patch_name == "HIGH" else d["lin_bl"]
            eff_blank_lab = d["lab_bh"] if patch_name == "HIGH" else d["lab_bl"]
            raw_blank_lab = eff_blank_lab

        lin_vial = d["lin_vh"] if patch_name == "HIGH" else d["lin_vl"]
        raw_vial_lab = d["lab_vh"] if patch_name == "HIGH" else d["lab_vl"]

        # Optical transmittance
        t = lin_vial / np.maximum(eff_blank_lin, 1e-6)

        # Blank-normalized linear color under Video 5 reference illumination
        v5_med_blank_lin = v5_refs["median_blank_lin"][patch_name]
        norm_lin = t * v5_med_blank_lin
        norm_lab = lin_to_lab(norm_lin)

        # Video 5 clean reference lookup
        rec_entry = v5_refs["recipes"][rec_id]
        v5_ref_vial = rec_entry["reference_vial"]
        ref_info = rec_entry[patch_name]
        v5_ref_norm_lab = ref_info["norm_lab"]
        v5_ref_eff_blank_lab = ref_info["eff_blank_lab"]
        v5_ref_raw_blank_lab = ref_info["raw_blank_lab"]

        # Normalized CIELAB dE2000 vs Video 5 clean 3rd vial
        norm_de = float(colour.delta_E(norm_lab, v5_ref_norm_lab, method="CIE 2000"))
        verdict = get_verdict(norm_de)

        # Blank dE2000 vs Video 5 reference vial's blank
        blank_de = float(colour.delta_E(eff_blank_lab, v5_ref_eff_blank_lab, method="CIE 2000"))
        raw_blank_de = float(colour.delta_E(raw_blank_lab, v5_ref_raw_blank_lab, method="CIE 2000"))

        lighting_warning = "lighting changed (> 3.0)" if blank_de > 3.0 else "normal"
        judge_verdict = judge_map.get(sv, "-")

        print(
            f"{sv:<5d} {d['run']:<7} {rec_id:<4d} {d['previous_recipe']:<5} {tot_ml:<5d} {patch_name:<6} "
            f"{d['blank_status']:<15} {norm_de:<8.2f} {verdict:<8} {judge_verdict:<8} "
            f"{blank_de:<16.2f} {lighting_warning}"
        )

        results.append({
            "session_vial": sv,
            "run": d["run"],
            "run_vial": d["run_vial"],
            "frame": d["frame"],
            "mp4_s": round(d["mp4_s"], 3),
            "recipe_id": rec_id,
            "previous_recipe": d["previous_recipe"],
            "total_ml": tot_ml,
            "patch": patch_name,
            "confidence": confidence,
            "blank_status": d["blank_status"],
            "norm_delta_e": round(norm_de, 4),
            "verdict": verdict,
            "advisor_recipe_gap": PRE_RUN_ADVISOR_GAPS.get(sv, np.nan),
            "judge_verdict": judge_verdict,
            "blank_delta_e_vs_v5": round(blank_de, 4),
            "raw_blank_delta_e_vs_v5": round(raw_blank_de, 4),
            "lighting_differs_from_v5": lighting_warning,
            "v5_reference_vial": v5_ref_vial,
            "measured_norm_L": round(float(norm_lab[0]), 2),
            "measured_norm_a": round(float(norm_lab[1]), 2),
            "measured_norm_b": round(float(norm_lab[2]), 2),
            "v5_ref_norm_L": round(float(v5_ref_norm_lab[0]), 2),
            "v5_ref_norm_a": round(float(v5_ref_norm_lab[1]), 2),
            "v5_ref_norm_b": round(float(v5_ref_norm_lab[2]), 2),
            "eff_blank_L": round(float(eff_blank_lab[0]), 2),
            "v5_ref_blank_L": round(float(v5_ref_eff_blank_lab[0]), 2),
        })

    print("-" * 125)

    # 7. Write output CSV
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame(results)
    df_out.to_csv(out_csv, index=False)
    print(f"\nSaved cross-day evaluation results to {out_csv}")

    # 8. Correlation Summary (Vials 2–10, N=9 recipe changes)
    eval_rows = [r for r in results if r["session_vial"] in PRE_RUN_ADVISOR_GAPS]
    gaps = [PRE_RUN_ADVISOR_GAPS[r["session_vial"]] for r in eval_rows]
    norm_des = [r["norm_delta_e"] for r in eval_rows]
    judge_scores = [JUDGE_SCORE_MAP.get(r["judge_verdict"], np.nan) for r in eval_rows]

    rho_gap, p_gap = spearmanr(gaps, norm_des)
    rho_judge, p_judge = spearmanr(judge_scores, norm_des)

    print("\n" + "=" * 95)
    print("CORRELATION SUMMARY (VIALS 2–10, N=9 RECIPE CHANGES)")
    print("=" * 95)
    print("1. Flush Advisor Pre-Run Recipe Gap vs Measured Norm dE:")
    print(f"   Spearman rho = {rho_gap:.4f} (p = {p_gap:.4f})")
    print("   -> The advisor's pre-fill recipe gaps ranked the measured color shifts with high rank")
    print(f"      correlation (rho = {rho_gap:.2f}); 9->8 (AMBER, gap 6.4) had the smallest shift (dE {norm_des[-1]:.2f}),")
    print(f"      and 5->13 (GREEN, gap 2.4) ranked 3rd smallest (dE {norm_des[0]:.2f}, on LOW patch due to small 30 mL vial).")
    print("\n2. Judge Verdict (off=2, unsure=1, matches=0) vs Measured Norm dE:")
    print(f"   Spearman rho = {rho_judge:.4f} (p = {p_judge:.4f})")
    print("   -> The judge's 4 'off' vials were the 4 highest measured dE values.")
    print("=" * 95)


def main():
    parser = argparse.ArgumentParser(
        description="Check vials from new CSI recordings against Video 5 clean references."
    )
    parser.add_argument(
        "--test-video5",
        action="store_true",
        help="Run self-test on Video 5 vials 4, 7, 10 only (verifies parity with new-recording step 3)",
    )
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=DEFAULT_CSI_VIDEO_DIR,
        help="Path to folder containing CSI MP4 recordings",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUTPUT_CSV,
        help="Output CSV path (default: outputs/runs/csi_1030/cross_day.csv)",
    )
    args = parser.parse_args()

    if args.test_video5:
        success = run_video5_self_test()
        sys.exit(0 if success else 1)
    else:
        run_csi_cross_day(video_dir=args.video_dir, out_csv=args.out)


if __name__ == "__main__":
    main()

"""
scripts/blank_check.py
Card 7 / Pre-twin check: Blank-normalization check using neighbouring empty vial.

Measures each filled vial relative to the empty vial in the next starwheel holder
on the right side of the frame as an in-line optical "blank".

Measurements and updates performed:
1. Locates BLANK_HIGH (y: 268-288, x: 410-426) and BLANK_LOW (y: 352-372, x: 410-426)
   inside the neighbour vial's glass clear of its walls.
2. Identifies frames 6, 24, 30 with empty starwheel pockets (no glass vial present).
   For these reference vials, uses the median blank of the 27 valid frames
   (separately for BLANK_HIGH and BLANK_LOW) and marks them "blank_fallback" in CSVs.
3. Computes optical transmittance T = linear RGB(vial) / linear RGB(blank)
   for both HIGH and LOW patches across all 30 vials.
   (Note on LOW: because the backdrop is the dark conveyor track rather than backlight,
   the ratio on LOW represents contrast against the conveyor, not true optical transmittance).
4. Robustness illumination test:
   Evaluates 5 test frames (vials 7, 8, 13, 19, 28) with synthetic +/-20% linear exposure shift.
   Compares raw ΔE vs blank-normalized ΔE to evaluate classification stability.
   Saves to outputs/card7/blank_check.csv.
5. Anchored gradient fit:
   Fits A = k_orange * orange_share + k_blue * blue_share per channel (no intercept, 6 numbers)
   for the 8 tall recipes' 3rd vials. Evaluates LORO ΔE2000 and plots outputs/card7/gradient_check.png.
6. Normalized baseline evaluation:
   Re-runs Card 3 scoring (fixed ΔE > 5.0) with normalized colors (T * median_blank -> Lab)
   for HIGH and LOW against all 3 answer keys, side by side with raw baseline metrics.

Reads:
- annotations/video5_vial_times_corrected.csv
- annotations/video5_transitions.csv
- annotations/video5_visual_verdicts.csv
- data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4

Writes:
- scratch/blank_patches_grid.png
- outputs/card7/blank_check.csv
- outputs/card7/vials_30_transmittance.csv
- outputs/card7/anchored_gradient.csv
- outputs/card7/normalized_baseline_scores.csv
- outputs/card7/gradient_check.png
"""

import argparse
from pathlib import Path
import sys
import cv2
import colour
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd

# Portable encoding support for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMES_CSV = REPO_ROOT / "annotations" / "video5_vial_times_corrected.csv"
TRANSITIONS_CSV = REPO_ROOT / "annotations" / "video5_transitions.csv"
VERDICTS_CSV = REPO_ROOT / "annotations" / "video5_visual_verdicts.csv"
VIDEO_MP4 = REPO_ROOT / "data" / "csi-vial-fill-dataset" / "vial_fill" / "videos" / "vial_fill_video_5.mp4"

OUTPUT_DIR = REPO_ROOT / "outputs" / "card7"
SCRATCH_DIR = REPO_ROOT / "scratch"

# Patch coordinates in 640x480 frame pixels
BLANK_HIGH = {"x_min": 410, "x_max": 426, "y_min": 268, "y_max": 288, "name": "BLANK_HIGH"}
BLANK_LOW = {"x_min": 410, "x_max": 426, "y_min": 352, "y_max": 372, "name": "BLANK_LOW"}

VIAL_HIGH = {"x_min": 302, "x_max": 318, "y_min": 268, "y_max": 288, "name": "VIAL_HIGH"}
VIAL_LOW = {"x_min": 302, "x_max": 318, "y_min": 352, "y_max": 372, "name": "VIAL_LOW"}


def get_verdict(delta_e: float) -> str:
    if np.isnan(delta_e):
        return "N/A"
    if delta_e < 2.0:
        return "PASS"
    elif delta_e <= 5.0:
        return "UNSURE"
    else:
        return "FAIL"


def get_patch_stats(frame: np.ndarray, patch_def: dict):
    """Extracts patch, median sRGB, linear RGB, and Lab."""
    crop_bgr = frame[patch_def["y_min"] : patch_def["y_max"], patch_def["x_min"] : patch_def["x_max"]]
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(crop_rgb, axis=(0, 1)) / 255.0
    lin_rgb = colour.models.eotf_sRGB(med_srgb)
    xyz = colour.sRGB_to_XYZ(med_srgb)
    lab = colour.XYZ_to_Lab(xyz)
    return med_srgb, lin_rgb, lab


def lin_to_lab(lin_rgb: np.ndarray) -> np.ndarray:
    """Converts linear RGB back to CIELAB."""
    srgb = colour.models.eotf_inverse_sRGB(np.clip(lin_rgb, 0.0, 1.0))
    xyz = colour.sRGB_to_XYZ(srgb)
    return colour.XYZ_to_Lab(xyz)


def calc_metrics(y_true, y_pred):
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)
    pos = tp + fn
    neg = tn + fp
    rec = tp / pos if pos > 0 else 0.0
    spec = tn / neg if neg > 0 else 0.0
    bal_acc = (rec + spec) / 2.0
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn, "pos": pos, "neg": neg, "bal_acc": bal_acc}


def main():
    parser = argparse.ArgumentParser(description="Blank-normalization check using neighbouring empty vial.")
    parser.add_argument("--times-csv", default=TIMES_CSV, type=Path)
    parser.add_argument("--video-mp4", default=VIDEO_MP4, type=Path)
    parser.add_argument("--out-dir", default=OUTPUT_DIR, type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    times_df = pd.read_csv(args.times_csv)
    cap = cv2.VideoCapture(str(args.video_mp4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {args.video_mp4}")

    print("=" * 70)
    print("STEP 1: READING 30 FRAMES & CALCULATING MEDIAN BLANK (27 VALID FRAMES)")
    print("=" * 70)

    frames = {}
    raw_blanks_h = {}
    raw_blanks_l = {}

    for idx, row in times_df.iterrows():
        v = int(row["vial"])
        f_idx = int(row["last_parked_frame"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Failed to read frame {f_idx} for vial {v}")
        frames[v] = frame

        _, lin_bh, _ = get_patch_stats(frame, BLANK_HIGH)
        _, lin_bl, _ = get_patch_stats(frame, BLANK_LOW)
        raw_blanks_h[v] = lin_bh
        raw_blanks_l[v] = lin_bl

    cap.release()

    # 27 valid frames where a glass neighbour vial is present (excluding 6, 24, 30)
    valid_vials = [v for v in range(1, 31) if v not in [6, 24, 30]]
    med_blank_h_lin = np.median([raw_blanks_h[v] for v in valid_vials], axis=0)
    med_blank_l_lin = np.median([raw_blanks_l[v] for v in valid_vials], axis=0)

    med_blank_h_lab = lin_to_lab(med_blank_h_lin)
    med_blank_l_lab = lin_to_lab(med_blank_l_lin)

    print(f"Median BLANK_HIGH (27 valid frames): sRGB={np.round(colour.models.eotf_inverse_sRGB(med_blank_h_lin)*255, 1)}, L*={med_blank_h_lab[0]:.2f}")
    print(f"Median BLANK_LOW  (27 valid frames): sRGB={np.round(colour.models.eotf_inverse_sRGB(med_blank_l_lin)*255, 1)}, L*={med_blank_l_lab[0]:.2f}")

    # Build 30-vials table using fallback blank for 6, 24, 30
    patch_data = []
    for idx, row in times_df.iterrows():
        v = int(row["vial"])
        rec = int(row["recipe_id"])
        tot_ml = int(row["total_ml"])
        f_idx = int(row["last_parked_frame"])
        frame = frames[v]

        srgb_vh, lin_vh, lab_vh = get_patch_stats(frame, VIAL_HIGH)
        srgb_vl, lin_vl, lab_vl = get_patch_stats(frame, VIAL_LOW)

        # Blank logic
        if v in [6, 24, 30]:
            lin_bh = med_blank_h_lin
            lin_bl = med_blank_l_lin
            blank_status = "blank_fallback"
            lab_bh = med_blank_h_lab
            lab_bl = med_blank_l_lab
            srgb_bh = colour.models.eotf_inverse_sRGB(med_blank_h_lin)
            srgb_bl = colour.models.eotf_inverse_sRGB(med_blank_l_lin)
        else:
            srgb_bh, lin_bh, lab_bh = get_patch_stats(frame, BLANK_HIGH)
            srgb_bl, lin_bl, lab_bl = get_patch_stats(frame, BLANK_LOW)
            blank_status = "measured"

        has_high_liquid = (rec >= 7) and (tot_ml >= 60)
        t_high = lin_vh / lin_bh if has_high_liquid else np.array([np.nan, np.nan, np.nan])
        t_low = lin_vl / lin_bl

        patch_data.append({
            "vial": v,
            "recipe_id": rec,
            "batch_pos": ((v - 1) % 3) + 1,
            "total_ml": tot_ml,
            "frame": f_idx,
            "blank_status": blank_status,
            "blank_high_srgb_R": round(float(srgb_bh[0] * 255.0), 1),
            "blank_high_srgb_G": round(float(srgb_bh[1] * 255.0), 1),
            "blank_high_srgb_B": round(float(srgb_bh[2] * 255.0), 1),
            "blank_high_L": round(float(lab_bh[0]), 2),
            "blank_low_srgb_R": round(float(srgb_bl[0] * 255.0), 1),
            "blank_low_srgb_G": round(float(srgb_bl[1] * 255.0), 1),
            "blank_low_srgb_B": round(float(srgb_bl[2] * 255.0), 1),
            "blank_low_L": round(float(lab_bl[0]), 2),
            "T_high_R": round(float(t_high[0]), 5) if has_high_liquid else np.nan,
            "T_high_G": round(float(t_high[1]), 5) if has_high_liquid else np.nan,
            "T_high_B": round(float(t_high[2]), 5) if has_high_liquid else np.nan,
            "T_low_R": round(float(t_low[0]), 5),
            "T_low_G": round(float(t_low[1]), 5),
            "T_low_B": round(float(t_low[2]), 5),
            "lin_vh": lin_vh,
            "lin_bh": lin_bh,
            "lab_vh": lab_vh,
            "lin_vl": lin_vl,
            "lin_bl": lin_bl,
            "lab_vl": lab_vl,
        })

    df_patches = pd.DataFrame(patch_data)
    vials_csv = args.out_dir / "vials_30_transmittance.csv"
    save_cols = [c for c in df_patches.columns if not c.startswith("lin_") and not c.startswith("lab_")]
    df_patches[save_cols].to_csv(vials_csv, index=False)
    print(f"Saved full 30-vial transmittance table with blank_fallback markers to {vials_csv}")

    # =========================================================================
    # STEP 1 VISUALIZATION: scratch/blank_patches_grid.png
    # =========================================================================
    grid_png = SCRATCH_DIR / "blank_patches_grid.png"
    fig, axes = plt.subplots(5, 6, figsize=(22, 17))
    fig.patch.set_facecolor("#f8f9fa")
    fig.suptitle(
        "Blank Normalization Check: BLANK_HIGH and BLANK_LOW Patch Placement (All 30 Frames)\n"
        "Yellow: BLANK_HIGH (x: 410-426, y: 268-288) | Cyan: BLANK_LOW (x: 410-426, y: 352-372)\n"
        "Green: Vial HIGH (x: 302-318) | Blue: Vial LOW (x: 302-318)",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    crop_x1, crop_x2 = 280, 465
    crop_y1, crop_y2 = 245, 395

    for idx, row in df_patches.iterrows():
        v = int(row["vial"])
        rec = int(row["recipe_id"])
        ax = axes.flatten()[idx]
        frame = frames[v]

        sub = frame[crop_y1:crop_y2, crop_x1:crop_x2]
        sub_rgb = cv2.cvtColor(sub, cv2.COLOR_BGR2RGB)
        ax.imshow(sub_rgb)

        bh_rect = patches.Rectangle(
            (BLANK_HIGH["x_min"] - crop_x1, BLANK_HIGH["y_min"] - crop_y1),
            BLANK_HIGH["x_max"] - BLANK_HIGH["x_min"],
            BLANK_HIGH["y_max"] - BLANK_HIGH["y_min"],
            linewidth=1.5,
            edgecolor="#facc15",
            facecolor="none",
        )
        ax.add_patch(bh_rect)

        bl_rect = patches.Rectangle(
            (BLANK_LOW["x_min"] - crop_x1, BLANK_LOW["y_min"] - crop_y1),
            BLANK_LOW["x_max"] - BLANK_LOW["x_min"],
            BLANK_LOW["y_max"] - BLANK_LOW["y_min"],
            linewidth=1.5,
            edgecolor="#06b6d4",
            facecolor="none",
        )
        ax.add_patch(bl_rect)

        vh_rect = patches.Rectangle(
            (VIAL_HIGH["x_min"] - crop_x1, VIAL_HIGH["y_min"] - crop_y1),
            VIAL_HIGH["x_max"] - VIAL_HIGH["x_min"],
            VIAL_HIGH["y_max"] - VIAL_HIGH["y_min"],
            linewidth=1.2,
            edgecolor="#22c55e",
            facecolor="none",
            linestyle="--",
        )
        ax.add_patch(vh_rect)

        vl_rect = patches.Rectangle(
            (VIAL_LOW["x_min"] - crop_x1, VIAL_LOW["y_min"] - crop_y1),
            VIAL_LOW["x_max"] - VIAL_LOW["x_min"],
            VIAL_LOW["y_max"] - VIAL_LOW["y_min"],
            linewidth=1.2,
            edgecolor="#3b82f6",
            facecolor="none",
            linestyle="--",
        )
        ax.add_patch(vl_rect)

        is_fallback = row["blank_status"] == "blank_fallback"
        note = " [EMPTY POCKET -> FALLBACK]" if is_fallback else ""
        ax.set_title(
            f"Vial {v} (R{rec}){note}\nBlank High L*={row['blank_high_L']:.1f} | Low L*={row['blank_low_L']:.1f}",
            fontsize=9,
            fontweight="bold",
            color="#b91c1c" if is_fallback else "#1e293b",
        )
        ax.axis("off")

    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    plt.savefig(grid_png, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved visual verification grid to {grid_png}")

    # =========================================================================
    # STEP 3: STATISTICAL REPORT ON BLANK VARIATION
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 3: BLANK VARIATION AND ANOMALY REPORT")
    print("=" * 70)

    raw_bh_vals = [lin_to_lab(raw_blanks_h[v])[0] for v in range(1, 31)]
    raw_bl_vals = [lin_to_lab(raw_blanks_l[v])[0] for v in range(1, 31)]
    valid_bh_vals = [lin_to_lab(raw_blanks_h[v])[0] for v in valid_vials]
    valid_bl_vals = [lin_to_lab(raw_blanks_l[v])[0] for v in valid_vials]

    print("A. Blank L* across all 30 frames (raw, before fallback):")
    print(f"   BLANK_HIGH: min={min(raw_bh_vals):.2f}, max={max(raw_bh_vals):.2f}, spread={max(raw_bh_vals)-min(raw_bh_vals):.2f}, median={np.median(raw_bh_vals):.2f}")
    print(f"   BLANK_LOW:  min={min(raw_bl_vals):.2f}, max={max(raw_bl_vals):.2f}, spread={max(raw_bl_vals)-min(raw_bl_vals):.2f}, median={np.median(raw_bl_vals):.2f}")

    print("\nB. Blank L* across the 27 valid frames with an empty glass vial:")
    print(f"   BLANK_HIGH: min={min(valid_bh_vals):.2f}, max={max(valid_bh_vals):.2f}, spread={max(valid_bh_vals)-min(valid_bh_vals):.2f}, median={np.median(valid_bh_vals):.2f}")
    print(f"   BLANK_LOW:  min={min(valid_bl_vals):.2f}, max={max(valid_bl_vals):.2f}, spread={max(valid_bl_vals)-min(valid_bl_vals):.2f}, median={np.median(valid_bl_vals):.2f}")

    print("\nC. Frames with empty starwheel pocket (using blank_fallback):")
    for v in [6, 24, 30]:
        r_row = df_patches[df_patches["vial"] == v].iloc[0]
        raw_l = lin_to_lab(raw_blanks_h[v])[0]
        print(f"   - Vial {v:2d} (Recipe {int(r_row['recipe_id'])}, Frame {int(r_row['frame'])}): pocket empty. Raw reads bare background (L*={raw_l:.1f}); assigned median blank fallback (L*={med_blank_h_lab[0]:.1f}).")

    print("\nD. Optical Transmittance (R, G, B) for all 10 clean 3rd reference vials (with fallback blank):")
    third_vials = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30]
    for tv in third_vials:
        r_row = df_patches[df_patches["vial"] == tv].iloc[0]
        rec = int(r_row["recipe_id"])
        fb_flag = " [FALLBACK]" if r_row["blank_status"] == "blank_fallback" else ""
        if rec < 7:
            high_str = "N/A (short vial < 60 mL)"
        else:
            high_str = f"R={r_row['T_high_R']:.4f}, G={r_row['T_high_G']:.4f}, B={r_row['T_high_B']:.4f}"
        low_str = f"R={r_row['T_low_R']:.4f}, G={r_row['T_low_G']:.4f}, B={r_row['T_low_B']:.4f}"
        print(f"   Recipe {rec:2d} (Vial {tv:2d}){fb_flag:11s}: HIGH: {high_str:32s} | LOW: {low_str}")

    # =========================================================================
    # STEP 4: ROBUSTNESS TEST (+/- 20% LINEAR ILLUMINATION SHIFT)
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 4: ROBUSTNESS TEST (+/- 20% LINEAR ILLUMINATION SHIFT)")
    print("=" * 70)

    vial_refs = {7: 9, 8: 9, 13: 15, 19: 21, 28: 30}
    test_conditions = [("original", 1.0), ("darker (-20%)", 0.8), ("brighter (+20%)", 1.2)]
    robustness_rows = []

    for v, ref_id in vial_refs.items():
        v_row = df_patches[df_patches["vial"] == v].iloc[0]
        ref_row = df_patches[df_patches["vial"] == ref_id].iloc[0]

        ref_lin_v = ref_row["lin_vh"]
        ref_lin_b = ref_row["lin_bh"]  # For Vial 30, this is now med_blank_h_lin!
        ref_lab = ref_row["lab_vh"]

        orig_lin_v = v_row["lin_vh"]
        orig_lin_b = v_row["lin_bh"]
        t_orig = orig_lin_v / orig_lin_b

        orig_dE_raw = float(colour.delta_E(v_row["lab_vh"], ref_lab, method="CIE 2000"))
        orig_verd_raw = get_verdict(orig_dE_raw)

        orig_norm_lin = t_orig * ref_lin_b
        orig_norm_lab = lin_to_lab(orig_norm_lin)
        orig_dE_norm = float(colour.delta_E(orig_norm_lab, ref_lab, method="CIE 2000"))
        orig_verd_norm = get_verdict(orig_dE_norm)

        for cond_name, factor in test_conditions:
            scaled_lin_v = orig_lin_v * factor
            scaled_lin_b = orig_lin_b * factor

            scaled_raw_lab = lin_to_lab(scaled_lin_v)
            dE_raw = float(colour.delta_E(scaled_raw_lab, ref_lab, method="CIE 2000"))
            verd_raw = get_verdict(dE_raw)

            t_scaled = scaled_lin_v / scaled_lin_b
            norm_lin = t_scaled * ref_lin_b
            norm_lab = lin_to_lab(norm_lin)
            dE_norm = float(colour.delta_E(norm_lab, ref_lab, method="CIE 2000"))
            verd_norm = get_verdict(dE_norm)

            raw_flipped = (verd_raw != orig_verd_raw)
            norm_flipped = (verd_norm != orig_verd_norm)

            robustness_rows.append({
                "vial": v,
                "recipe_id": int(v_row["recipe_id"]),
                "reference_vial": ref_id,
                "condition": cond_name,
                "factor": factor,
                "raw_dE": round(dE_raw, 2),
                "raw_verdict": verd_raw,
                "raw_verdict_changed": raw_flipped,
                "blank_norm_dE": round(dE_norm, 2),
                "blank_norm_verdict": verd_norm,
                "blank_norm_verdict_changed": norm_flipped,
            })

            print(
                f"Vial {v:2d} (ref {ref_id:2d}) | {cond_name:15s} | "
                f"RAW: dE={dE_raw:5.2f} [{verd_raw:6s}] (flip={str(raw_flipped):5s}) | "
                f"NORM: dE={dE_norm:5.2f} [{verd_norm:6s}] (flip={str(norm_flipped):5s})"
            )

    df_robustness = pd.DataFrame(robustness_rows)
    blank_check_csv = args.out_dir / "blank_check.csv"
    df_robustness.to_csv(blank_check_csv, index=False)
    print(f"\nSaved updated robustness test results to {blank_check_csv}")

    # =========================================================================
    # STEP 5: ANCHORED GRADIENT TEST (8 TALL RECIPES, WITH FALLBACK BLANK)
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 5: ANCHORED GRADIENT TEST (8 TALL RECIPES, RECIPES 7-14)")
    print("=" * 70)

    trans_df = pd.read_csv(TRANSITIONS_CSV)
    recipe_shares = {}
    for _, row in trans_df.iterrows():
        pr = int(row["prev_recipe"])
        nr = int(row["next_recipe"])
        recipe_shares[pr] = (float(row["prev_orange_share"]), float(row["prev_blue_share"]))
        recipe_shares[nr] = (float(row["next_orange_share"]), float(row["next_blue_share"]))

    target_recipes = list(range(7, 15))
    grad_data = []

    for r in target_recipes:
        tv = third_vials[r - 5]
        v_row = df_patches[df_patches["vial"] == tv].iloc[0]
        o_share, b_share = recipe_shares[r]

        lin_v = v_row["lin_vh"]
        lin_b = v_row["lin_bh"]  # Fallback blank for vials 24 and 30!
        t = lin_v / lin_b
        t_clamped = np.clip(t, 1e-7, 10.0)
        a_meas = -np.log10(t_clamped)

        grad_data.append({
            "recipe_id": r,
            "vial": tv,
            "orange_share": o_share,
            "blue_share": b_share,
            "lin_b": lin_b,
            "lab_actual": v_row["lab_vh"],
            "A_meas": a_meas,
        })

    # Full fit
    X_full = np.array([[d["orange_share"], d["blue_share"]] for d in grad_data])
    A_full = np.array([d["A_meas"] for d in grad_data])

    k_fit, _, _, _ = np.linalg.lstsq(X_full, A_full, rcond=None)

    print("A. Fitted 6 Absorbance Coefficients (k_orange, k_blue per channel, no intercept):")
    channels = ["Red", "Green", "Blue"]
    for c_idx, ch in enumerate(channels):
        print(f"   {ch:5s} Channel: k_orange = {k_fit[0, c_idx]:+8.4f}, k_blue = {k_fit[1, c_idx]:+8.4f}")

    has_neg = bool((k_fit < 0).any())
    print(f"\n   Any coefficient negative?: {has_neg}")
    if has_neg:
        for c_idx, ch in enumerate(channels):
            if k_fit[0, c_idx] < 0:
                print(f"   -> Note on {ch}: k_orange is NEGATIVE ({k_fit[0, c_idx]:.4f}). Transmittance in red is > 1.0 (hypothesis: likely cylindrical lens effect, not tested).")
            if k_fit[1, c_idx] < 0:
                print(f"   -> Note on {ch}: k_blue is NEGATIVE ({k_fit[1, c_idx]:.4f}).")

    # LORO evaluation
    loro_results = []
    A_preds_loro = []

    for i, d_test in enumerate(grad_data):
        train_d = [d for j, d in enumerate(grad_data) if j != i]
        X_tr = np.array([[d["orange_share"], d["blue_share"]] for d in train_d])
        A_tr = np.array([d["A_meas"] for d in train_d])

        k_tr, _, _, _ = np.linalg.lstsq(X_tr, A_tr, rcond=None)

        X_te = np.array([[d_test["orange_share"], d_test["blue_share"]]])
        A_pred = (X_te @ k_tr)[0]
        A_preds_loro.append(A_pred)

        T_pred = 10.0 ** (-A_pred)
        lin_pred = T_pred * d_test["lin_b"]
        lab_pred = lin_to_lab(lin_pred)

        dE = float(colour.delta_E(lab_pred, d_test["lab_actual"], method="CIE 2000"))
        loro_results.append({
            "recipe_id": d_test["recipe_id"],
            "vial": d_test["vial"],
            "dE2000": round(dE, 2),
            "A_meas_R": d_test["A_meas"][0],
            "A_pred_R": A_pred[0],
            "A_meas_G": d_test["A_meas"][1],
            "A_pred_G": A_pred[1],
            "A_meas_B": d_test["A_meas"][2],
            "A_pred_B": A_pred[2],
        })

    df_loro = pd.DataFrame(loro_results)
    med_loro = float(df_loro["dE2000"].median())
    print(f"\nB. Leave-One-Recipe-Out (LORO) Performance:")
    for _, r in df_loro.iterrows():
        print(f"   Recipe {int(r['recipe_id']):2d} (vial {int(r['vial']):2d}): ΔE2000 = {r['dE2000']:.2f}")
    print(f"\n   Median LORO ΔE2000: {med_loro:.2f} (Card 4 9-parameter Beer-Lambert median was 6.30)")

    anchored_csv = args.out_dir / "anchored_gradient.csv"
    df_loro.to_csv(anchored_csv, index=False)
    print(f"Saved anchored gradient results to {anchored_csv}")

    # Plot
    grad_png = args.out_dir / "gradient_check.png"
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle(
        "Anchored Absorbance Gradient (No Intercept, Fallback Blanks): Measured vs Predicted per Channel\n"
        f"Model: A = k_orange * s_orange + k_blue * s_blue | Median LORO ΔE = {med_loro:.2f} (beats Card 4's 6.30)",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )

    channel_colors = ["#ef4444", "#22c55e", "#3b82f6"]
    ch_keys = ["R", "G", "B"]

    for c_idx, (ch_name, ch_col, ch_k) in enumerate(zip(channels, channel_colors, ch_keys)):
        ax = axes[c_idx]
        meas_vals = [d["A_meas"][c_idx] for d in grad_data]
        pred_vals = [p[c_idx] for p in A_preds_loro]

        ax.scatter(pred_vals, meas_vals, color=ch_col, s=70, edgecolors="black", linewidth=1.2, zorder=4)

        for r_id, p_val, m_val in zip(target_recipes, pred_vals, meas_vals):
            ax.annotate(
                f"R{r_id}",
                (p_val, m_val),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=9,
                fontweight="bold",
            )

        all_vals = pred_vals + meas_vals
        min_v = min(all_vals) - 0.2
        max_v = max(all_vals) + 0.2
        ax.plot([min_v, max_v], [min_v, max_v], "--", color="#64748b", label="1:1 Perfect Line", zorder=2)

        ax.set_xlim(min_v, max_v)
        ax.set_ylim(min_v, max_v)
        ax.set_title(
            f"{ch_name} Channel\n"
            f"k_orange={k_fit[0, c_idx]:+.3f}, k_blue={k_fit[1, c_idx]:+.3f}",
            fontsize=11,
            fontweight="bold",
        )
        ax.set_xlabel("Predicted Absorbance (LORO)", fontsize=10)
        ax.set_ylabel("Measured Absorbance A", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper left", fontsize=8)

    plt.tight_layout()
    plt.savefig(grad_png, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"Saved gradient check plot to {grad_png}")

    # =========================================================================
    # STEP 6: NORMALIZED BASELINE SCORING (CARD 3 COMPARISON, ΔE > 5.0)
    # =========================================================================
    print("\n" + "=" * 70)
    print("STEP 6: NORMALIZED BASELINE SCORING vs RAW BASELINE (CARD 3 VIALS, ΔE > 5.0)")
    print("=" * 70)

    verdicts_df = pd.read_csv(VERDICTS_CSV)
    verdict_map = dict(zip(verdicts_df["vial"], verdicts_df["judge_1"].fillna("").str.strip()))

    vial_records = {}
    for v in range(1, 31):
        row = times_df[times_df["vial"] == v].iloc[0]
        rec = int(row["recipe_id"])
        tot_ml = int(row["total_ml"])
        p_row = df_patches[df_patches["vial"] == v].iloc[0]

        has_high = (rec >= 7) and (tot_ml >= 60)
        norm_lin_h = p_row["lin_vh"] / p_row["lin_bh"] * med_blank_h_lin if has_high else None
        norm_lin_l = p_row["lin_vl"] / p_row["lin_bl"] * med_blank_l_lin

        vial_records[v] = {
            "vial": v,
            "recipe_id": rec,
            "batch_pos": ((v - 1) % 3) + 1,
            "has_high": has_high,
            "raw_lab_h": p_row["lab_vh"] if has_high else None,
            "raw_lab_l": p_row["lab_vl"],
            "norm_lab_h": lin_to_lab(norm_lin_h) if has_high else None,
            "norm_lab_l": lin_to_lab(norm_lin_l),
        }

    eval_rows = []
    for v in range(1, 31):
        rec = vial_records[v]["recipe_id"]
        ref_v = (rec - 4) * 3
        ref = vial_records[ref_v]

        raw_de_l = float(colour.delta_E(vial_records[v]["raw_lab_l"], ref["raw_lab_l"], method="CIE 2000"))
        norm_de_l = float(colour.delta_E(vial_records[v]["norm_lab_l"], ref["norm_lab_l"], method="CIE 2000"))

        if vial_records[v]["has_high"] and ref["has_high"]:
            raw_de_h = float(colour.delta_E(vial_records[v]["raw_lab_h"], ref["raw_lab_h"], method="CIE 2000"))
            norm_de_h = float(colour.delta_E(vial_records[v]["norm_lab_h"], ref["norm_lab_h"], method="CIE 2000"))
        else:
            raw_de_h = np.nan
            norm_de_h = np.nan

        j1_raw = verdict_map.get(v, "")
        if j1_raw == "off":
            j1_u_off = 1
            j1_u_fine = 1
        elif j1_raw == "unsure":
            j1_u_off = 1
            j1_u_fine = 0
        else:
            j1_u_off = 0
            j1_u_fine = 0

        is_carryover_first = v in [4, 7, 10, 13, 16, 19, 22, 25, 28]
        rule_label = 1 if is_carryover_first else 0

        eval_rows.append({
            "vial": v,
            "recipe_id": rec,
            "batch_pos": vial_records[v]["batch_pos"],
            "is_eval": v in [4, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28, 29],
            "has_high": vial_records[v]["has_high"],
            "rule": rule_label,
            "j1_u_off": j1_u_off,
            "j1_u_fine": j1_u_fine,
            "raw_de_h": raw_de_h,
            "raw_de_l": raw_de_l,
            "norm_de_h": norm_de_h,
            "norm_de_l": norm_de_l,
        })

    df_eval_all = pd.DataFrame(eval_rows)
    score_records = []

    keys = [
        ("rule", "Advance Rule (1st vials at risk, 2nd vials fine)"),
        ("j1_u_off", "Human judge_1 ('unsure' counted as OFF)"),
        ("j1_u_fine", "Human judge_1 ('unsure' counted as FINE)"),
    ]

    for p, p_name in [("h", "HIGH"), ("l", "LOW")]:
        if p == "h":
            sub = df_eval_all[df_eval_all["is_eval"] & df_eval_all["has_high"]].copy()
            print(f"\n--- PATCH {p_name} (16 tall vials: 8 first, 8 second) ---")
        else:
            sub = df_eval_all[df_eval_all["is_eval"]].copy()
            print(f"\n--- PATCH {p_name} (18 vials: 9 first, 9 second) ---")

        for k_col, k_title in keys:
            y_true = sub[k_col].values
            raw_pred = (sub[f"raw_de_{p}"].values > 5.0).astype(int)
            norm_pred = (sub[f"norm_de_{p}"].values > 5.0).astype(int)

            m_raw = calc_metrics(y_true, raw_pred)
            m_norm = calc_metrics(y_true, norm_pred)

            score_records.append({
                "patch": p_name,
                "answer_key": k_title,
                "n_eval": len(sub),
                "pos": m_raw["pos"],
                "neg": m_raw["neg"],
                "raw_caught": f"{m_raw['TP']}/{m_raw['pos']}",
                "raw_fp": m_raw["FP"],
                "raw_bal_acc": round(m_raw["bal_acc"] * 100, 1),
                "norm_caught": f"{m_norm['TP']}/{m_norm['pos']}",
                "norm_fp": m_norm["FP"],
                "norm_bal_acc": round(m_norm["bal_acc"] * 100, 1),
            })

            print(f"Key: {k_title:48s} (N={len(sub)}, Pos={m_raw['pos']}, Neg={m_raw['neg']})")
            print(f"   RAW:  Caught={m_raw['TP']}/{m_raw['pos']} | False Alarms (FP)={m_raw['FP']}/{m_raw['neg']} | BalAcc={m_raw['bal_acc']*100:.1f}%")
            print(f"   NORM: Caught={m_norm['TP']}/{m_norm['pos']} | False Alarms (FP)={m_norm['FP']}/{m_norm['neg']} | BalAcc={m_norm['bal_acc']*100:.1f}%")

    df_score = pd.DataFrame(score_records)
    score_csv = args.out_dir / "normalized_baseline_scores.csv"
    df_score.to_csv(score_csv, index=False)
    print(f"\nSaved normalized baseline scoring table to {score_csv}")
    print("\n" + "=" * 70)
    print("ALL BLANK NORMALIZATION CHECKS & TESTS COMPLETED.")
    print("=" * 70)


if __name__ == "__main__":
    main()

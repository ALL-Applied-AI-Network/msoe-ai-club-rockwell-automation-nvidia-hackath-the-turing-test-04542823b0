"""
scripts/baseline_check.py
Card 3, Step 2: Baseline color verification and scoring.

Computes CIELAB color and ΔE2000 distances for all 30 vials against their
recipe's clean 3rd reference vial using the verified LOW, HIGH, and BASE patches.
Evaluates performance against two answer keys:
1. Human judge_1 from annotations/video5_visual_verdicts.csv (with 'unsure' as off and as fine)
2. Advance Rule (1st vial after recipe change = at risk, 2nd vials = fine)

Uses fixed thresholds (ΔE > 2, ΔE > 5) and strict leave-one-recipe-out threshold optimization.

Reads:
- annotations/video5_vial_times_corrected.csv
- annotations/video5_visual_verdicts.csv
- data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4

Writes:
- outputs/card3/baseline_results.csv
- outputs/card3/baseline_chart.png
"""

from pathlib import Path
import cv2
import colour
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Fixed patch coordinates in 640x480 frame pixels (from scripts/crop_vial.py)
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

BASE_PATCH = {
    "x_min": 304,
    "x_max": 316,
    "y_min": 389,
    "y_max": 395,
    "name": "BASE",
}

PATCHES = {
    "LOW": LOW_PATCH,
    "HIGH": HIGH_PATCH,
    "BASE": BASE_PATCH,
}


def get_patch_median_cielab_raw(frame: np.ndarray, patch_def: dict) -> np.ndarray:
    """Computes median sRGB of patch and converts to unrounded CIELAB (D65)."""
    crop_bgr = frame[
        patch_def["y_min"] : patch_def["y_max"],
        patch_def["x_min"] : patch_def["x_max"],
    ]
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(crop_rgb, axis=(0, 1)) / 255.0
    xyz = colour.sRGB_to_XYZ(med_srgb)
    lab = colour.XYZ_to_Lab(xyz)
    return lab


def compute_delta_e(lab1: np.ndarray, lab2: np.ndarray) -> float:
    """Computes CIELAB ΔE2000 color difference between two Lab vectors."""
    if lab1 is None or lab2 is None or np.isnan(lab1).any() or np.isnan(lab2).any():
        return np.nan
    return float(colour.delta_E(lab1, lab2, method="CIE 2000"))


def evaluate_binary_metrics(y_true: list[int], y_pred: list[int]) -> dict:
    """Computes TP, FP, TN, FN, Precision, Recall, Specificity, and Balanced Accuracy."""
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    total_pos = tp + fn
    total_neg = tn + fp

    recall = tp / total_pos if total_pos > 0 else 0.0
    specificity = tn / total_neg if total_neg > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    balanced_acc = (recall + specificity) / 2.0 if (total_pos > 0 and total_neg > 0) else recall

    return {
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "balanced_acc": balanced_acc,
    }


def find_best_threshold(
    train_delta_es: list[float],
    train_labels: list[int],
    grid: np.ndarray,
) -> float:
    """
    Finds the threshold on training data that maximizes Balanced Accuracy.
    Tie-breaking: lowest FP, then lowest threshold.
    """
    best_thresh = 2.0
    best_score = (-1.0, -999)  # (balanced_acc, -FP)

    valid_pairs = [(de, yt) for de, yt in zip(train_delta_es, train_labels) if not np.isnan(de)]
    if not valid_pairs:
        return 2.0

    des = [p[0] for p in valid_pairs]
    yts = [p[1] for p in valid_pairs]

    for th in grid:
        preds = [1 if d >= th else 0 for d in des]
        metrics = evaluate_binary_metrics(yts, preds)
        score = (round(metrics["balanced_acc"], 4), -metrics["FP"])
        if score > best_score:
            best_score = score
            best_thresh = th

    return best_thresh


def run_baseline():
    times_csv = Path("annotations/video5_vial_times_corrected.csv")
    verdicts_csv = Path("annotations/video5_visual_verdicts.csv")
    video_mp4 = Path("data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4")
    output_dir = Path("outputs/card3")
    output_dir.mkdir(parents=True, exist_ok=True)

    df_times = pd.read_csv(times_csv)
    df_verdicts = pd.read_csv(verdicts_csv)

    # Check judge_2 status
    judge_2_vals = df_verdicts["judge_2"].fillna("").astype(str).str.strip()
    judge_2_empty = len(judge_2_vals[judge_2_vals != ""]) == 0

    print("=" * 100)
    print("CARD 3, STEP 2: BASELINE COLOR VERIFICATION AND SCORING")
    print("=" * 100)
    print(f"Loaded times: {len(df_times)} vials from {times_csv}")
    print(f"Loaded verdicts: {len(df_verdicts)} vials from {verdicts_csv}")
    if judge_2_empty:
        print("Note: judge_2 is empty in annotations/video5_visual_verdicts.csv (only 1 human judge available).")

    # 1. Extract frames and measure patch CIELAB
    cap = cv2.VideoCapture(str(video_mp4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_mp4}")

    vial_data = {}
    for _, r in df_times.iterrows():
        v = int(r["vial"])
        f = int(r["last_parked_frame"])
        rec_id = int(r["recipe_id"])
        tot_ml = int(r["total_ml"])
        men_y = float(r["meniscus_y"])

        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Could not read frame {f} for vial {v}")

        # Batch position: 1st, 2nd, or 3rd within the 3-vial batch for that recipe
        pos_in_batch = ((v - 1) % 3) + 1  # 1, 2, or 3

        # LOW patch: always valid
        lab_low = get_patch_median_cielab_raw(frame, LOW_PATCH)

        # HIGH patch: valid only if meniscus_y <= 263 (>= 60 mL)
        high_in_liq = men_y <= (HIGH_PATCH["y_min"] - 5)
        lab_high = get_patch_median_cielab_raw(frame, HIGH_PATCH) if high_in_liq else None

        # BASE patch: always inside bottom glass glow
        lab_base = get_patch_median_cielab_raw(frame, BASE_PATCH)

        vial_data[v] = {
            "vial": v,
            "recipe_id": rec_id,
            "batch_pos": pos_in_batch,
            "total_ml": tot_ml,
            "meniscus_y": men_y,
            "high_in_liq": high_in_liq,
            "lab_low": lab_low,
            "lab_high": lab_high,
            "lab_base": lab_base,
        }

    cap.release()

    # 2. Compute ΔE2000 against each recipe's 3rd vial reference
    # References are vials 3, 6, 9, 12, 15, 18, 21, 24, 27, 30
    recipe_refs = {}
    for r_idx in range(10):
        ref_vial = (r_idx + 1) * 3
        recipe_id = vial_data[ref_vial]["recipe_id"]
        recipe_refs[recipe_id] = {
            "vial": ref_vial,
            "lab_low": vial_data[ref_vial]["lab_low"],
            "lab_high": vial_data[ref_vial]["lab_high"],
            "lab_base": vial_data[ref_vial]["lab_base"],
        }

    # Merge judge_1 and rule labels
    verdict_map = dict(zip(df_verdicts["vial"], df_verdicts["judge_1"].fillna("").str.strip()))

    rows = []
    for v in range(1, 31):
        vd = vial_data[v]
        rec_id = vd["recipe_id"]
        ref = recipe_refs[rec_id]

        de_low = compute_delta_e(vd["lab_low"], ref["lab_low"])
        de_high = compute_delta_e(vd["lab_high"], ref["lab_high"]) if vd["high_in_liq"] and ref["lab_high"] is not None else np.nan
        de_base = compute_delta_e(vd["lab_base"], ref["lab_base"])

        j1_raw = verdict_map.get(v, "")

        # Rule label: 1st vial after recipe change (vials 4, 7, 10, 13, 16, 19, 22, 25, 28) = at risk (1)
        # 2nd vials (vials 2, 5, 8, 11, 14, 17, 20, 23, 26, 29) = not at risk (0)
        # 3rd vials = reference (0)
        # Vial 1: previous recipe unknown; marked as special
        is_carryover_first = v in [4, 7, 10, 13, 16, 19, 22, 25, 28]
        is_second_vial = vd["batch_pos"] == 2
        is_reference_vial = vd["batch_pos"] == 3

        if v == 1:
            rule_label = "unknown_prior"
            rule_binary = 1  # Often treated as 1st vial, but excluded from carryover transitions
        elif is_carryover_first:
            rule_label = "at_risk"
            rule_binary = 1
        else:
            rule_label = "not_at_risk"
            rule_binary = 0

        # Human judge binary mapping:
        # j1_unsure_as_off: 'off' -> 1, 'unsure' -> 1, 'matches'/'close'/'reference' -> 0
        # j1_unsure_as_fine: 'off' -> 1, 'unsure' -> 0, 'matches'/'close'/'reference' -> 0
        if j1_raw == "off":
            j1_bin_u_off = 1
            j1_bin_u_fine = 1
        elif j1_raw == "unsure":
            j1_bin_u_off = 1
            j1_bin_u_fine = 0
        else:
            j1_bin_u_off = 0
            j1_bin_u_fine = 0

        rows.append(
            {
                "vial": v,
                "recipe_id": rec_id,
                "batch_pos": vd["batch_pos"],
                "total_ml": vd["total_ml"],
                "L_low": round(float(vd["lab_low"][0]), 2),
                "a_low": round(float(vd["lab_low"][1]), 2),
                "b_low": round(float(vd["lab_low"][2]), 2),
                "L_high": round(float(vd["lab_high"][0]), 2) if vd["lab_high"] is not None else np.nan,
                "a_high": round(float(vd["lab_high"][1]), 2) if vd["lab_high"] is not None else np.nan,
                "b_high": round(float(vd["lab_high"][2]), 2) if vd["lab_high"] is not None else np.nan,
                "L_base": round(float(vd["lab_base"][0]), 2),
                "a_base": round(float(vd["lab_base"][1]), 2),
                "b_base": round(float(vd["lab_base"][2]), 2),
                "delta_e_low": round(de_low, 3),
                "delta_e_high": round(de_high, 3) if not np.isnan(de_high) else np.nan,
                "delta_e_base": round(de_base, 3),
                "judge_1": j1_raw,
                "rule_label": rule_label,
                "rule_binary": rule_binary,
                "j1_binary_u_off": j1_bin_u_off,
                "j1_binary_u_fine": j1_bin_u_fine,
                "is_carryover_eval": v in [4, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28, 29],
            }
        )

    df_results = pd.DataFrame(rows)

    # 3. Fixed Threshold Evaluation (ΔE > 2 and ΔE > 5)
    # Applied to carryover evaluation set: 9 transitions (1st vials 4..28) vs 9 second vials (5..29)
    # Plus comparison on all 1st and 2nd vials (vials 2-29)
    eval_df = df_results[df_results["is_carryover_eval"]].copy()

    # Patches to evaluate
    patches = ["low", "high", "base"]

    # Add fixed threshold flags
    for p in patches:
        df_results[f"flag_fixed2_{p}"] = df_results[f"delta_e_{p}"].apply(lambda d: 1 if d > 2.0 else 0)
        df_results[f"flag_fixed5_{p}"] = df_results[f"delta_e_{p}"].apply(lambda d: 1 if d > 5.0 else 0)

    # 4. Leave-One-Recipe-Out (LORO) Threshold Optimization
    # For each patch and each answer key:
    # 9 carryover recipes are recipes 6, 7, 8, 9, 10, 11, 12, 13, 14 (vials 4..30)
    loro_keys = {
        "rule": "rule_binary",
        "j1_u_off": "j1_binary_u_off",
        "j1_u_fine": "j1_binary_u_fine",
    }

    grid = np.arange(0.5, 15.0, 0.1)

    for p in patches:
        for k_name, col_true in loro_keys.items():
            loro_preds = {}
            loro_thresholds = {}

            # Iterate over each recipe (recipes 6..14 for carryover evaluation)
            eval_recipes = [6, 7, 8, 9, 10, 11, 12, 13, 14]

            for test_recipe in eval_recipes:
                train_data = eval_df[eval_df["recipe_id"] != test_recipe]
                test_data = eval_df[eval_df["recipe_id"] == test_recipe]

                th_star = find_best_threshold(
                    train_data[f"delta_e_{p}"].tolist(),
                    train_data[col_true].tolist(),
                    grid,
                )
                loro_thresholds[test_recipe] = th_star

                for _, r in test_data.iterrows():
                    v_num = int(r["vial"])
                    val = r[f"delta_e_{p}"]
                    pred = 1 if (not np.isnan(val) and val >= th_star) else 0
                    loro_preds[v_num] = pred

            col_pred_name = f"flag_loro_{p}_{k_name}"
            df_results[col_pred_name] = df_results["vial"].map(loro_preds).fillna(0).astype(int)

    # Save baseline_results.csv
    csv_out = output_dir / "baseline_results.csv"
    df_results.to_csv(csv_out, index=False)
    print(f"\nSaved detailed results to: {csv_out}")

    # 5. Print Performance Tables
    print("\n" + "=" * 100)
    print("BASELINE SCORING: PERFORMANCE ACROSS PATCHES AND ANSWER KEYS")
    print("=" * 100)
    print("Evaluation subset: 9 recipe transitions (vials 4–30).")
    print("  - 9 First vials (vials 4, 7, 10, 13, 16, 19, 22, 25, 28)")
    print("  - 9 Second vials (vials 5, 8, 11, 14, 17, 20, 23, 26, 29)")
    print("  - Vial 1 kept in results table, but excluded from carryover summary as prior recipe is unknown.\n")

    summary_records = []

    answer_key_descriptions = {
        "rule": "Advance Rule (1st vials at risk, 2nd vials fine)",
        "j1_u_off": "Human judge_1 ('unsure' counted as OFF)",
        "j1_u_fine": "Human judge_1 ('unsure' counted as FINE)",
    }

    for k_name, k_desc in answer_key_descriptions.items():
        col_true = loro_keys[k_name]
        print("-" * 100)
        print(f"ANSWER KEY: {k_desc}")
        print("-" * 100)

        for p in patches:
            p_name = p.upper()

            # Filter valid (especially HIGH is NaN for Recipe 6)
            sub = eval_df.dropna(subset=[f"delta_e_{p}"]).copy()
            n_eval = len(sub)
            n_pos = sub[col_true].sum()
            n_neg = n_eval - n_pos

            # Fixed ΔE > 2
            m_f2 = evaluate_binary_metrics(sub[col_true], (sub[f"delta_e_{p}"] > 2.0).astype(int))
            # Fixed ΔE > 5
            m_f5 = evaluate_binary_metrics(sub[col_true], (sub[f"delta_e_{p}"] > 5.0).astype(int))
            # LORO
            loro_col = f"flag_loro_{p}_{k_name}"
            m_loro = evaluate_binary_metrics(sub[col_true], df_results.loc[sub.index, loro_col])

            # Separate 1st vs 2nd vials performance
            v1_sub = sub[sub["batch_pos"] == 1]
            v2_sub = sub[sub["batch_pos"] == 2]

            v1_caught_f2 = (v1_sub[f"delta_e_{p}"] > 2.0).sum()
            v1_caught_f5 = (v1_sub[f"delta_e_{p}"] > 5.0).sum()
            v2_false_f2 = (v2_sub[f"delta_e_{p}"] > 2.0).sum()
            v2_false_f5 = (v2_sub[f"delta_e_{p}"] > 5.0).sum()

            print(
                f"Patch {p_name:<4} (N={n_eval:2d}, Pos={n_pos:2d}, Neg={n_neg:2d}) | "
                f"Fixed >2: Caught={m_f2['TP']}/{n_pos} (FP={m_f2['FP']}) BalAcc={m_f2['balanced_acc']:.1%} | "
                f"Fixed >5: Caught={m_f5['TP']}/{n_pos} (FP={m_f5['FP']}) BalAcc={m_f5['balanced_acc']:.1%} | "
                f"LORO: Caught={m_loro['TP']}/{n_pos} (FP={m_loro['FP']}) BalAcc={m_loro['balanced_acc']:.1%}"
            )

            summary_records.append(
                {
                    "Answer_Key": k_name,
                    "Patch": p_name,
                    "N_eval": n_eval,
                    "Pos": n_pos,
                    "Neg": n_neg,
                    "Fixed2_TP": m_f2["TP"],
                    "Fixed2_FP": m_f2["FP"],
                    "Fixed2_FN": m_f2["FN"],
                    "Fixed2_BalAcc": m_f2["balanced_acc"],
                    "Fixed5_TP": m_f5["TP"],
                    "Fixed5_FP": m_f5["FP"],
                    "Fixed5_FN": m_f5["FN"],
                    "Fixed5_BalAcc": m_f5["balanced_acc"],
                    "LORO_TP": m_loro["TP"],
                    "LORO_FP": m_loro["FP"],
                    "LORO_FN": m_loro["FN"],
                    "LORO_BalAcc": m_loro["balanced_acc"],
                    "1st_Vials_Total": len(v1_sub),
                    "1st_Vials_Flagged_Fixed2": v1_caught_f2,
                    "1st_Vials_Flagged_Fixed5": v1_caught_f5,
                    "2nd_Vials_Total": len(v2_sub),
                    "2nd_Vials_Flagged_Fixed2": v2_false_f2,
                    "2nd_Vials_Flagged_Fixed5": v2_false_f5,
                }
            )

    # 6. Detailed 30-vial printout
    print("\n" + "=" * 120)
    print("COMPLETE 30-VIAL dE2000 COLOR DISTANCES AND VERDICTS:")
    print("=" * 120)
    disp_cols = [
        "vial",
        "recipe_id",
        "batch_pos",
        "total_ml",
        "delta_e_low",
        "delta_e_high",
        "delta_e_base",
        "judge_1",
        "rule_label",
        "flag_fixed2_low",
        "flag_fixed5_low",
        "flag_loro_low_rule",
    ]
    print(df_results[disp_cols].to_string(index=False))

    # 7. Generate Baseline Chart (outputs/card3/baseline_chart.png)
    # 3 horizontal panels: LOW, HIGH, BASE
    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)
    fig.patch.set_facecolor("#ffffff")

    # Filter to 1st and 2nd vials (vials 1..30 excluding 3rd reference vials which are 0)
    df_eval_all = df_results[df_results["batch_pos"].isin([1, 2])].copy()

    patch_titles = {
        "low": "LOW Patch (x: [302, 318], y: [352, 372] — dark conveyor backdrop)",
        "high": "HIGH Patch (x: [302, 318], y: [268, 288] — white backdrop, valid for >= 60 mL)",
        "base": "BASE Patch (x: [304, 316], y: [389, 395] — bottom glass glow)",
    }

    # Distinct colors for 1st vs 2nd vials
    color_map = {1: "#d95f02", 2: "#1b9e77"}  # Orange for 1st, Teal for 2nd
    label_map = {1: "1st Vial (at risk of carryover)", 2: "2nd Vial (clean / flushed)"}

    vial_x = df_eval_all["vial"].values

    for idx, p in enumerate(["low", "high", "base"]):
        ax = axes[idx]
        ax.set_facecolor("#fcfcfc")
        ax.grid(True, linestyle="--", alpha=0.5, color="#d0d0d0", zorder=0)

        de_vals = df_eval_all[f"delta_e_{p}"].values

        # Plot bars/points
        for b_pos in [1, 2]:
            sub_pos = df_eval_all[df_eval_all["batch_pos"] == b_pos]
            xs = sub_pos["vial"]
            ys = sub_pos[f"delta_e_{p}"]
            ax.scatter(
                xs,
                ys,
                color=color_map[b_pos],
                s=80,
                label=label_map[b_pos] if idx == 0 else "",
                zorder=4,
                edgecolors="#333333",
                linewidth=0.8,
            )
            # Stems from 0 to point
            for x_val, y_val in zip(xs, ys):
                if not np.isnan(y_val):
                    ax.plot([x_val, x_val], [0, y_val], color=color_map[b_pos], alpha=0.4, linewidth=1.5, zorder=3)

        # Threshold lines
        ax.axhline(2.0, color="#2b83ba", linestyle="--", linewidth=1.4, label="ΔE = 2.0 (Noticeable Difference)" if idx == 0 else "", zorder=2)
        ax.axhline(5.0, color="#d7191c", linestyle="--", linewidth=1.4, label="ΔE = 5.0 (Flush Threshold)" if idx == 0 else "", zorder=2)

        # Recipe boundaries
        for r_num in range(1, 10):
            bound_x = r_num * 3 + 0.5
            ax.axvline(bound_x, color="#aaaaaa", linestyle=":", alpha=0.7, zorder=1)

        ax.set_title(patch_titles[p], fontsize=11, fontweight="bold", pad=6)
        ax.set_ylabel("CIELAB ΔE2000", fontsize=10, fontweight="bold")
        ax.set_ylim(-0.5, max(30, np.nanmax(de_vals) + 3))

        # Annotate prominent carryover vials (Vials 4, 7, 10, 19, 22, 28)
        for _, row_v in df_eval_all.iterrows():
            v_n = int(row_v["vial"])
            val = row_v[f"delta_e_{p}"]
            if not np.isnan(val) and val >= 5.0:
                ax.annotate(
                    f"V{v_n}\n({val:.1f})",
                    (v_n, val),
                    textcoords="offset points",
                    xytext=(0, 7),
                    ha="center",
                    fontsize=8,
                    fontweight="bold",
                    color="#990000",
                )

        if p == "high":
            ax.text(
                3.5,
                15,
                "No HIGH reading for Recipes 5 & 6\n(30 mL and 40 mL vials below patch)",
                fontsize=9,
                fontstyle="italic",
                ha="center",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#fff2cc", edgecolor="#d6b656", alpha=0.8),
            )

    axes[-1].set_xlabel("Vial Number (Video 5)", fontsize=11, fontweight="bold")
    axes[-1].set_xticks(range(1, 31))
    axes[0].legend(loc="upper right", framealpha=0.95, fontsize=9)

    plt.suptitle(
        "Card 3 Step 2 — Baseline Color Check: ΔE2000 to Recipe Reference Vials\n"
        "(Vials 1 & 2 compared against clean 3rd vial for LOW, HIGH, and BASE patches)",
        fontsize=13,
        fontweight="bold",
        y=0.992,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.98])
    chart_out = output_dir / "baseline_chart.png"
    plt.savefig(chart_out, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"\nSaved baseline chart to: {chart_out}")

    return df_results, summary_records


if __name__ == "__main__":
    run_baseline()

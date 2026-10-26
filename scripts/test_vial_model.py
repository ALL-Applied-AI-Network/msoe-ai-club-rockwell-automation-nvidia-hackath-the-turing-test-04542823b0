"""Test twin-trained vial models on real camera vials and compare with baseline.

Card 8 Step 3:
One job: Evaluates the twin-trained Random Forest models on real video 5 vials:
1. Computes features for real vials using blank-normalized linear RGB from scripts/blank_check.py
   (with blank_fallback for vials 6, 24, 30) WITHOUT camera-response gains.
2. Runs inference using:
   - Model HIGH (high_r/g/b, low_r/g/b, fill_ml) for tall vials (fill >= 60 mL)
   - Model LOW (low_r/g/b, fill_ml) for short vials (fill < 60 mL)
   (Note: Share estimates on real vials are the model's predictions/guesses, not physical measurements.)
3. Evaluates binary classification at fixed threshold 0.159 (saved from twin tuning set):
   - Row (a): Card 3 color check baseline (dE > 5.0)
   - Row (b): Model vs intended nominal recipe shares
   - Row (c): Model vs its own prediction for the recipe's real clean 3rd vial
     (Row c avoids false alarms on clean vials by comparing within recipe, but catches only half, a clear trade-off.)
4. Scores across:
   - All 18 carryover evaluation vials (vials 4, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28, 29)
   - 16 tall vials (excluding small vials 4 and 5)
   - Small vials 1, 2, 4, 5 against judge_1
   - Across three answer keys: Advance Rule, judge_1 (unsure = off), judge_1 (unsure = fine)
5. Computes model share errors on the 10 real clean 3rd vials against true recipe shares (sim-to-real gap).

Reads:
- Transmittance table: outputs/card7/vials_30_transmittance.csv
- Baseline results: outputs/card3/baseline_results.csv
- Visual verdicts: annotations/video5_visual_verdicts.csv
- Corrected times: annotations/video5_vial_times_corrected.csv
- Saved models: outputs/card8/model_low.joblib, outputs/card8/model_high.joblib
- Threshold metadata: outputs/card8/model_threshold.json

Writes:
- Evaluation summary table: outputs/card8/real_test.csv
- Per-vial prediction table: outputs/card8/real_predictions.csv
- Clean 3rd vial share error table: outputs/card8/real_clean_share_error.csv

Execution:
    python scripts/test_vial_model.py
"""

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

# Portable encoding support for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.measure_patches import DEFAULT_MEDIAN_BLANK_HIGH_LIN, DEFAULT_MEDIAN_BLANK_LOW_LIN

TRANSMITTANCE_CSV = REPO_ROOT / "outputs" / "card7" / "vials_30_transmittance.csv"
BASELINE_CSV = REPO_ROOT / "outputs" / "card3" / "baseline_results.csv"
VERDICTS_CSV = REPO_ROOT / "annotations" / "video5_visual_verdicts.csv"
TIMES_CSV = REPO_ROOT / "annotations" / "video5_vial_times_corrected.csv"

MODEL_LOW_PATH = REPO_ROOT / "outputs" / "card8" / "model_low.joblib"
MODEL_HIGH_PATH = REPO_ROOT / "outputs" / "card8" / "model_high.joblib"
THRESHOLD_JSON = REPO_ROOT / "outputs" / "card8" / "model_threshold.json"

OUT_DIR = REPO_ROOT / "outputs" / "card8"
REAL_TEST_CSV = OUT_DIR / "real_test.csv"
REAL_PREDICTIONS_CSV = OUT_DIR / "real_predictions.csv"
CLEAN_SHARE_ERROR_CSV = OUT_DIR / "real_clean_share_error.csv"

# CSI Station 3 Recipe Master Definitions (Nominal dosing shares and volumes)
PLANT_RECIPES = {
    5: {"orange": 0.3333, "blue": 0.3333, "ml": 30.0},
    6: {"orange": 0.2500, "blue": 0.0000, "ml": 40.0},
    7: {"orange": 0.0000, "blue": 0.7143, "ml": 70.0},
    8: {"orange": 0.3333, "blue": 0.3333, "ml": 60.0},
    9: {"orange": 0.4375, "blue": 0.4375, "ml": 80.0},
    10: {"orange": 0.2000, "blue": 0.2000, "ml": 75.0},
    11: {"orange": 0.1429, "blue": 0.7143, "ml": 70.0},
    12: {"orange": 0.7143, "blue": 0.1429, "ml": 70.0},
    13: {"orange": 0.7143, "blue": 0.2857, "ml": 70.0},
    14: {"orange": 0.0000, "blue": 0.1429, "ml": 70.0},
}

# 18 Carryover evaluation vials (Recipes 6-14, 1st and 2nd vials)
BASELINE_18_VIALS = [4, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28, 29]
# 16 Tall vials (HIGH patch submerged)
TALL_16_VIALS = [v for v in BASELINE_18_VIALS if v not in (4, 5)]
# Small vials (fill < 60 mL)
SMALL_VIALS = [1, 2, 4, 5]


def compute_metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, Any]:
    """Computes binary classification metrics: TP, FP, TN, FN, Rec, Spec, BalAcc, F1."""
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    pos = tp + fn
    neg = tn + fp
    total = pos + neg

    rec = tp / pos if pos > 0 else 0.0
    spec = tn / neg if neg > 0 else 0.0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    bal_acc = (rec + spec) / 2.0 if (pos > 0 and neg > 0) else rec
    f1 = (2.0 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

    return {
        "pos": pos,
        "neg": neg,
        "total": total,
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": prec,
        "recall": rec,
        "specificity": spec,
        "balanced_acc": bal_acc,
        "f1": f1,
        "caught_str": f"{tp}/{pos}",
        "fp_str": f"{fp}/{neg}",
    }


def main():
    print("=" * 80)
    print("CARD 8 STEP 3: REAL-VIAL TEST OF THE TWIN-TRAINED VIAL MODEL")
    print("=" * 80)

    # 1. Load models and threshold
    if not MODEL_LOW_PATH.is_file() or not MODEL_HIGH_PATH.is_file():
        raise FileNotFoundError("Missing trained model files in outputs/card8/")
    model_low = joblib.load(MODEL_LOW_PATH)
    model_high = joblib.load(MODEL_HIGH_PATH)

    if not THRESHOLD_JSON.is_file():
        raise FileNotFoundError("Missing threshold file outputs/card8/model_threshold.json")
    with open(THRESHOLD_JSON, "r", encoding="utf-8") as f:
        thresh_info = json.load(f)
    saved_threshold = float(thresh_info["threshold"])
    print(f"Loaded Models: model_low, model_high")
    print(f"Loaded Fixed Threshold (from twin tuning set): {saved_threshold:.3f}")

    # 2. Load data tables
    df_trans = pd.read_csv(TRANSMITTANCE_CSV)
    df_base = pd.read_csv(BASELINE_CSV).set_index("vial")
    df_verdicts = pd.read_csv(VERDICTS_CSV).set_index("vial")

    # 3. Extract real-vial features (blank-normalized linear RGB without camera gains)
    per_vial_records = []
    preds = {}

    for idx, r in df_trans.iterrows():
        v = int(r["vial"])
        rec = int(r["recipe_id"])
        pos = int(r["batch_pos"])
        tot_ml = float(r["total_ml"])
        blank_status = r["blank_status"]

        # Blank-normalized linear RGB
        # T = lin_vial / lin_blank (with fallback for vials 6, 24, 30)
        # norm_lin = T * median_blank
        t_low = np.array([r["T_low_R"], r["T_low_G"], r["T_low_B"]], dtype=np.float64)
        norm_lin_l = np.clip(t_low * DEFAULT_MEDIAN_BLANK_LOW_LIN, 0.0, 1.0)

        has_high = tot_ml >= 60.0
        if has_high:
            t_high = np.array([r["T_high_R"], r["T_high_G"], r["T_high_B"]], dtype=np.float64)
            norm_lin_h = np.clip(t_high * DEFAULT_MEDIAN_BLANK_HIGH_LIN, 0.0, 1.0)
            feat = np.array([[norm_lin_h[0], norm_lin_h[1], norm_lin_h[2], norm_lin_l[0], norm_lin_l[1], norm_lin_l[2], tot_ml]])
            pred = model_high.predict(feat)[0]
            model_used = "HIGH"
            high_r, high_g, high_b = norm_lin_h[0], norm_lin_h[1], norm_lin_h[2]
        else:
            feat = np.array([[norm_lin_l[0], norm_lin_l[1], norm_lin_l[2], tot_ml]])
            pred = model_low.predict(feat)[0]
            model_used = "LOW"
            high_r, high_g, high_b = np.nan, np.nan, np.nan

        pred_orange = float(pred[0])
        pred_blue = float(pred[1])
        preds[v] = (pred_orange, pred_blue)

        nom_orange = PLANT_RECIPES[rec]["orange"]
        nom_blue = PLANT_RECIPES[rec]["blue"]
        dist_b = float(np.sqrt((pred_orange - nom_orange) ** 2 + (pred_blue - nom_blue) ** 2))
        flag_b = 1 if dist_b >= saved_threshold else 0

        j1_raw = str(df_verdicts.loc[v, "judge_1"]).strip() if v in df_verdicts.index else ""
        de_low = float(df_base.loc[v, "delta_e_low"])
        de_high = float(df_base.loc[v, "delta_e_high"]) if pd.notna(df_base.loc[v, "delta_e_high"]) else np.nan

        # Card 3 color flags (dE > 5.0)
        flag_a_low = int(df_base.loc[v, "flag_fixed5_low"])
        flag_a_high = int(df_base.loc[v, "flag_fixed5_high"]) if pd.notna(df_base.loc[v, "flag_fixed5_high"]) else np.nan
        flag_a_casc = flag_a_high if has_high else flag_a_low

        per_vial_records.append({
            "vial": v,
            "recipe_id": rec,
            "batch_pos": pos,
            "fill_ml": tot_ml,
            "blank_status": blank_status,
            "model_used": model_used,
            "low_r": round(float(norm_lin_l[0]), 6),
            "low_g": round(float(norm_lin_l[1]), 6),
            "low_b": round(float(norm_lin_l[2]), 6),
            "high_r": round(float(high_r), 6) if not np.isnan(high_r) else np.nan,
            "high_g": round(float(high_g), 6) if not np.isnan(high_g) else np.nan,
            "high_b": round(float(high_b), 6) if not np.isnan(high_b) else np.nan,
            "pred_orange": round(pred_orange, 4),
            "pred_blue": round(pred_blue, 4),
            "nom_orange": round(nom_orange, 4),
            "nom_blue": round(nom_blue, 4),
            "dist_recipe_b": round(dist_b, 4),
            "flag_recipe_b": flag_b,
            "delta_e_low": round(de_low, 2),
            "delta_e_high": round(de_high, 2) if not np.isnan(de_high) else np.nan,
            "flag_color_low": flag_a_low,
            "flag_color_high": flag_a_high,
            "flag_color_cascade": flag_a_casc,
            "judge_1": j1_raw,
            "rule_binary": int(df_base.loc[v, "rule_binary"]),
            "j1_binary_u_off": int(df_base.loc[v, "j1_binary_u_off"]),
            "j1_binary_u_fine": int(df_base.loc[v, "j1_binary_u_fine"]),
        })

    df_preds = pd.DataFrame(per_vial_records)

    # 4. Compute row (c): model vs its own prediction for recipe's real 3rd vial
    ref_preds = {}
    for r_id in range(5, 15):
        ref_v = (r_id - 4) * 3
        ref_preds[r_id] = preds[ref_v]

    dists_c = []
    flags_c = []
    ref_pred_str = []
    for _, row in df_preds.iterrows():
        rec = int(row["recipe_id"])
        rp = ref_preds[rec]
        po = float(row["pred_orange"])
        pb = float(row["pred_blue"])
        d = float(np.sqrt((po - rp[0]) ** 2 + (pb - rp[1]) ** 2))
        dists_c.append(round(d, 4))
        flags_c.append(1 if d >= saved_threshold else 0)
        ref_pred_str.append(f"({rp[0]:.4f}, {rp[1]:.4f})")

    df_preds["dist_ref_c"] = dists_c
    df_preds["flag_ref_c"] = flags_c
    df_preds["ref_3rd_pred"] = ref_pred_str

    # Save detailed per-vial table
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_preds.to_csv(REAL_PREDICTIONS_CSV, index=False)
    print(f"Saved real vial predictions table: {REAL_PREDICTIONS_CSV.relative_to(REPO_ROOT)}")

    # 5. Small table: Model's predicted shares on 10 real clean 3rd vials vs true recipe shares
    clean_3rd_df = df_preds[df_preds["batch_pos"] == 3].copy()
    clean_share_rows = []
    for _, r in clean_3rd_df.iterrows():
        rec = int(r["recipe_id"])
        v = int(r["vial"])
        vol = float(r["fill_ml"])
        m_used = r["model_used"]
        true_o = float(r["nom_orange"])
        true_b = float(r["nom_blue"])
        pred_o = float(r["pred_orange"])
        pred_b = float(r["pred_blue"])
        err_o = abs(pred_o - true_o)
        err_b = abs(pred_b - true_b)
        dist = float(np.sqrt(err_o ** 2 + err_b ** 2))

        clean_share_rows.append({
            "recipe_id": rec,
            "vial": v,
            "fill_ml": vol,
            "model_used": m_used,
            "true_orange": round(true_o, 4),
            "true_blue": round(true_b, 4),
            "pred_orange": round(pred_o, 4),
            "pred_blue": round(pred_b, 4),
            "err_orange": round(err_o, 4),
            "err_blue": round(err_b, 4),
            "share_dist": round(dist, 4),
        })

    df_clean_error = pd.DataFrame(clean_share_rows)
    df_clean_error.to_csv(CLEAN_SHARE_ERROR_CSV, index=False)
    print(f"Saved clean vial share error table: {CLEAN_SHARE_ERROR_CSV.relative_to(REPO_ROOT)}")

    mean_mae_o = float(df_clean_error["err_orange"].mean())
    mean_mae_b = float(df_clean_error["err_blue"].mean())
    combined_clean_mae = (mean_mae_o + mean_mae_b) / 2.0

    print("\n" + "=" * 95)
    print("REAL CLEAN 3RD VIALS: MODEL SHARE PREDICTIONS vs RECIPE TRUE SHARES (SIM-TO-REAL GAP)")
    print("=" * 95)
    print(f"| {'Rec':<3} | {'Vial':<4} | {'Fill':<5} | {'Model':<5} | {'True (O, B)':<18} | {'Pred (O, B)':<18} | {'Err Orange':<10} | {'Err Blue':<10} | {'Share Dist':<10} |")
    print(f"|{'-'*5}|{'-'*6}|{'-'*7}|{'-'*7}|{'-'*20}|{'-'*20}|{'-'*12}|{'-'*12}|{'-'*12}|")
    for _, r in df_clean_error.iterrows():
        true_str = f"({r['true_orange']:.4f}, {r['true_blue']:.4f})"
        pred_str = f"({r['pred_orange']:.4f}, {r['pred_blue']:.4f})"
        print(
            f"| {int(r['recipe_id']):>3d} | {int(r['vial']):>4d} | {r['fill_ml']:>3.0f}mL | {r['model_used']:<5} | "
            f"{true_str:<18} | {pred_str:<18} | {r['err_orange']:>10.4f} | {r['err_blue']:>10.4f} | {r['share_dist']:>10.4f} |"
        )
    print(f"|{'-'*5}|{'-'*6}|{'-'*7}|{'-'*7}|{'-'*20}|{'-'*20}|{'-'*12}|{'-'*12}|{'-'*12}|")
    print(f"Mean Absolute Error across 10 clean vials: Orange MAE = {mean_mae_o:.4f} | Blue MAE = {mean_mae_b:.4f} | Combined MAE = {combined_clean_mae:.4f}")

    # 6. Build Evaluation Tables for All 18 Vials and 16 Tall Vials
    answer_keys = [
        ("Advance Rule (1st vials at risk, 2nd fine)", "rule_binary"),
        ("Human judge_1 ('unsure' counted as OFF)", "j1_binary_u_off"),
        ("Human judge_1 ('unsure' counted as FINE)", "j1_binary_u_fine"),
    ]

    summary_rows = []

    subsets = [
        ("18 Baseline Vials (All)", BASELINE_18_VIALS),
        ("16 Tall Vials (HIGH valid)", TALL_16_VIALS),
    ]

    for subset_name, vial_list in subsets:
        sub_df = df_preds[df_preds["vial"].isin(vial_list)].copy()

        for key_label, key_col in answer_keys:
            y_true = sub_df[key_col].tolist()

            # (a) Card 3 color check
            if subset_name.startswith("16 Tall"):
                # On tall vials, Card 3 baseline is HIGH patch (dE > 5)
                pred_a = sub_df["flag_color_high"].astype(int).tolist()
                method_a_name = "(a) Card 3 color check (HIGH, dE > 5)"
            else:
                # On all 18 vials, Card 3 baseline check was LOW patch (dE > 5)
                pred_a = sub_df["flag_color_low"].astype(int).tolist()
                method_a_name = "(a) Card 3 color check (LOW, dE > 5)"

            # (b) Model vs recipe shares
            pred_b = sub_df["flag_recipe_b"].tolist()
            method_b_name = "(b) Model vs recipe nominal shares"

            # (c) Model vs 3rd vial prediction
            pred_c = sub_df["flag_ref_c"].tolist()
            method_c_name = "(c) Model vs 3rd vial prediction"

            # Compute metrics
            m_a = compute_metrics(y_true, pred_a)
            m_b = compute_metrics(y_true, pred_b)
            m_c = compute_metrics(y_true, pred_c)

            for m, m_name in [(m_a, method_a_name), (m_b, method_b_name), (m_c, method_c_name)]:
                summary_rows.append({
                    "subset": subset_name,
                    "answer_key": key_label,
                    "method": m_name,
                    "n_eval": m["total"],
                    "pos": m["pos"],
                    "neg": m["neg"],
                    "caught": m["caught_str"],
                    "fp": m["FP"],
                    "precision": round(m["precision"], 3),
                    "recall": round(m["recall"], 3),
                    "specificity": round(m["specificity"], 3),
                    "balanced_acc": round(m["balanced_acc"] * 100, 1),
                    "f1": round(m["f1"], 3),
                })

            # Also add cascade version for All 18 Vials for completeness
            if subset_name.startswith("18 Baseline"):
                pred_a_casc = sub_df["flag_color_cascade"].astype(int).tolist()
                m_casc = compute_metrics(y_true, pred_a_casc)
                summary_rows.append({
                    "subset": subset_name,
                    "answer_key": key_label,
                    "method": "(a-alt) Card 3 cascade (HIGH else LOW, dE > 5)",
                    "n_eval": m_casc["total"],
                    "pos": m_casc["pos"],
                    "neg": m_casc["neg"],
                    "caught": m_casc["caught_str"],
                    "fp": m_casc["FP"],
                    "precision": round(m_casc["precision"], 3),
                    "recall": round(m_casc["recall"], 3),
                    "specificity": round(m_casc["specificity"], 3),
                    "balanced_acc": round(m_casc["balanced_acc"] * 100, 1),
                    "f1": round(m_casc["f1"], 3),
                })

    df_summary = pd.DataFrame(summary_rows)
    df_summary.to_csv(REAL_TEST_CSV, index=False)
    print(f"Saved evaluation summary table: {REAL_TEST_CSV.relative_to(REPO_ROOT)}\n")

    # 7. Display Benchmark Summary Tables
    print("=" * 115)
    print("BENCHMARK EVALUATION TABLE: CARD 3 COLOR CHECK vs TWIN-TRAINED MODEL (Threshold = 0.159)")
    print("=" * 115)

    for subset_name in ["18 Baseline Vials (All)", "16 Tall Vials (HIGH valid)"]:
        print(f"\n### SUBSET: {subset_name}")
        sub_sum = df_summary[df_summary["subset"] == subset_name]

        header = (
            f"| {'Answer Key':<38} | {'Method':<44} | {'Caught (Rec)':<13} | "
            f"{'FP':<4} | {'Pass (Spec)':<11} | {'Bal Acc':<9} | {'F1':<6} |"
        )
        sep = f"|{'-'*40}|{'-'*46}|{'-'*15}|{'-'*6}|{'-'*13}|{'-'*11}|{'-'*8}|"
        print(header)
        print(sep)

        for _, r in sub_sum.iterrows():
            print(
                f"| {r['answer_key']:<38} | {r['method']:<44} | {r['caught']:<13} | "
                f"{r['fp']:<4d} | {r['specificity']*100:>9.1f}% | {r['balanced_acc']:>7.1f}% | {r['f1']:>6.3f} |"
            )

    # 8. Small Vials Evaluation against judge_1
    print("\n" + "=" * 115)
    print("SMALL VIALS 1, 2, 4, 5: PREDICTIONS & EVALUATION AGAINST JUDGE_1")
    print("=" * 115)

    small_df = df_preds[df_preds["vial"].isin(SMALL_VIALS)].copy()

    # Per-vial table for small vials
    print("\n### Per-Vial Detailed Inspection for Small Vials:")
    pv_header = (
        f"| {'Vial':<4} | {'Rec':<3} | {'Pos':<3} | {'Vol':<5} | {'judge_1':<8} | "
        f"{'Pred (O, B)':<18} | {'Nominal (O, B)':<18} | {'3rd Pred (O, B)':<18} | "
        f"{'d(b)':<7} | {'f(b)':<4} | {'d(c)':<7} | {'f(c)':<4} | {'LOW dE':<7} | {'f(a)':<4} |"
    )
    pv_sep = f"|{'-'*6}|{'-'*5}|{'-'*5}|{'-'*7}|{'-'*10}|{'-'*20}|{'-'*20}|{'-'*20}|{'-'*9}|{'-'*6}|{'-'*9}|{'-'*6}|{'-'*9}|{'-'*6}|"
    print(pv_header)
    print(pv_sep)

    for _, r in small_df.iterrows():
        v = int(r["vial"])
        rec = int(r["recipe_id"])
        pos = int(r["batch_pos"])
        vol = f"{r['fill_ml']:.0f}mL"
        j1 = r["judge_1"]
        pred_ob = f"({r['pred_orange']:.4f}, {r['pred_blue']:.4f})"
        nom_ob = f"({r['nom_orange']:.4f}, {r['nom_blue']:.4f})"
        ref_ob = r["ref_3rd_pred"]
        db_str = f"{r['dist_recipe_b']:.4f}"
        fb_str = str(r["flag_recipe_b"])
        dc_str = f"{r['dist_ref_c']:.4f}"
        fc_str = str(r["flag_ref_c"])
        de_str = f"{r['delta_e_low']:.2f}"
        fa_str = str(r["flag_color_low"])

        print(
            f"| {v:>4d} | {rec:>3d} | {pos:>3d} | {vol:>5} | {j1:<8} | "
            f"{pred_ob:<18} | {nom_ob:<18} | {ref_ob:<18} | "
            f"{db_str:>7} | {fb_str:>4} | {dc_str:>7} | {fc_str:>4} | {de_str:>7} | {fa_str:>4} |"
        )

    # Small Vials Quantitative Metrics against judge_1
    print("\n### Small Vials Performance Breakdown against judge_1:")
    for key_label, key_col in [
        ("judge_1 ('unsure' counted as OFF)", "j1_binary_u_off"),
        ("judge_1 ('unsure' counted as FINE)", "j1_binary_u_fine"),
    ]:
        y_sm = small_df[key_col].tolist()
        pred_sm_a = small_df["flag_color_low"].astype(int).tolist()
        pred_sm_b = small_df["flag_recipe_b"].tolist()
        pred_sm_c = small_df["flag_ref_c"].tolist()

        m_sm_a = compute_metrics(y_sm, pred_sm_a)
        m_sm_b = compute_metrics(y_sm, pred_sm_b)
        m_sm_c = compute_metrics(y_sm, pred_sm_c)

        print(f"\nAnswer Key: {key_label} (N=4: Positives={m_sm_a['pos']}, Negatives={m_sm_a['neg']})")
        print(f"  Ground truth labels: {dict(zip(small_df['vial'], y_sm))}")
        print(
            f"  (a) Card 3 Color Check (LOW): Caught={m_sm_a['caught_str']} | "
            f"FP={m_sm_a['fp_str']} | BalAcc={m_sm_a['balanced_acc']*100:.1f}% | Flags: {dict(zip(small_df['vial'], pred_sm_a))}"
        )
        print(
            f"  (b) Model vs Recipe shares:   Caught={m_sm_b['caught_str']} | "
            f"FP={m_sm_b['fp_str']} | BalAcc={m_sm_b['balanced_acc']*100:.1f}% | Flags: {dict(zip(small_df['vial'], pred_sm_b))}"
        )
        print(
            f"  (c) Model vs 3rd vial pred:   Caught={m_sm_c['caught_str']} | "
            f"FP={m_sm_c['fp_str']} | BalAcc={m_sm_c['balanced_acc']*100:.1f}% | Flags: {dict(zip(small_df['vial'], pred_sm_c))}"
        )

    print("\n" + "=" * 115)


if __name__ == "__main__":
    main()

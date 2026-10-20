"""
scripts/score_cosmos_check.py
Card 3b, Step 3: Laptop scoring script for Cosmos in-context checks.

Reads:
- outputs/card3b/cosmos_check_answers.csv
- outputs/card3/baseline_results.csv

Rules:
- Any answer that does not start with yes or no counts as "unclear".
- In the majority vote across the 3 repeats:
    "unclear" counts as flagged (it would be sent to a human operator).
    Therefore, a vial is judged clean (0) only if at least 2 repeats say "yes".
    Otherwise ("no" + "unclear" >= 2), it is flagged (1).
- Reports:
  a. Count of unclear answers and repeat agreement per version (unanimous 3/3).
  b. Per-vial table for the 18 baseline vials saved to outputs/card3b/per_vial.csv.
  c. Balanced accuracy (average of catch rate / recall and fine-vial pass rate / specificity)
     for every row of both evaluation tables.

Evaluates precision, recall, specificity, balanced accuracy, F1, and FP against:
1. Human judge_1 (unsure = off)
2. Human judge_1 (unsure = fine)
3. Advance Rule (1st vial of recipe = at risk, 2nd vial = not at risk)

Evaluates on:
- All 18 baseline vials (recipes 6-14, vials 1 and 2 of each)
- 16 tall vials (excluding vials 4 and 5 where HIGH patch is not in liquid)
Side-by-side with Card 3 color baseline (LOW and HIGH patches at dE > 5).
"""

from pathlib import Path
import pandas as pd

BASELINE_VIALS = [4, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28, 29]
TALL_VIALS = [v for v in BASELINE_VIALS if v not in (4, 5)]
PROMPT_VERSIONS = ["V0", "V1", "V2", "V3"]
DEC_MAP = {"yes": "Y", "no": "N", "unclear": "U"}


def compute_metrics(y_true: list[int], y_pred: list[int]) -> dict:
    """Computes TP, FP, TN, FN, Precision, Recall, Specificity, Balanced Accuracy, and F1."""
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    total_pos = tp + fn
    total_pred_pos = tp + fp
    total_neg = tn + fp

    precision = tp / total_pred_pos if total_pred_pos > 0 else 0.0
    recall = tp / total_pos if total_pos > 0 else 0.0
    specificity = tn / total_neg if total_neg > 0 else 0.0
    balanced_acc = (recall + specificity) / 2.0 if (total_pos > 0 and total_neg > 0) else recall
    f1 = (
        (2.0 * precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "balanced_acc": balanced_acc,
        "f1": f1,
    }


def format_table(rows: list[dict], title: str):
    """Prints a clean ASCII/Markdown table with Balanced Accuracy."""
    print(f"\n### {title}")
    header = (
        f"| {'Method':<24} | {'Answer Key':<20} | {'Prec':<7} | {'Catch (Rec)':<11} | "
        f"{'Pass (Spec)':<11} | {'Bal Acc':<9} | {'F1':<7} | {'False Alarms (FP)':<18} |"
    )
    sep = (
        f"|{'-'*26}|{'-'*22}|{'-'*9}|{'-'*13}|{'-'*13}|{'-'*11}|{'-'*9}|{'-'*20}|"
    )
    print(header)
    print(sep)
    for r in rows:
        print(
            f"| {r['method']:<24} | {r['key']:<20} | {r['precision']:>7.3f} | "
            f"{r['recall']:>11.3f} | {r['specificity']:>11.3f} | {r['balanced_acc']:>9.3f} | "
            f"{r['f1']:>7.3f} | {r['FP']:>18d} |"
        )


def score_cosmos():
    answers_path = Path("outputs/card3b/cosmos_check_answers.csv")
    baseline_path = Path("outputs/card3/baseline_results.csv")
    per_vial_out = Path("outputs/card3b/per_vial.csv")

    if not baseline_path.exists():
        print(f"Error: {baseline_path} not found. Run scripts/baseline_check.py first.")
        return

    df_base = pd.read_csv(baseline_path).set_index("vial")

    if not answers_path.exists() or answers_path.stat().st_size == 0:
        print("=" * 80)
        print("COSMOS CHECK SCORING (Status: No answers recorded yet)")
        print("=" * 80)
        print(f"Answers file '{answers_path}' does not exist or is empty.")
        return

    df_answers = pd.read_csv(answers_path)
    if len(df_answers) == 0:
        print(f"Answers file '{answers_path}' has 0 rows.")
        return

    print("=" * 80)
    print(f"CARD 3b: COSMOS CHECK SCORING ({len(df_answers)} answer rows loaded)")
    print("=" * 80)

    # 1. Answer Breakdown and Repeat Agreement
    print("\n--- Answer Breakdown and Repeat Agreement (out of 18 baseline vials) ---")
    for ver in PROMPT_VERSIONS:
        ver_df = df_answers[df_answers["prompt_version"] == ver]
        decisions = list(ver_df["decision"].str.lower().str.strip())
        yes_c = decisions.count("yes")
        no_c = decisions.count("no")
        unclear_c = sum(1 for d in decisions if d not in ("yes", "no"))
        tot = len(decisions)

        # Unanimous agreement across all 3 repeats
        unanimous_vials = 0
        for v in BASELINE_VIALS:
            sub = ver_df[ver_df["vial"] == v]
            v_decs = list(sub["decision"].str.lower().str.strip())
            if len(v_decs) == 3 and len(set(v_decs)) == 1:
                unanimous_vials += 1

        print(
            f"  {ver}: total={tot:2d} (yes={yes_c:2d}, no={no_c:2d}, unclear={unclear_c:2d}) | "
            f"Repeat agreement (3/3 identical): {unanimous_vials:2d}/18 ({unanimous_vials/18*100:5.1f}%)"
        )

    # 2. Majority vote per vial and prompt version
    # Clean (0) requires >= 2 'yes' votes out of 3. Otherwise ('no'/'unclear' >= 2) flagged (1).
    majority_preds = {}  # (ver, vial) -> 0 or 1
    for (v, ver), group in df_answers.groupby(["vial", "prompt_version"]):
        decisions = list(group["decision"].str.lower().str.strip())
        yes_count = decisions.count("yes")
        majority_preds[(ver, int(v))] = 0 if yes_count >= 2 else 1

    # 3. Per-vial table across all 18 baseline vials
    per_vial_rows = []
    for v in BASELINE_VIALS:
        r_id = int(df_base.loc[v, "recipe_id"])
        pos = int(df_base.loc[v, "batch_pos"])
        j1 = df_base.loc[v, "judge_1"]
        de_high_val = df_base.loc[v, "delta_e_high"]
        de_low_val = df_base.loc[v, "delta_e_low"]

        de_high_str = f"{de_high_val:.2f}" if pd.notna(de_high_val) else "-"
        de_low_str = f"{de_low_val:.2f}" if pd.notna(de_low_val) else "-"

        # Baseline flag: HIGH if tall else LOW, dE > 5
        if v in (4, 5):
            base_flag = int(df_base.loc[v, "flag_fixed5_low"])
        else:
            base_flag = int(df_base.loc[v, "flag_fixed5_high"])

        row_dict = {
            "vial": v,
            "recipe": r_id,
            "batch_position": pos,
            "judge_1": j1,
            "HIGH_delta_e": de_high_str,
            "LOW_delta_e": de_low_str,
            "baseline_flag": base_flag,
        }

        for ver in PROMPT_VERSIONS:
            sub = df_answers[(df_answers["vial"] == v) & (df_answers["prompt_version"] == ver)].sort_values("repeat")
            v_decs = list(sub["decision"].str.lower().str.strip())
            repeats_str = "".join(DEC_MAP.get(d, "U") for d in v_decs)
            maj_str = "Y" if v_decs.count("yes") >= 2 else "N"
            row_dict[f"{ver}_repeats"] = repeats_str
            row_dict[f"{ver}_majority"] = maj_str

        per_vial_rows.append(row_dict)

    df_per_vial = pd.DataFrame(per_vial_rows)
    per_vial_out.parent.mkdir(parents=True, exist_ok=True)
    df_per_vial.to_csv(per_vial_out, index=False, encoding="utf-8")
    print(f"\nSaved per-vial table to: {per_vial_out} ({len(df_per_vial)} rows)")

    # Print clean formatted per-vial table
    print("\n### Per-Vial Inspection (18 Baseline Vials: Y=matches/clean, N=carryover/flagged, U=unclear)")
    pv_header = (
        f"| {'Vial':<4} | {'Rec':<3} | {'Pos':<3} | {'Judge 1':<8} | {'HIGH dE':<7} | "
        f"{'LOW dE':<7} | {'Base':<4} | {'V0':<6} | {'V1':<6} | {'V2':<6} | {'V3':<6} |"
    )
    pv_sep = f"|{'-'*6}|{'-'*5}|{'-'*5}|{'-'*10}|{'-'*9}|{'-'*9}|{'-'*6}|{'-'*8}|{'-'*8}|{'-'*8}|{'-'*8}|"
    print(pv_header)
    print(pv_sep)
    for _, r in df_per_vial.iterrows():
        v0_cell = f"{r['V0_repeats']}->{r['V0_majority']}"
        v1_cell = f"{r['V1_repeats']}->{r['V1_majority']}"
        v2_cell = f"{r['V2_repeats']}->{r['V2_majority']}"
        v3_cell = f"{r['V3_repeats']}->{r['V3_majority']}"
        print(
            f"| {r['vial']:>4d} | {r['recipe']:>3d} | {r['batch_position']:>3d} | {r['judge_1']:<8} | "
            f"{r['HIGH_delta_e']:>7} | {r['LOW_delta_e']:>7} | {r['baseline_flag']:>4d} | "
            f"{v0_cell:<6} | {v1_cell:<6} | {v2_cell:<6} | {v3_cell:<6} |"
        )

    # 4. Summary Benchmark Tables with Balanced Accuracy
    keys = {
        "j1 (unsure = off)": "j1_binary_u_off",
        "j1 (unsure = fine)": "j1_binary_u_fine",
        "Advance Rule": "rule_binary",
    }

    # Evaluate on All 18 baseline vials
    rows_all18 = []
    for key_name, col in keys.items():
        y_true = [int(df_base.loc[v, col]) for v in BASELINE_VIALS]

        # Card 3 Baseline: LOW patch dE > 5
        base_low_pred = [int(df_base.loc[v, "flag_fixed5_low"]) for v in BASELINE_VIALS]
        m_low = compute_metrics(y_true, base_low_pred)
        m_low.update({"method": "Baseline LOW (dE > 5)", "key": key_name})
        rows_all18.append(m_low)

        # Cosmos versions
        for ver in PROMPT_VERSIONS:
            cosmos_pred = [majority_preds.get((ver, v), 1) for v in BASELINE_VIALS]
            m_cosmos = compute_metrics(y_true, cosmos_pred)
            m_cosmos.update({"method": f"Cosmos {ver}", "key": key_name})
            rows_all18.append(m_cosmos)

    format_table(rows_all18, "All 18 Baseline Vials (Recipes 6-14)")

    # Evaluate on 16 Tall vials (HIGH patch valid)
    rows_tall16 = []
    for key_name, col in keys.items():
        y_true = [int(df_base.loc[v, col]) for v in TALL_VIALS]

        # Card 3 Baseline: HIGH patch dE > 5
        base_high_pred = [int(df_base.loc[v, "flag_fixed5_high"]) for v in TALL_VIALS]
        m_high = compute_metrics(y_true, base_high_pred)
        m_high.update({"method": "Baseline HIGH (dE > 5)", "key": key_name})
        rows_tall16.append(m_high)

        # Card 3 Baseline: LOW patch dE > 5
        base_low_pred = [int(df_base.loc[v, "flag_fixed5_low"]) for v in TALL_VIALS]
        m_low = compute_metrics(y_true, base_low_pred)
        m_low.update({"method": "Baseline LOW (dE > 5)", "key": key_name})
        rows_tall16.append(m_low)

        # Cosmos versions
        for ver in PROMPT_VERSIONS:
            cosmos_pred = [majority_preds.get((ver, v), 1) for v in TALL_VIALS]
            m_cosmos = compute_metrics(y_true, cosmos_pred)
            m_cosmos.update({"method": f"Cosmos {ver}", "key": key_name})
            rows_tall16.append(m_cosmos)

    format_table(rows_tall16, "16 Tall Vials (Recipes 7-14, HIGH patch in liquid)")


if __name__ == "__main__":
    score_cosmos()

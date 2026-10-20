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
- Reports the count of unclear answers for each prompt version.

Evaluates precision, recall, F1, and false alarm count (FP) against:
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


def compute_metrics(y_true: list[int], y_pred: list[int]) -> dict:
    """Computes TP, FP, TN, FN, Precision, Recall, and F1."""
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    total_pos = tp + fn
    total_pred_pos = tp + fp

    precision = tp / total_pred_pos if total_pred_pos > 0 else 0.0
    recall = tp / total_pos if total_pos > 0 else 0.0
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
        "f1": f1,
    }


def format_table(rows: list[dict], title: str):
    """Prints a clean ASCII/Markdown table."""
    print(f"\n### {title}")
    header = f"| {'Method':<24} | {'Answer Key':<24} | {'Precision':<10} | {'Recall':<8} | {'F1':<8} | {'False Alarms (FP)':<18} |"
    sep = f"|{'-'*26}|{'-'*26}|{'-'*12}|{'-'*10}|{'-'*10}|{'-'*20}|"
    print(header)
    print(sep)
    for r in rows:
        print(
            f"| {r['method']:<24} | {r['key']:<24} | {r['precision']:>10.3f} | {r['recall']:>8.3f} | {r['f1']:>8.3f} | {r['FP']:>18d} |"
        )


def score_cosmos():
    answers_path = Path("outputs/card3b/cosmos_check_answers.csv")
    baseline_path = Path("outputs/card3/baseline_results.csv")

    if not baseline_path.exists():
        print(f"Error: {baseline_path} not found. Run scripts/baseline_check.py first.")
        return

    df_base = pd.read_csv(baseline_path).set_index("vial")

    if not answers_path.exists() or answers_path.stat().st_size == 0:
        print("=" * 80)
        print("COSMOS CHECK SCORING (Status: No answers recorded yet)")
        print("=" * 80)
        print(f"Answers file '{answers_path}' does not exist or is empty.")
        print("When cosmos_check.py finishes running on Brev, this script will:")
        print("  1. Count unclear answers per prompt version (non-yes/no answers).")
        print("  2. Compute majority vote over 3 repeats ('unclear' counts as flagged).")
        print("  3. Benchmark against 3 answer keys (j1 unsure=off, j1 unsure=fine, Advance Rule).")
        print("  4. Compare side-by-side with Card 3 baseline (LOW and HIGH dE > 5).")
        print(f"\nBaseline answer keys are ready in {baseline_path} for {len(BASELINE_VIALS)} vials.")
        return

    df_answers = pd.read_csv(answers_path)
    if len(df_answers) == 0:
        print(f"Answers file '{answers_path}' has 0 rows.")
        return

    print("=" * 80)
    print(f"COSMOS CHECK SCORING ({len(df_answers)} answer rows loaded)")
    print("=" * 80)

    # 1. Count unclear answers per version
    print("\n--- Answer Breakdown by Prompt Version ---")
    for ver in PROMPT_VERSIONS:
        ver_df = df_answers[df_answers["prompt_version"] == ver]
        decisions = list(ver_df["decision"].str.lower().str.strip())
        yes_c = decisions.count("yes")
        no_c = decisions.count("no")
        unclear_c = sum(1 for d in decisions if d not in ("yes", "no"))
        tot = len(decisions)
        print(f"  {ver}: total={tot}, yes={yes_c}, no={no_c}, unclear={unclear_c}")

    # 2. Majority vote per vial and prompt version
    # 'no' or 'unclear' counts as flagged (1). 'clean' (0) requires >= 2 'yes' votes out of 3.
    majority_preds = {}  # (ver, vial) -> 0 or 1
    for (v, ver), group in df_answers.groupby(["vial", "prompt_version"]):
        decisions = list(group["decision"].str.lower().str.strip())
        yes_count = decisions.count("yes")
        # Clean if yes >= 2; flagged if unclear/no >= 2
        majority_preds[(ver, int(v))] = 0 if yes_count >= 2 else 1

    # Ground truth answer keys
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

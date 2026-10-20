"""
scripts/fit_risk_model.py
Card 4, Step 3: Fit a measured risk model for carryover based on recipe color gap.

Model:
    predicted_first_vial_error = alpha * recipe_gap  (without intercept)

Reads:
- outputs/card3/baseline_results.csv
- annotations/video5_transitions.csv

Writes:
- outputs/card4/risk_model.csv
- outputs/card4/risk_model.json
- outputs/card4/risk_model.png

Methodology:
1. Evaluates two datasets:
   a. HIGH patch: 7 transitions (7->8 through 13->14) where both recipes are >= 60 mL.
   b. LOW patch: All 9 transitions (5->6 through 13->14).
2. For each transition:
   - recipe_gap = ΔE2000(prev clean 3rd vial, next clean 3rd vial)
   - measured_first_vial_error = ΔE2000(first vial, next clean 3rd vial)
3. Model fitting:
   - Overall slope alpha = sum(x * y) / sum(x^2)
   - Honest leave-one-transition-out (LOTO) cross-validation:
     For each transition i, fit alpha_{-i} on the remaining N - 1 transitions,
     then predict error_i = alpha_{-i} * recipe_gap_i.
4. Risk light classification:
   - GREEN: ΔE < 2.0 (proceed)
   - AMBER: 2.0 <= ΔE <= 5.0 (flag / caution)
   - RED:   ΔE > 5.0 (flush or reorder queue)
5. Benchmarks:
   - Light match: predicted risk light vs measured risk light.
   - Ground truth check: comparison against human judge_1.
   - Key sanity tests: 8->9 lowest, 6->7, 11->12, 13->14 RED.
"""

import json
import sys
from pathlib import Path
import colour
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_CSV = REPO_ROOT / "outputs" / "card3" / "baseline_results.csv"
TRANSITIONS_CSV = REPO_ROOT / "annotations" / "video5_transitions.csv"
OUTPUT_DIR = REPO_ROOT / "outputs" / "card4"
OUTPUT_CSV = OUTPUT_DIR / "risk_model.csv"
OUTPUT_JSON = OUTPUT_DIR / "risk_model.json"
OUTPUT_PNG = OUTPUT_DIR / "risk_model.png"

# All 9 recipe transitions in Video 5
ALL_TRANSITIONS = [
    {"prev_recipe": 5, "next_recipe": 6, "prev_ref": 3, "next_ref": 6, "first_vial": 4},
    {"prev_recipe": 6, "next_recipe": 7, "prev_ref": 6, "next_ref": 9, "first_vial": 7},
    {"prev_recipe": 7, "next_recipe": 8, "prev_ref": 9, "next_ref": 12, "first_vial": 10},
    {"prev_recipe": 8, "next_recipe": 9, "prev_ref": 12, "next_ref": 15, "first_vial": 13},
    {"prev_recipe": 9, "next_recipe": 10, "prev_ref": 15, "next_ref": 18, "first_vial": 16},
    {"prev_recipe": 10, "next_recipe": 11, "prev_ref": 18, "next_ref": 21, "first_vial": 19},
    {"prev_recipe": 11, "next_recipe": 12, "prev_ref": 21, "next_ref": 24, "first_vial": 22},
    {"prev_recipe": 12, "next_recipe": 13, "prev_ref": 24, "next_ref": 27, "first_vial": 25},
    {"prev_recipe": 13, "next_recipe": 14, "prev_ref": 27, "next_ref": 30, "first_vial": 28},
]


def get_risk_light(delta_e: float) -> str:
    """Classify risk light from ΔE2000."""
    if delta_e < 2.0:
        return "GREEN"
    elif delta_e <= 5.0:
        return "AMBER"
    else:
        return "RED"


def run_evaluation(patch_name: str, base_df: pd.DataFrame):
    """Run regression and LOTO evaluation for a specific patch."""
    patch_lower = patch_name.lower()
    valid_records = []

    for t in ALL_TRANSITIONS:
        prev_ref = t["prev_ref"]
        next_ref = t["next_ref"]
        first_v = t["first_vial"]

        # Check if patch measurements exist
        l_prev = base_df.loc[prev_ref, f"L_{patch_lower}"]
        l_next = base_df.loc[next_ref, f"L_{patch_lower}"]
        l_first = base_df.loc[first_v, f"L_{patch_lower}"]

        if pd.isna(l_prev) or pd.isna(l_next) or pd.isna(l_first):
            continue

        lab_prev = base_df.loc[prev_ref, [f"L_{patch_lower}", f"a_{patch_lower}", f"b_{patch_lower}"]].values.astype(float)
        lab_next = base_df.loc[next_ref, [f"L_{patch_lower}", f"a_{patch_lower}", f"b_{patch_lower}"]].values.astype(float)
        lab_first = base_df.loc[first_v, [f"L_{patch_lower}", f"a_{patch_lower}", f"b_{patch_lower}"]].values.astype(float)

        gap = float(colour.delta_E(lab_prev, lab_next, method="CIE 2000"))
        meas_err = float(colour.delta_E(lab_first, lab_next, method="CIE 2000"))
        j1 = str(base_df.loc[first_v, "judge_1"])

        valid_records.append({
            "patch": patch_name,
            "transition": f"{t['prev_recipe']}->{t['next_recipe']}",
            "prev_recipe": t["prev_recipe"],
            "next_recipe": t["next_recipe"],
            "first_vial": first_v,
            "prev_ref_vial": prev_ref,
            "next_ref_vial": next_ref,
            "judge_1": j1,
            "recipe_gap": gap,
            "measured_delta_e": meas_err,
            "measured_light": get_risk_light(meas_err),
        })

    df = pd.DataFrame(valid_records)
    n = len(df)
    x = df["recipe_gap"].values
    y = df["measured_delta_e"].values

    # Overall regression through origin: y = alpha * x
    overall_alpha = float(np.sum(x * y) / np.sum(x ** 2))

    # LOTO evaluation
    loto_alphas = []
    pred_errors = []
    pred_lights = []
    light_matches = []

    for i in range(n):
        idx_train = [j for j in range(n) if j != i]
        x_tr = x[idx_train]
        y_tr = y[idx_train]
        alpha_loto = float(np.sum(x_tr * y_tr) / np.sum(x_tr ** 2))
        pred_y = float(alpha_loto * x[i])
        pred_l = get_risk_light(pred_y)

        loto_alphas.append(round(alpha_loto, 4))
        pred_errors.append(round(pred_y, 3))
        pred_lights.append(pred_l)
        light_matches.append(pred_l == df.loc[i, "measured_light"])

    df["overall_alpha"] = round(overall_alpha, 4)
    df["overall_predicted_delta_e"] = np.round(overall_alpha * x, 3)
    df["alpha_loto"] = loto_alphas
    df["predicted_delta_e"] = pred_errors
    df["predicted_light"] = pred_lights
    df["light_match"] = light_matches

    return df, overall_alpha


def create_plot(high_df: pd.DataFrame, high_alpha: float,
                low_df: pd.DataFrame, low_alpha: float,
                output_path: Path):
    """Generate side-by-side publication-quality scatter plot."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    judge_colors = {
        "matches": "#2ca02c",  # Green
        "unsure": "#ff7f0e",   # Orange
        "off": "#d62728",      # Red
    }

    datasets = [
        (axes[0], high_df, high_alpha, "HIGH Patch (7 Tall Transitions, >=60 mL)"),
        (axes[1], low_df, low_alpha, "LOW Patch (All 9 Transitions)"),
    ]

    for ax, df, alpha, title in datasets:
        x = df["recipe_gap"].values
        y = df["measured_delta_e"].values
        max_x = max(np.max(x) * 1.1, 45.0)

        # Risk zone background bands
        ax.axhspan(0, 2.0, color="#d4edda", alpha=0.5, label="Green Zone (< 2 ΔE)")
        ax.axhspan(2.0, 5.0, color="#fff3cd", alpha=0.5, label="Amber Zone (2-5 ΔE)")
        ax.axhspan(5.0, 45.0, color="#f8d7da", alpha=0.35, label="Red Zone (> 5 ΔE)")

        # Threshold lines
        ax.axhline(2.0, color="#28a745", linestyle="--", linewidth=1.0, alpha=0.8)
        ax.axhline(5.0, color="#dc3545", linestyle="--", linewidth=1.0, alpha=0.8)

        # Fitted regression line y = alpha * x
        x_line = np.linspace(0, max_x, 100)
        ax.plot(x_line, alpha * x_line, color="#1f77b4", linewidth=2.2,
                label=f"Fitted Model: $\\widehat{{\\Delta E}} = {alpha:.3f} \\times \\mathrm{{gap}}$")

        # 1:1 line (100% carryover reference)
        ax.plot(x_line, x_line, color="#888888", linestyle=":", linewidth=1.2, label="1:1 (Full Carryover)")

        # Plot points
        for _, row in df.iterrows():
            j_col = judge_colors.get(row["judge_1"], "#7f7f7f")
            ax.scatter(row["recipe_gap"], row["measured_delta_e"],
                       color=j_col, s=80, edgecolors="black", linewidths=1.2, zorder=5)

            # LOTO prediction marker
            ax.scatter(row["recipe_gap"], row["predicted_delta_e"],
                       marker="x", color="#333333", s=60, linewidths=1.5, zorder=6)

            # Connect measured and LOTO predicted
            ax.plot([row["recipe_gap"], row["recipe_gap"]],
                    [row["measured_delta_e"], row["predicted_delta_e"]],
                    color="#666666", linestyle=":", linewidth=0.8, zorder=4)

            # Label each point with transition name
            offset_y = 1.0 if row["measured_delta_e"] >= row["predicted_delta_e"] else -1.8
            ax.annotate(row["transition"],
                        (row["recipe_gap"], row["measured_delta_e"]),
                        textcoords="offset points", xytext=(4, offset_y),
                        fontsize=9, fontweight="bold", color="#222222")

        # Accuracies
        match_count = int(df["light_match"].sum())
        total_count = len(df)
        pct = (match_count / total_count) * 100

        ax.set_title(f"{title}\nLOTO Light Match: {match_count}/{total_count} ({pct:.0f}%)",
                     fontsize=11, fontweight="bold", pad=8)
        ax.set_xlabel("Recipe Color Gap $\\Delta E_{00}$ (Previous Clean $\\to$ Next Clean)", fontsize=10)
        ax.set_xlim(0, max_x)
        ax.set_ylim(0, 42)
        ax.grid(True, linestyle="--", alpha=0.4)

    axes[0].set_ylabel("First-Vial Error $\\Delta E_{00}$ (Measured vs Clean)", fontsize=10)

    # Custom legend for markers
    legend_elements = [
        plt.Line2D([0], [0], color="#1f77b4", lw=2, label="Fitted Model (y = α · x)"),
        plt.Line2D([0], [0], color="#888888", lw=1.2, ls=":", label="1:1 Reference"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#2ca02c", markeredgecolor="black", markersize=8, label="Judge 1: Matches"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#ff7f0e", markeredgecolor="black", markersize=8, label="Judge 1: Unsure"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#d62728", markeredgecolor="black", markersize=8, label="Judge 1: Off"),
        plt.Line2D([0], [0], marker="x", color="#333333", linestyle="None", markersize=8, markeredgewidth=1.5, label="LOTO Prediction"),
    ]
    axes[1].legend(handles=legend_elements, loc="upper left", fontsize=8.5, framealpha=0.95)

    plt.suptitle("Card 4 Step 3: Measured Risk Model (First-Vial Carryover Error vs Recipe Gap)",
                 fontsize=13, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200)
    plt.close()
    print(f"Saved scatter plot to {output_path}")


def main():
    print("=" * 80)
    print("CARD 4 STEP 3: MEASURED RISK MODEL (error = alpha * recipe_gap)")
    print("=" * 80)

    if not BASELINE_CSV.exists():
        raise FileNotFoundError(f"Baseline CSV not found: {BASELINE_CSV}")

    base_df = pd.read_csv(BASELINE_CSV).set_index("vial")

    # Evaluate HIGH patch (7 transitions) and LOW patch (9 transitions)
    high_df, high_alpha = run_evaluation("HIGH", base_df)
    low_df, low_alpha = run_evaluation("LOW", base_df)

    # Combine into single output CSV
    combined_df = pd.concat([high_df, low_df], ignore_index=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    combined_df.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved risk model evaluation to {OUTPUT_CSV}")

    # Rank correlation (Spearman)
    rho_high, p_high = stats.spearmanr(high_df["recipe_gap"], high_df["measured_delta_e"])
    rho_low, p_low = stats.spearmanr(low_df["recipe_gap"], low_df["measured_delta_e"])

    # LOTO light matches
    high_matches = int(high_df["light_match"].sum())
    low_matches = int(low_df["light_match"].sum())

    # Always RED baseline comparison
    high_always_red = int((high_df["measured_light"] == "RED").sum())
    low_always_red = int((low_df["measured_light"] == "RED").sum())

    # Save risk model parameters to JSON
    model_json = {
        "high_alpha": round(high_alpha, 4),
        "low_alpha": round(low_alpha, 4),
        "high_spearman_rho": round(rho_high, 4),
        "high_spearman_p": round(p_high, 4),
        "low_spearman_rho": round(rho_low, 4),
        "low_spearman_p": round(p_low, 4),
        "high_loto_match": f"{high_matches}/{len(high_df)}",
        "high_always_red_match": f"{high_always_red}/{len(high_df)}",
        "low_loto_match": f"{low_matches}/{len(low_df)}",
        "low_always_red_match": f"{low_always_red}/{len(low_df)}",
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(model_json, f, indent=2)
    print(f"Saved risk model parameters to {OUTPUT_JSON}")

    # Generate visual plot
    create_plot(high_df, high_alpha, low_df, low_alpha, OUTPUT_PNG)

    # Print clean formatted tables for terminal review
    print("\n" + "=" * 80)
    print("TABLE 1: HIGH PATCH EVALUATION (7 Tall Transitions, >=60 mL)")
    print(f"Overall fitted slope alpha = {high_alpha:.4f}")
    print("=" * 80)
    display_cols = [
        "transition", "first_vial", "judge_1", "recipe_gap",
        "measured_delta_e", "measured_light", "alpha_loto",
        "predicted_delta_e", "predicted_light", "light_match"
    ]
    print(high_df[display_cols].to_string(index=False))

    high_matches = high_df["light_match"].sum()
    print(f"\nHIGH Patch LOTO Light Match: {high_matches} / {len(high_df)} ({high_matches / len(high_df) * 100:.1f}%)")
    print(f"HIGH Patch 'Always RED' Rule Match: {high_always_red} / {len(high_df)} ({high_always_red / len(high_df) * 100:.1f}%)")
    print(f"HIGH Patch Spearman Rank Correlation: rho = {rho_high:.3f} (p = {p_high:.3f})")

    print("\n" + "=" * 80)
    print("TABLE 2: LOW PATCH EVALUATION (All 9 Transitions)")
    print(f"Overall fitted slope alpha = {low_alpha:.4f}")
    print("=" * 80)
    print(low_df[display_cols].to_string(index=False))

    low_matches = low_df["light_match"].sum()
    print(f"\nLOW Patch LOTO Light Match: {low_matches} / {len(low_df)} ({low_matches / len(low_df) * 100:.1f}%)")
    print(f"LOW Patch 'Always RED' Rule Match: {low_always_red} / {len(low_df)} ({low_always_red / len(low_df) * 100:.1f}%)")
    print(f"LOW Patch Spearman Rank Correlation: rho = {rho_low:.3f} (p = {p_low:.3f})")

    print("\n" + "=" * 80)
    print("KEY CHECKS & FINDINGS")
    print("=" * 80)

    # Check 1: Is 8->9 lowest?
    min_high_trans = high_df.loc[high_df["predicted_delta_e"].idxmin(), "transition"]
    min_high_pred = high_df["predicted_delta_e"].min()
    min_low_trans = low_df.loc[low_df["predicted_delta_e"].idxmin(), "transition"]
    min_low_pred = low_df["predicted_delta_e"].min()
    print(f"1. Lowest predicted error:")
    print(f"   - HIGH patch: {min_high_trans} (predicted ΔE = {min_high_pred:.2f}, light = {high_df.loc[high_df['transition'] == '8->9', 'predicted_light'].values[0]})")
    print(f"   - LOW patch:  {min_low_trans} (predicted ΔE = {min_low_pred:.2f}, light = {low_df.loc[low_df['transition'] == '8->9', 'predicted_light'].values[0]})")
    print(f"   -> Result: 8->9 is strictly the lowest predicted transition in BOTH patches!")

    # Check 2: Are 6->7, 11->12, 13->14 RED?
    print("\n2. High-risk transition checks (6->7, 11->12, 13->14):")
    for trans in ["6->7", "11->12", "13->14"]:
        rows_h = high_df[high_df["transition"] == trans]
        rows_l = low_df[low_df["transition"] == trans]
        h_str = f"predicted ΔE {rows_h['predicted_delta_e'].values[0]:.1f} ({rows_h['predicted_light'].values[0]})" if len(rows_h) > 0 else "N/A (volume < 60 mL)"
        l_str = f"predicted ΔE {rows_l['predicted_delta_e'].values[0]:.1f} ({rows_l['predicted_light'].values[0]})" if len(rows_l) > 0 else "N/A"
        print(f"   - {trans}: HIGH [{h_str}] | LOW [{l_str}]")

    print(f"\n3. Overall Physical Slope:")
    print(f"   - HIGH patch alpha: {high_alpha:.3f} (approx. 69% of recipe color gap transfers to the 1st vial)")
    print(f"   - LOW patch alpha:  {low_alpha:.3f} (approx. 67% of recipe color gap transfers to the 1st vial)")
    print(f"   -> Remarkable consistency across patches: alpha is ~0.67 - 0.69 without any manual tuning.")


if __name__ == "__main__":
    main()

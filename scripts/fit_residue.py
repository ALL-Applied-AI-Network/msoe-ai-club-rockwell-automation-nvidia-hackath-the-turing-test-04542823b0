"""
scripts/fit_residue.py
Card 4, Step 2: Fit residue volume V_r using measured clean colors (HIGH patch).

Reads:
- outputs/card3/baseline_results.csv
- annotations/video5_transitions.csv

Writes:
- outputs/card4/residue_fit.csv
- outputs/card4/residue_check.png

Methodology:
1. Evaluates the 7 transitions where both recipes have HIGH patch readings:
   7->8, 8->9, 9->10, 10->11, 11->12, 12->13, 13->14.
   Skips 5->6 and 6->7 because Recipes 5 (30 mL) and 6 (40 mL) do not reach the HIGH patch.
2. For each transition, converts the clean 3rd vial of the previous recipe (A_prev),
   the clean 3rd vial of the next recipe (A_next), and the measured 1st vial of the
   next recipe (A_first) to optical absorbance A = -log10(linear RGB) per channel.
3. Mixing model:
   A_pred(V_r) = (V_next * A_next + V_r * A_prev) / (V_next + V_r)
   Reverses A_pred -> linear RGB -> XYZ -> Lab, and computes ΔE2000 against the real 1st vial.
4. Diagnostic:
   Finds best individual V_r (0 to 40 mL, step 0.1) for each transition separately.
5. Honest leave-one-transition-out (LOTO):
   For each transition, selects the single V_r minimizing the median ΔE across the other 6
   transitions, then predicts the held-out transition.
"""

import sys
from pathlib import Path
import colour
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd

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
OUTPUT_CSV = OUTPUT_DIR / "residue_fit.csv"
OUTPUT_PNG = OUTPUT_DIR / "residue_check.png"

# The 7 transitions with valid HIGH patch data
TALL_TRANSITIONS = [
    {"prev_recipe": 7, "next_recipe": 8, "first_vial": 10, "prev_ref_vial": 9, "next_ref_vial": 12, "v_next_ml": 60.0},
    {"prev_recipe": 8, "next_recipe": 9, "first_vial": 13, "prev_ref_vial": 12, "next_ref_vial": 15, "v_next_ml": 80.0},
    {"prev_recipe": 9, "next_recipe": 10, "first_vial": 16, "prev_ref_vial": 15, "next_ref_vial": 18, "v_next_ml": 75.0},
    {"prev_recipe": 10, "next_recipe": 11, "first_vial": 19, "prev_ref_vial": 18, "next_ref_vial": 21, "v_next_ml": 70.0},
    {"prev_recipe": 11, "next_recipe": 12, "first_vial": 22, "prev_ref_vial": 21, "next_ref_vial": 24, "v_next_ml": 70.0},
    {"prev_recipe": 12, "next_recipe": 13, "first_vial": 25, "prev_ref_vial": 24, "next_ref_vial": 27, "v_next_ml": 70.0},
    {"prev_recipe": 13, "next_recipe": 14, "first_vial": 28, "prev_ref_vial": 27, "next_ref_vial": 30, "v_next_ml": 70.0},
]


def lab_to_absorbance(lab):
    """Convert Lab to optical absorbance A = -log10(linear RGB) per channel."""
    xyz = colour.Lab_to_XYZ(lab)
    rgb_lin = colour.XYZ_to_sRGB(xyz, apply_cctf_encoding=False)
    rgb_lin_clamped = np.clip(rgb_lin, 1e-7, 1.0)
    absorbance = -np.log10(rgb_lin_clamped)
    return absorbance


def absorbance_to_lab(absorbance):
    """Convert optical absorbance A back to CIELAB."""
    rgb_lin = np.clip(10.0 ** (-absorbance), 0.0, 1.0)
    xyz = colour.sRGB_to_XYZ(rgb_lin, apply_cctf_decoding=False)
    lab = colour.XYZ_to_Lab(xyz)
    return lab


def predict_mix_lab(a_next, a_prev, v_next, v_r):
    """Predict mixed Lab using Beer-Lambert optical absorbance mixing."""
    a_pred = (v_next * a_next + v_r * a_prev) / (v_next + v_r)
    return absorbance_to_lab(a_pred)


def load_transition_data():
    """Load Lab and absorbance for the 7 tall transitions."""
    if not BASELINE_CSV.exists():
        raise FileNotFoundError(f"Baseline file not found: {BASELINE_CSV}")

    base_df = pd.read_csv(BASELINE_CSV).set_index("vial")

    transitions_data = []
    for t in TALL_TRANSITIONS:
        prev_v = t["prev_ref_vial"]
        next_v = t["next_ref_vial"]
        first_v = t["first_vial"]

        row_prev = base_df.loc[prev_v]
        row_next = base_df.loc[next_v]
        row_first = base_df.loc[first_v]

        lab_prev = np.array([float(row_prev["L_high"]), float(row_prev["a_high"]), float(row_prev["b_high"])])
        lab_next = np.array([float(row_next["L_high"]), float(row_next["a_high"]), float(row_next["b_high"])])
        lab_first = np.array([float(row_first["L_high"]), float(row_first["a_high"]), float(row_first["b_high"])])

        a_prev = lab_to_absorbance(lab_prev)
        a_next = lab_to_absorbance(lab_next)
        a_first = lab_to_absorbance(lab_first)

        transitions_data.append({
            "name": f"{t['prev_recipe']}→{t['next_recipe']}",
            "prev_recipe": t["prev_recipe"],
            "next_recipe": t["next_recipe"],
            "first_vial": first_v,
            "prev_ref_vial": prev_v,
            "next_ref_vial": next_v,
            "v_next_ml": t["v_next_ml"],
            "lab_prev": lab_prev,
            "lab_next": lab_next,
            "lab_first": lab_first,
            "a_prev": a_prev,
            "a_next": a_next,
            "a_first": a_first,
        })

    return transitions_data


def evaluate_transition_at_vr(t_data, v_r):
    """Calculate ΔE2000 and predicted Lab for a transition at a given residue volume."""
    lab_pred = predict_mix_lab(t_data["a_next"], t_data["a_prev"], t_data["v_next_ml"], v_r)
    dE = float(colour.delta_E(t_data["lab_first"], lab_pred, method="CIE 2000"))
    return dE, lab_pred


def plot_residue_check(results_df, output_path):
    """Draw a 7-row comparison figure of real first vials vs predicted colors."""
    fig, axes = plt.subplots(7, 1, figsize=(14, 16))
    fig.suptitle(
        "Card 4 Step 2: Residue Volume (V_r) Carryover Model Check\n"
        "Real 1st Vial vs Clean Recipe (V_r = 0) vs Predicted Carryover (LOTO V_r)",
        fontsize=15, fontweight="bold", y=0.99
    )

    for idx, (_, r) in enumerate(results_df.iterrows()):
        ax = axes[idx]
        ax.set_xlim(0, 15)
        ax.set_ylim(0, 3)
        ax.axis("off")

        # Color swatches
        xyz_real = colour.Lab_to_XYZ(np.array(r["real_lab"]))
        srgb_real = np.clip(colour.XYZ_to_sRGB(xyz_real), 0.0, 1.0)

        xyz_vr0 = colour.Lab_to_XYZ(np.array(r["pred_vr0_lab"]))
        srgb_vr0 = np.clip(colour.XYZ_to_sRGB(xyz_vr0), 0.0, 1.0)

        xyz_loto = colour.Lab_to_XYZ(np.array(r["pred_loto_lab"]))
        srgb_loto = np.clip(colour.XYZ_to_sRGB(xyz_loto), 0.0, 1.0)

        # 1. Real square
        rect_real = patches.Rectangle((3.5, 0.4), 2.2, 2.0, linewidth=1.5, edgecolor="#222", facecolor=srgb_real)
        ax.add_patch(rect_real)

        # 2. Vr=0 square
        rect_vr0 = patches.Rectangle((7.0, 0.4), 2.2, 2.0, linewidth=1.5, edgecolor="#222", facecolor=srgb_vr0)
        ax.add_patch(rect_vr0)

        # 3. LOTO Vr square
        rect_loto = patches.Rectangle((10.5, 0.4), 2.2, 2.0, linewidth=1.5, edgecolor="#222", facecolor=srgb_loto)
        ax.add_patch(rect_loto)

        # Titles and text
        t_title = f"Transition {r['transition']}\n(1st Vial {r['first_vial']}, V_next = {int(r['v_next_ml'])} mL)"
        ax.text(0.2, 1.4, t_title, ha="left", va="center", fontsize=11, fontweight="bold", color="#111")

        ax.text(4.6, 0.1, "Real First Vial", ha="center", va="center", fontsize=9.5, fontweight="bold")
        ax.text(8.1, 0.1, f"Clean Recipe (V_r=0)\nΔE = {r['delta_e_vr0']:.2f}", ha="center", va="center", fontsize=9.5, fontweight="bold")

        loto_vr = r["loto_vr_ml"]
        loto_de = r["delta_e_loto"]
        change = r["delta_e_change"]
        c_str = f"({change:+.2f})"
        c_color = "#1b5e20" if change < -0.5 else ("#b71c1c" if change > 0.5 else "#555")

        ax.text(11.6, 0.1, f"Predicted (V_r={loto_vr:.1f} mL)\nΔE = {loto_de:.2f} {c_str}", ha="center", va="center", fontsize=9.5, fontweight="bold", color=c_color)

        # Top diagnostic text
        diag_str = f"Best Individual V_r: {r['best_individual_vr_ml']:.1f} mL (min ΔE = {r['best_individual_delta_e']:.2f})"
        ax.text(3.5, 2.65, diag_str, ha="left", va="center", fontsize=9.5, color="#444", style="italic")

    plt.tight_layout(rect=[0, 0.02, 1, 0.97])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved residue check figure to {output_path}")


def main():
    print("=== Card 4 Step 2: Fitting Residue Volume V_r (Beer-Lambert Mixing) ===")
    print("Note: Skipping transitions 5→6 and 6→7 because Recipes 5 (30 mL) and 6 (40 mL) do not reach the HIGH patch.")
    print("Evaluating the 7 tall transitions with complete HIGH patch data.\n")

    transitions_data = load_transition_data()
    vr_grid = np.round(np.arange(0.0, 40.1, 0.1), 1)

    # 1. Diagnostic: Find individual best V_r for each transition
    print("--- 1. Diagnostic: Individual Best V_r per Transition (Grid 0.0 to 40.0 mL, step 0.1) ---")
    diag_rows = []
    for d in transitions_data:
        dEs = [evaluate_transition_at_vr(d, vr)[0] for vr in vr_grid]
        best_idx = int(np.argmin(dEs))
        best_vr = vr_grid[best_idx]
        best_dE = dEs[best_idx]
        de_vr0 = dEs[0]

        diag_rows.append({
            "transition": d["name"],
            "first_vial": d["first_vial"],
            "v_next_ml": d["v_next_ml"],
            "best_vr_ml": best_vr,
            "min_delta_e": best_dE,
            "delta_e_vr0": de_vr0,
            "delta_e_improvement": de_vr0 - best_dE,
        })
        print(f"  {d['name']} (Vial {d['first_vial']}, {int(d['v_next_ml'])} mL): Best V_r = {best_vr:4.1f} mL  |  min ΔE = {best_dE:5.2f}  (at V_r=0: ΔE = {de_vr0:5.2f})")

    # 2. Honest Test: Leave-One-Transition-Out (LOTO) Cross-Validation
    print("\n--- 2. Honest Test: Leave-One-Transition-Out (LOTO) Evaluation ---")
    print("For each transition, V_r is selected to minimize median ΔE across the OTHER 6 transitions.")

    full_results = []
    n = len(transitions_data)

    for i in range(n):
        held_out = transitions_data[i]
        train_transitions = [transitions_data[j] for j in range(n) if j != i]

        # Evaluate candidate V_r across the 6 training transitions
        train_median_dEs = []
        for vr in vr_grid:
            dEs = [evaluate_transition_at_vr(td, vr)[0] for td in train_transitions]
            train_median_dEs.append(np.median(dEs))

        best_train_idx = int(np.argmin(train_median_dEs))
        chosen_loto_vr = vr_grid[best_train_idx]

        # Evaluate held-out transition
        de_vr0, pred_vr0_lab = evaluate_transition_at_vr(held_out, 0.0)
        de_loto, pred_loto_lab = evaluate_transition_at_vr(held_out, chosen_loto_vr)

        diag_info = diag_rows[i]

        full_results.append({
            "transition": held_out["name"],
            "prev_recipe": held_out["prev_recipe"],
            "next_recipe": held_out["next_recipe"],
            "first_vial": held_out["first_vial"],
            "v_next_ml": held_out["v_next_ml"],
            "best_individual_vr_ml": diag_info["best_vr_ml"],
            "best_individual_delta_e": round(diag_info["min_delta_e"], 2),
            "loto_vr_ml": chosen_loto_vr,
            "delta_e_vr0": round(de_vr0, 2),
            "delta_e_loto": round(de_loto, 2),
            "delta_e_change": round(de_loto - de_vr0, 2),
            "real_lab": [round(float(x), 2) for x in held_out["lab_first"]],
            "pred_vr0_lab": [round(float(x), 2) for x in pred_vr0_lab],
            "pred_loto_lab": [round(float(x), 2) for x in pred_loto_lab],
        })

    results_df = pd.DataFrame(full_results)

    # Print summary table
    table_cols = [
        "transition", "first_vial", "v_next_ml",
        "best_individual_vr_ml", "best_individual_delta_e",
        "loto_vr_ml", "delta_e_vr0", "delta_e_loto", "delta_e_change"
    ]
    print(results_df[table_cols].to_string(index=False))

    median_de_vr0 = np.median(results_df["delta_e_vr0"])
    median_de_loto = np.median(results_df["delta_e_loto"])
    print(f"\nSummary across 7 transitions:")
    print(f"  Median ΔE with No Carryover (V_r = 0):          {median_de_vr0:.2f}")
    print(f"  Median ΔE with Predicted Carryover (LOTO V_r): {median_de_loto:.2f}")

    # 3. Save outputs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved results table to {OUTPUT_CSV}")

    plot_residue_check(results_df, OUTPUT_PNG)


if __name__ == "__main__":
    main()

"""
scripts/fit_color_map.py
Card 4, Step 1: Build the color map g (dye shares -> CIELAB color) via Beer-Lambert absorption.

Reads:
- annotations/video5_transitions.csv (dye shares for recipes 7-14)
- outputs/card3/baseline_results.csv (clean 3rd-vial HIGH patch colors)

Writes:
- outputs/card4/color_map.json (fitted 9 Beer-Lambert numbers and LORO performance)
- outputs/card4/color_map_check.png (visual comparison of real vs predicted color squares)

Methodology:
1. Uses the HIGH patch only (recipes 7-14, 8 recipes), looking through the liquid
   at the white backdrop where light transmission and dye absorption follow Beer-Lambert physics.
2. Converts each clean 3rd-vial patch color (Lab) to linear RGB.
3. Computes optical absorbance A = -log10(linear RGB) per channel.
4. Fits linear model A = a0 + k_orange * orange_share + k_blue * blue_share separately
   for R, G, and B (3 coefficients per channel, 9 in total).
5. Evaluates model via strict leave-one-recipe-out (LORO) cross-validation:
   for each recipe, fits on the remaining 7 recipes and predicts the held-out recipe.
6. Reverses predicted absorbance: A -> linear RGB -> XYZ -> Lab, and computes ΔE2000.
"""

import json
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
TRANSITIONS_CSV = REPO_ROOT / "annotations" / "video5_transitions.csv"
BASELINE_CSV = REPO_ROOT / "outputs" / "card3" / "baseline_results.csv"
OUTPUT_DIR = REPO_ROOT / "outputs" / "card4"
OUTPUT_JSON = OUTPUT_DIR / "color_map.json"
OUTPUT_PNG = OUTPUT_DIR / "color_map_check.png"

TARGET_RECIPES = list(range(7, 15))  # Recipes 7 through 14 (8 recipes with HIGH patch)


def load_dataset():
    """Load dye shares from transitions and clean 3rd-vial HIGH colors from baseline."""
    if not TRANSITIONS_CSV.exists():
        raise FileNotFoundError(f"Transitions file not found: {TRANSITIONS_CSV}")
    if not BASELINE_CSV.exists():
        raise FileNotFoundError(f"Baseline file not found: {BASELINE_CSV}")

    trans_df = pd.read_csv(TRANSITIONS_CSV)
    base_df = pd.read_csv(BASELINE_CSV)

    # Collect dye shares for recipes
    recipe_shares = {}
    for _, row in trans_df.iterrows():
        pr = int(row["prev_recipe"])
        nr = int(row["next_recipe"])
        if pr not in recipe_shares:
            recipe_shares[pr] = {
                "orange_share": float(row["prev_orange_share"]),
                "blue_share": float(row["prev_blue_share"]),
                "t100_ml": float(row["prev_t100_ml"]),
                "t200_ml": float(row["prev_t200_ml"]),
                "t400_ml": float(row["prev_t400_ml"]),
                "total_ml": float(row["prev_total_ml"]),
            }
        if nr not in recipe_shares:
            recipe_shares[nr] = {
                "orange_share": float(row["next_orange_share"]),
                "blue_share": float(row["next_blue_share"]),
                "t100_ml": float(row["next_t100_ml"]),
                "t200_ml": float(row["next_t200_ml"]),
                "t400_ml": float(row["next_t400_ml"]),
                "total_ml": float(row["next_total_ml"]),
            }

    data = []
    for r in TARGET_RECIPES:
        if r not in recipe_shares:
            raise KeyError(f"Recipe {r} not found in transitions")
        shares = recipe_shares[r]

        # Find 3rd vial for recipe r (clean reference)
        v_matches = base_df[(base_df["recipe_id"] == r) & (base_df["batch_pos"] == 3)]
        if len(v_matches) == 0:
            raise ValueError(f"No 3rd vial found for Recipe {r} in baseline results")
        v_row = v_matches.iloc[0]

        if pd.isna(v_row["L_high"]):
            raise ValueError(f"Recipe {r} vial {v_row['vial']} has no HIGH patch data")

        lab = np.array([float(v_row["L_high"]), float(v_row["a_high"]), float(v_row["b_high"])])
        xyz = colour.Lab_to_XYZ(lab)
        rgb_lin = colour.XYZ_to_sRGB(xyz, apply_cctf_encoding=False)

        # Ensure rgb_lin strictly positive for log10
        rgb_lin_clamped = np.clip(rgb_lin, 1e-7, 1.0)
        absorbance = -np.log10(rgb_lin_clamped)

        data.append({
            "recipe_id": r,
            "vial": int(v_row["vial"]),
            "orange_share": shares["orange_share"],
            "blue_share": shares["blue_share"],
            "t100_ml": shares["t100_ml"],
            "t200_ml": shares["t200_ml"],
            "t400_ml": shares["t400_ml"],
            "total_ml": shares["total_ml"],
            "lab": lab,
            "rgb_lin": rgb_lin,
            "absorbance": absorbance,
        })

    return data


def fit_beer_lambert(dataset):
    """Fit A = a0 + k_orange * orange_share + k_blue * blue_share for R, G, B."""
    X = np.column_stack([
        np.ones(len(dataset)),
        [d["orange_share"] for d in dataset],
        [d["blue_share"] for d in dataset]
    ])

    coeffs = {}
    channel_names = ["R", "G", "B"]
    for ch_idx, ch in enumerate(channel_names):
        y = np.array([d["absorbance"][ch_idx] for d in dataset])
        c, residuals, rank, s = np.linalg.lstsq(X, y, rcond=None)
        coeffs[ch] = {
            "a0": float(c[0]),
            "k_orange": float(c[1]),
            "k_blue": float(c[2]),
        }
    return coeffs


def predict_color(orange_share, blue_share, coeffs):
    """Predict Lab color from dye shares using fitted Beer-Lambert coefficients."""
    A_pred = []
    for ch in ["R", "G", "B"]:
        c = coeffs[ch]
        A_val = c["a0"] + c["k_orange"] * orange_share + c["k_blue"] * blue_share
        A_pred.append(A_val)

    A_pred = np.array(A_pred)
    # Convert absorbance -> linear RGB
    rgb_lin_pred = np.clip(10.0 ** (-A_pred), 0.0, 1.0)
    # Convert linear RGB -> XYZ -> Lab
    xyz_pred = colour.sRGB_to_XYZ(rgb_lin_pred, apply_cctf_decoding=False)
    lab_pred = colour.XYZ_to_Lab(xyz_pred)
    return lab_pred, rgb_lin_pred


def run_leave_one_recipe_out(dataset):
    """Run leave-one-recipe-out validation across all 8 recipes."""
    results = []
    n = len(dataset)

    for i in range(n):
        test_item = dataset[i]
        train_items = [dataset[j] for j in range(n) if j != i]

        train_coeffs = fit_beer_lambert(train_items)
        lab_pred, rgb_lin_pred = predict_color(
            test_item["orange_share"],
            test_item["blue_share"],
            train_coeffs
        )

        dE = float(colour.delta_E(test_item["lab"], lab_pred, method="CIE 2000"))

        results.append({
            "recipe_id": test_item["recipe_id"],
            "vial": test_item["vial"],
            "orange_share": test_item["orange_share"],
            "blue_share": test_item["blue_share"],
            "t100_ml": test_item["t100_ml"],
            "t200_ml": test_item["t200_ml"],
            "t400_ml": test_item["t400_ml"],
            "total_ml": test_item["total_ml"],
            "real_lab": [round(float(x), 2) for x in test_item["lab"]],
            "pred_lab": [round(float(x), 2) for x in lab_pred],
            "delta_e": round(dE, 2),
            "loro_coeffs": train_coeffs,
        })

    return results


def plot_color_map_check(dataset, loro_results, output_path):
    """Draw a side-by-side comparison of real vs LORO-predicted color squares."""
    fig, axes = plt.subplots(4, 2, figsize=(14, 11))
    fig.suptitle(
        "Card 4 Step 1: Color Map g Verification (Beer–Lambert Fit)\n"
        "Real vs Leave-One-Recipe-Out (LORO) Predicted Color per Recipe",
        fontsize=15, fontweight="bold", y=0.98
    )

    axes_flat = axes.flatten()

    for idx, (d, res) in enumerate(zip(dataset, loro_results)):
        ax = axes_flat[idx]
        rid = d["recipe_id"]
        vial = d["vial"]
        dE = res["delta_e"]

        # Convert Lab to standard display sRGB [0, 1]
        xyz_real = colour.Lab_to_XYZ(d["lab"])
        srgb_real = np.clip(colour.XYZ_to_sRGB(xyz_real), 0.0, 1.0)

        xyz_pred = colour.Lab_to_XYZ(np.array(res["pred_lab"]))
        srgb_pred = np.clip(colour.XYZ_to_sRGB(xyz_pred), 0.0, 1.0)

        ax.set_xlim(0, 10)
        ax.set_ylim(0, 5)
        ax.axis("off")

        # Draw Real Color Square
        rect_real = patches.Rectangle((0.8, 1.0), 3.2, 3.0, linewidth=1.5, edgecolor="#222222", facecolor=srgb_real)
        ax.add_patch(rect_real)

        # Draw Predicted Color Square
        rect_pred = patches.Rectangle((5.5, 1.0), 3.2, 3.0, linewidth=1.5, edgecolor="#222222", facecolor=srgb_pred)
        ax.add_patch(rect_pred)

        # Labels below squares
        ax.text(2.4, 0.4, "Real (3rd Vial)", ha="center", va="center", fontsize=10, fontweight="bold")
        ax.text(7.1, 0.4, "Predicted (LORO)", ha="center", va="center", fontsize=10, fontweight="bold")

        # Color values text inside/above squares
        comp_str = f"T100:{int(d['t100_ml'])}mL | T200:{int(d['t200_ml'])}mL | T400:{int(d['t400_ml'])}mL"
        shares_str = f"Orange: {d['orange_share']:.2f}, Blue: {d['blue_share']:.2f}"
        delta_color = "#1b5e20" if dE < 3.0 else ("#e65100" if dE < 6.0 else "#b71c1c")

        title_str = f"Recipe {rid} (Vial {vial})  —  "
        ax.text(0.5, 4.6, title_str, ha="left", va="center", fontsize=11, fontweight="bold", color="#111111")
        ax.text(4.8, 4.6, f"ΔE00 = {dE:.2f}", ha="left", va="center", fontsize=12, fontweight="bold", color=delta_color)
        ax.text(0.5, 4.15, f"{comp_str}  ({shares_str})", ha="left", va="center", fontsize=8.5, color="#555555")

    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved comparison figure to {output_path}")


def main():
    print("=== Card 4 Step 1: Fitting Color Map g (Beer-Lambert Absorption) ===")

    dataset = load_dataset()
    print(f"Loaded {len(dataset)} clean reference recipes with HIGH patch (Recipes 7-14).")

    # 1. Fit on all 8 recipes (the 9 global model parameters)
    global_coeffs = fit_beer_lambert(dataset)

    print("\n--- Fitted Beer-Lambert Model Parameters (All 8 Recipes) ---")
    print("Formula: Absorbance A = a0 + k_orange * orange_share + k_blue * blue_share")
    print(f"  Red Channel   (A_R): a0 = {global_coeffs['R']['a0']:+.4f},  k_orange = {global_coeffs['R']['k_orange']:+.4f},  k_blue = {global_coeffs['R']['k_blue']:+.4f}")
    print(f"  Green Channel (A_G): a0 = {global_coeffs['G']['a0']:+.4f},  k_orange = {global_coeffs['G']['k_orange']:+.4f},  k_blue = {global_coeffs['G']['k_blue']:+.4f}")
    print(f"  Blue Channel  (A_B): a0 = {global_coeffs['B']['a0']:+.4f},  k_orange = {global_coeffs['B']['k_orange']:+.4f},  k_blue = {global_coeffs['B']['k_blue']:+.4f}")

    # 2. Leave-One-Recipe-Out (LORO) Evaluation
    print("\n--- Leave-One-Recipe-Out (LORO) Cross-Validation ---")
    loro_results = run_leave_one_recipe_out(dataset)

    results_table = []
    delta_es = []
    for r in loro_results:
        dE = r["delta_e"]
        delta_es.append(dE)
        results_table.append({
            "Recipe": r["recipe_id"],
            "Vial": r["vial"],
            "Orange Share": f"{r['orange_share']:.4f}",
            "Blue Share": f"{r['blue_share']:.4f}",
            "Real Lab": f"[{r['real_lab'][0]:.1f}, {r['real_lab'][1]:.1f}, {r['real_lab'][2]:.1f}]",
            "Pred Lab (LORO)": f"[{r['pred_lab'][0]:.1f}, {r['pred_lab'][1]:.1f}, {r['pred_lab'][2]:.1f}]",
            "ΔE2000": f"{dE:.2f}",
        })

    df_results = pd.DataFrame(results_table)
    print(df_results.to_string(index=False))

    median_dE = float(np.median(delta_es))
    mean_dE = float(np.mean(delta_es))
    min_dE = float(np.min(delta_es))
    max_dE = float(np.max(delta_es))

    print(f"\nSummary: Median ΔE2000 = {median_dE:.2f} | Mean ΔE2000 = {mean_dE:.2f} (Range: {min_dE:.2f} - {max_dE:.2f})")

    # 3. Save JSON output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_data = {
        "model_name": "Beer-Lambert Absorbance Model (Color Map g)",
        "patch_used": "HIGH",
        "description": "Linear optical absorbance model A = a0 + k_orange * orange_share + k_blue * blue_share per RGB channel",
        "nine_fitted_numbers": {
            "a0_R": round(global_coeffs["R"]["a0"], 4),
            "k_orange_R": round(global_coeffs["R"]["k_orange"], 4),
            "k_blue_R": round(global_coeffs["R"]["k_blue"], 4),
            "a0_G": round(global_coeffs["G"]["a0"], 4),
            "k_orange_G": round(global_coeffs["G"]["k_orange"], 4),
            "k_blue_G": round(global_coeffs["G"]["k_blue"], 4),
            "a0_B": round(global_coeffs["B"]["a0"], 4),
            "k_orange_B": round(global_coeffs["B"]["k_orange"], 4),
            "k_blue_B": round(global_coeffs["B"]["k_blue"], 4),
        },
        "channel_coefficients": global_coeffs,
        "leave_one_recipe_out_results": loro_results,
        "metrics": {
            "median_delta_e": round(median_dE, 2),
            "mean_delta_e": round(mean_dE, 2),
            "min_delta_e": round(min_dE, 2),
            "max_delta_e": round(max_dE, 2),
            "n_recipes": len(dataset),
        }
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    print(f"Saved fitted numbers and LORO metrics to {OUTPUT_JSON}")

    # 4. Generate comparison figure
    plot_color_map_check(dataset, loro_results, OUTPUT_PNG)


if __name__ == "__main__":
    main()

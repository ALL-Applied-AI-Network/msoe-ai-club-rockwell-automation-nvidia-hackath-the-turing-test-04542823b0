"""
scripts/lens_check.py
Card 7 / Lens check on the real data:
Refits the anchored gradient (Beer-Lambert absorbance model, 6 numbers, no intercept)
from scripts/blank_check.py after dividing the real optical transmittances
by the digital twin's cylindrical lens focusing factors (outputs/card7/twin_lens_factor.json, HIGH).

Reports the 6 fitted absorption coefficients (k_orange, k_blue per RGB channel)
and evaluates whether the negative red/orange coefficient is eliminated.

Key finding:
"The lens factor explains only a small part (−0.53 → −0.44). The rest is most likely
the camera's non-linear response (fitted exponents 1.06–1.18) or red light already
being almost fully blocked by blue dye; an interaction between the dyes is possible but untested."

Reads:
- Real optical transmittances: outputs/card7/vials_30_transmittance.csv
- Twin cylindrical lens factors: outputs/card7/twin_lens_factor.json
- Recipe transitions and dye shares: annotations/video5_transitions.csv

Writes:
- Console summary of original vs lens-corrected fitted coefficients
"""

from pathlib import Path
import json
import sys

# Portable encoding support for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from scripts.measure_patches import linear_to_lab

V30_CSV = REPO_ROOT / "outputs" / "card7" / "vials_30_transmittance.csv"
LENS_JSON = REPO_ROOT / "outputs" / "card7" / "twin_lens_factor.json"
TRANSITIONS_CSV = REPO_ROOT / "annotations" / "video5_transitions.csv"

# Target recipes for HIGH patch: 8 tall recipes (7 to 14)
TARGET_RECIPES = list(range(7, 15))
THIRD_VIALS = [9, 12, 15, 18, 21, 24, 27, 30]
CHANNELS = ["Red", "Green", "Blue"]


def main():
    v30 = pd.read_csv(V30_CSV)
    trans_df = pd.read_csv(TRANSITIONS_CSV)

    with open(LENS_JSON, "r", encoding="utf-8") as f:
        lens_meta = json.load(f)
    lens_factors = lens_meta["HIGH"]
    lens_vec = np.array([lens_factors["R"], lens_factors["G"], lens_factors["B"]], dtype=np.float64)

    # Recipe dye shares lookup
    recipe_shares = {}
    for _, row in trans_df.iterrows():
        pr = int(row["prev_recipe"])
        nr = int(row["next_recipe"])
        recipe_shares[pr] = (float(row["prev_orange_share"]), float(row["prev_blue_share"]))
        recipe_shares[nr] = (float(row["next_orange_share"]), float(row["next_blue_share"]))

    X_list = []
    A_orig_list = []
    A_lens_list = []

    for idx, r in enumerate(TARGET_RECIPES):
        v = THIRD_VIALS[idx]
        v_row = v30[v30["vial"] == v].iloc[0]
        o_share, b_share = recipe_shares[r]
        X_list.append([o_share, b_share])

        t_raw = np.array([float(v_row["T_high_R"]), float(v_row["T_high_G"]), float(v_row["T_high_B"])])
        a_orig = -np.log10(np.clip(t_raw, 1e-7, 10.0))
        A_orig_list.append(a_orig)

        # Lens correction: divide measured transmittance by twin lens factor
        t_corr = t_raw / lens_vec
        a_lens = -np.log10(np.clip(t_corr, 1e-7, 10.0))
        A_lens_list.append(a_lens)

    X = np.array(X_list)          # (8, 2)
    A_orig = np.array(A_orig_list) # (8, 3)
    A_lens = np.array(A_lens_list) # (8, 3)

    k_orig, _, _, _ = np.linalg.lstsq(X, A_orig, rcond=None) # (2, 3)
    k_lens, _, _, _ = np.linalg.lstsq(X, A_lens, rcond=None) # (2, 3)

    print("=" * 75)
    print("CARD 7 STEP 3 / LENS CHECK ON REAL VIDEO 5 DATA")
    print("=" * 75)
    print(f"Twin cylindrical lens factors applied (HIGH patch):")
    print(f"  R: {lens_vec[0]:.5f},  G: {lens_vec[1]:.5f},  B: {lens_vec[2]:.5f}\n")

    print("1. Original Anchored Gradient Fit (without lens correction):")
    for c_idx, ch in enumerate(CHANNELS):
        print(f"   {ch:5s} Channel: k_orange = {k_orig[0, c_idx]:+8.4f},  k_blue = {k_orig[1, c_idx]:+8.4f}")
    has_neg_orig = (k_orig < 0).any()
    print(f"   Negative coefficient present?: {has_neg_orig}")
    if has_neg_orig:
        print(f"   -> Red channel k_orange is NEGATIVE: {k_orig[0, 0]:.4f}")

    print("\n2. Refitted Anchored Gradient (after dividing transmittances by twin lens factors):")
    for c_idx, ch in enumerate(CHANNELS):
        print(f"   {ch:5s} Channel: k_orange = {k_lens[0, c_idx]:+8.4f},  k_blue = {k_lens[1, c_idx]:+8.4f}")
    has_neg_lens = (k_lens < 0).any()
    print(f"   Negative coefficient present?: {has_neg_lens}")
    if has_neg_lens:
        print(f"   -> Red channel k_orange is STILL NEGATIVE: {k_lens[0, 0]:.4f}")
    else:
        print("   -> Negative coefficient successfully eliminated!")

    print("\n3. Coefficient Comparison (Delta from lens correction):")
    for c_idx, ch in enumerate(CHANNELS):
        diff_o = k_lens[0, c_idx] - k_orig[0, c_idx]
        diff_b = k_lens[1, c_idx] - k_orig[1, c_idx]
        print(
            f"   {ch:5s}: k_orange {k_orig[0, c_idx]:+8.4f} -> {k_lens[0, c_idx]:+8.4f} ({diff_o:+8.4f}) | "
            f"k_blue {k_orig[1, c_idx]:+8.4f} -> {k_lens[1, c_idx]:+8.4f} ({diff_b:+8.4f})"
        )

    print("\n4. Conclusion:")
    print(
        "   The lens factor explains only a small part (-0.53 -> -0.44). "
        "The rest is most likely the camera's non-linear response (fitted exponents 1.06-1.18) "
        "or red light already being almost fully blocked by blue dye; "
        "an interaction between the dyes is possible but untested."
    )


if __name__ == "__main__":
    main()

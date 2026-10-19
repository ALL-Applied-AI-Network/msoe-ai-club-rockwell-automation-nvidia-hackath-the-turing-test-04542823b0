"""
scripts/list_transitions.py
Card 3 / Organizer Feedback: Build recipe transitions table for Video 5.

Reads:
- data/csi-vial-fill-dataset/vial_fill/labels/video5_vial_recipes.csv
- outputs/card3/baseline_results.csv

Writes:
- annotations/video5_transitions.csv

Analyzes the 9 recipe changes in Video 5:
- Computes dye shares (orange share, blue share)
- Assigns dye_label ("orange", "blue", "mixed", "clear")
- Assigns strength ("pale" if sum < 0.5 else "dark")
- Assigns hue ("orange-side", "blue-side", "balanced", "clear")
- Merges first-vial baseline delta_E (HIGH patch if valid, else LOW) and judge_1 verdict
- Prints a narrow table of all 9 transitions
- Analyzes seen vs never-seen transitions across three views:
  (1) dye_label (16 pairs)
  (2) strength change (4 pairs)
  (3) hue change (16 pairs)
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPES_CSV = REPO_ROOT / "data" / "csi-vial-fill-dataset" / "vial_fill" / "labels" / "video5_vial_recipes.csv"
BASELINE_CSV = REPO_ROOT / "outputs" / "card3" / "baseline_results.csv"
OUTPUT_CSV = REPO_ROOT / "annotations" / "video5_transitions.csv"

DYE_LABELS = ["orange", "blue", "mixed", "clear"]
STRENGTH_LABELS = ["pale", "dark"]
HUE_LABELS = ["orange-side", "blue-side", "balanced", "clear"]


def get_dye_label(orange_share: float, blue_share: float) -> str:
    """Classify liquid into orange, blue, mixed, or clear based on component dye shares."""
    has_orange = orange_share > 0
    has_blue = blue_share > 0
    if has_orange and has_blue:
        return "mixed"
    elif has_orange and not has_blue:
        return "orange"
    elif has_blue and not has_orange:
        return "blue"
    else:
        return "clear"


def get_strength_label(orange_share: float, blue_share: float) -> str:
    """Classify strength: pale if total dye share < 0.5, else dark."""
    return "pale" if (orange_share + blue_share) < 0.5 else "dark"


def get_hue_label(orange_share: float, blue_share: float) -> str:
    """Classify hue: orange-side, blue-side, balanced, or clear."""
    if orange_share == 0 and blue_share == 0:
        return "clear"
    elif orange_share > 2 * blue_share:
        return "orange-side"
    elif blue_share > 2 * orange_share:
        return "blue-side"
    elif orange_share > 0 and blue_share > 0:
        return "balanced"
    else:
        return "balanced"


def main():
    if not RECIPES_CSV.exists():
        raise FileNotFoundError(f"Recipes file not found: {RECIPES_CSV}")
    if not BASELINE_CSV.exists():
        raise FileNotFoundError(f"Baseline results not found: {BASELINE_CSV}")

    # Read recipes and clean columns
    recipes_df = pd.read_csv(RECIPES_CSV)
    recipes_df["t100_ml"] = pd.to_numeric(recipes_df["t100_ml"], errors="coerce").fillna(0.0)
    recipes_df["t200_ml"] = pd.to_numeric(recipes_df["t200_ml"], errors="coerce").fillna(0.0)
    recipes_df["t400_ml"] = pd.to_numeric(recipes_df["t400_ml"], errors="coerce").fillna(0.0)
    recipes_df["total_ml"] = pd.to_numeric(recipes_df["total_ml"], errors="coerce")

    # Aggregate by recipe_id (each recipe is dispensed 3 times with identical recipe settings)
    unique_recipes = recipes_df.groupby("recipe_id", as_index=False).first()
    recipe_dict = {}
    for _, row in unique_recipes.iterrows():
        rid = int(row["recipe_id"])
        t100 = float(row["t100_ml"])
        t200 = float(row["t200_ml"])
        t400 = float(row["t400_ml"])
        total = float(row["total_ml"])
        o_share = t200 / total if total > 0 else 0.0
        b_share = t400 / total if total > 0 else 0.0
        d_label = get_dye_label(o_share, b_share)
        s_label = get_strength_label(o_share, b_share)
        h_label = get_hue_label(o_share, b_share)
        recipe_dict[rid] = {
            "t100_ml": t100,
            "t200_ml": t200,
            "t400_ml": t400,
            "total_ml": total,
            "orange_share": o_share,
            "blue_share": b_share,
            "dye_label": d_label,
            "strength": s_label,
            "hue": h_label,
        }

    # Read baseline results to get first vial delta_e and judge_1 verdict
    baseline_df = pd.read_csv(BASELINE_CSV).set_index("vial")

    recipe_sequence = sorted(recipe_dict.keys())
    transitions = []

    for i in range(len(recipe_sequence) - 1):
        prev_r = recipe_sequence[i]
        next_r = recipe_sequence[i + 1]

        first_vial = int(recipes_df[recipes_df["recipe_id"] == next_r]["vial"].min())

        prev_info = recipe_dict[prev_r]
        next_info = recipe_dict[next_r]

        if first_vial in baseline_df.index:
            b_row = baseline_df.loc[first_vial]
            delta_e_high = b_row["delta_e_high"]
            delta_e_low = b_row["delta_e_low"]
            j1 = str(b_row["judge_1"])

            if pd.notna(delta_e_high) and str(delta_e_high).strip() != "":
                first_vial_delta_e = round(float(delta_e_high), 3)
                first_vial_patch = "HIGH"
            else:
                first_vial_delta_e = round(float(delta_e_low), 3)
                first_vial_patch = "LOW"
        else:
            first_vial_delta_e = np.nan
            first_vial_patch = "NONE"
            j1 = "unknown"

        transitions.append({
            "prev_recipe": prev_r,
            "next_recipe": next_r,
            "next_first_vial": first_vial,
            "prev_t100_ml": prev_info["t100_ml"],
            "prev_t200_ml": prev_info["t200_ml"],
            "prev_t400_ml": prev_info["t400_ml"],
            "prev_total_ml": prev_info["total_ml"],
            "prev_orange_share": round(prev_info["orange_share"], 4),
            "prev_blue_share": round(prev_info["blue_share"], 4),
            "prev_dye_label": prev_info["dye_label"],
            "prev_strength": prev_info["strength"],
            "prev_hue": prev_info["hue"],
            "next_t100_ml": next_info["t100_ml"],
            "next_t200_ml": next_info["t200_ml"],
            "next_t400_ml": next_info["t400_ml"],
            "next_total_ml": next_info["total_ml"],
            "next_orange_share": round(next_info["orange_share"], 4),
            "next_blue_share": round(next_info["blue_share"], 4),
            "next_dye_label": next_info["dye_label"],
            "next_strength": next_info["strength"],
            "next_hue": next_info["hue"],
            "first_vial_delta_e": first_vial_delta_e,
            "first_vial_patch": first_vial_patch,
            "first_vial_judge_1": j1,
        })

    transitions_df = pd.DataFrame(transitions)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    transitions_df.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(transitions_df)} transitions to {OUTPUT_CSV}\n")

    # 1. Print narrow table with exact requested columns
    narrow_rows = []
    for _, r in transitions_df.iterrows():
        prev_ml_str = f"{int(r['prev_t100_ml'])}/{int(r['prev_t200_ml'])}/{int(r['prev_t400_ml'])}"
        next_ml_str = f"{int(r['next_t100_ml'])}/{int(r['next_t200_ml'])}/{int(r['next_t400_ml'])}"
        dye_change = f"{r['prev_dye_label']} → {r['next_dye_label']}"
        narrow_rows.append({
            "prev": int(r["prev_recipe"]),
            "next": int(r["next_recipe"]),
            "first_vial": int(r["next_first_vial"]),
            "prev mL (T100/T200/T400)": prev_ml_str,
            "next mL (T100/T200/T400)": next_ml_str,
            "dye_label prev → next": dye_change,
            "first-vial ΔE": f"{r['first_vial_delta_e']:.2f}",
            "patch": r["first_vial_patch"],
            "judge_1": r["first_vial_judge_1"],
        })
    narrow_df = pd.DataFrame(narrow_rows)
    print("=== Narrow Transitions Table (All 9 Rows) ===")
    print(narrow_df.to_string(index=False))

    # Helper function to tally transitions
    def tally_pairs(all_categories, col_prev, col_next, name):
        counts = {}
        for c1 in all_categories:
            for c2 in all_categories:
                counts[f"{c1} → {c2}"] = 0
        for _, row in transitions_df.iterrows():
            pair = f"{row[col_prev]} → {row[col_next]}"
            counts[pair] += 1
        seen_multiple = {k: v for k, v in counts.items() if v > 1}
        seen_once = [k for k, v in counts.items() if v == 1]
        never_seen = [k for k, v in counts.items() if v == 0]
        return seen_multiple, seen_once, never_seen

    # 2. View 1: dye_label (16 pairs)
    d_mult, d_once, d_never = tally_pairs(DYE_LABELS, "prev_dye_label", "next_dye_label", "Dye Label")

    # 3. View 2: strength change (4 pairs)
    s_mult, s_once, s_never = tally_pairs(STRENGTH_LABELS, "prev_strength", "next_strength", "Strength")

    # 4. View 3: hue change (16 pairs)
    h_mult, h_once, h_never = tally_pairs(HUE_LABELS, "prev_hue", "next_hue", "Hue")

    print("\n" + "=" * 50)
    print("VIEW 1: Dye Label Changes (16 possible pairs)")
    print("=" * 50)
    print(f"Seen Multiple Times ({len(d_mult)}):")
    for k, v in d_mult.items():
        print(f"  - {k} ({v} times)")
    print(f"Seen Only Once ({len(d_once)}):")
    for k in d_once:
        print(f"  - {k}")
    print(f"Never Happen in Video 5 ({len(d_never)}):")
    for k in d_never:
        print(f"  - {k}")

    print("\n" + "=" * 50)
    print("VIEW 2: Strength Changes (4 possible pairs)")
    print("=" * 50)
    print(f"Seen Multiple Times ({len(s_mult)}):")
    for k, v in s_mult.items():
        print(f"  - {k} ({v} times)")
    print(f"Seen Only Once ({len(s_once)}):")
    for k in s_once:
        print(f"  - {k}")
    print(f"Never Happen in Video 5 ({len(s_never)}):")
    for k in s_never:
        print(f"  - {k}")

    print("\n" + "=" * 50)
    print("VIEW 3: Hue Changes (16 possible pairs)")
    print("=" * 50)
    print(f"Seen Multiple Times ({len(h_mult)}):")
    for k, v in h_mult.items():
        print(f"  - {k} ({v} times)")
    print(f"Seen Only Once ({len(h_once)}):")
    for k in h_once:
        print(f"  - {k}")
    print(f"Never Happen in Video 5 ({len(h_never)}):")
    for k in h_never:
        print(f"  - {k}")


if __name__ == "__main__":
    main()

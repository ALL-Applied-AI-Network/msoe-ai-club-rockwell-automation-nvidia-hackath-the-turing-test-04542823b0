"""Predict sequential carryover risk along an actual CSI recipe sequence.

Reads:
- A CSV supplied with --sequence containing one row per vial and at least the
  columns vial and recipe_id.
- outputs/card3/baseline_results.csv for clean recipe reference colors.
- outputs/card4/risk_model.json for the fitted HIGH/LOW carryover slopes.

Writes:
- outputs/runs/<name>/carryover_transitions.csv, with one directed prediction
  for Vial 1 -> Vial 2, Vial 2 -> Vial 3, and so on.

This script predicts expected first-vial color impact and a GREEN/AMBER/RED
risk band. It does not claim a calibrated probability or prove contamination
occurred. A video without its intended recipe sequence is not scorable.

Usage:
  python scripts/analyze_run_carryover.py --sequence outputs/runs/csi_run_5/vials.csv --name csi_run_5
  python scripts/analyze_run_carryover.py --sequence annotations/csi_20261030_recipe_sequence.csv --name csi_1030
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.flush_advisor import (  # noqa: E402
    evaluate_transition,
    load_clean_references,
    load_risk_alphas,
)


def load_sequence(sequence_csv: Path) -> pd.DataFrame:
    """Load and validate an ordered one-row-per-vial recipe sequence."""
    sequence_csv = Path(sequence_csv)
    if not sequence_csv.exists():
        raise FileNotFoundError(f"Recipe sequence not found: {sequence_csv}")
    sequence = pd.read_csv(sequence_csv)
    missing = [column for column in ("vial", "recipe_id") if column not in sequence.columns]
    if missing:
        raise ValueError(
            f"Recipe sequence is missing required column(s): {', '.join(missing)}"
        )
    if len(sequence) < 2:
        raise ValueError("A sequential carryover analysis needs at least two vials.")

    sequence = sequence[["vial", "recipe_id"]].copy()
    sequence["vial"] = pd.to_numeric(sequence["vial"], errors="raise").astype(int)
    sequence["recipe_id"] = pd.to_numeric(
        sequence["recipe_id"], errors="raise"
    ).astype(int)
    sequence = sequence.sort_values("vial").reset_index(drop=True)

    if sequence["vial"].duplicated().any():
        duplicates = sequence.loc[sequence["vial"].duplicated(), "vial"].tolist()
        raise ValueError(f"Duplicate vial number(s) in sequence: {duplicates}")
    return sequence


def analyze_sequence(sequence_csv: Path, name: str) -> Path:
    """Write one fitted carryover prediction for every adjacent vial pair."""
    sequence = load_sequence(sequence_csv)
    references = load_clean_references()
    high_alpha, low_alpha = load_risk_alphas()

    unknown_recipes = sorted(set(sequence["recipe_id"]) - set(references))
    if unknown_recipes:
        raise ValueError(
            "No clean reference is available for recipe(s): "
            + ", ".join(str(recipe) for recipe in unknown_recipes)
        )

    rows: list[dict[str, object]] = []
    records = sequence.to_dict("records")
    for source, target in zip(records, records[1:]):
        result = evaluate_transition(
            int(source["recipe_id"]),
            int(target["recipe_id"]),
            references,
            high_alpha,
            low_alpha,
        )
        rows.append(
            {
                "source_vial": int(source["vial"]),
                "target_vial": int(target["vial"]),
                "source_recipe": int(source["recipe_id"]),
                "target_recipe": int(target["recipe_id"]),
                "recipe_change": int(source["recipe_id"]) != int(target["recipe_id"]),
                "predicted_carryover_delta_e": round(float(result["pred_err"]), 3),
                "clean_recipe_gap_delta_e": round(float(result["gap"]), 3),
                "risk_light": result["light"],
                "significant_predicted": result["light"] == "RED",
                "measurement_patch": result["patch"],
                "action": result["action"],
            }
        )

    out_dir = REPO_ROOT / "outputs" / "runs" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "carryover_transitions.csv"
    result_df = pd.DataFrame(rows)
    result_df.to_csv(output, index=False)

    counts = result_df["risk_light"].value_counts().to_dict()
    print(f"Sequential carryover predictions saved: {output}")
    print(
        f"Vials: {len(sequence)} | transitions: {len(result_df)} | "
        f"RED: {counts.get('RED', 0)} | AMBER: {counts.get('AMBER', 0)} | "
        f"GREEN: {counts.get('GREEN', 0)}"
    )
    print(
        "These are fitted impact/risk predictions from the known recipe sequence, "
        "not calibrated probabilities or proof of contamination."
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Predict carryover risk for every adjacent vial in a known CSI recipe sequence."
    )
    parser.add_argument(
        "--sequence",
        type=Path,
        required=True,
        help="CSV with one row per vial and columns vial,recipe_id",
    )
    parser.add_argument("--name", required=True, help="Run folder name under outputs/runs/")
    args = parser.parse_args()
    analyze_sequence(args.sequence, args.name)


if __name__ == "__main__":
    main()

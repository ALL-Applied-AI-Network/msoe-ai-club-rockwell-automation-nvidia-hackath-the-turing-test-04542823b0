"""
scripts/flush_advisor.py
Card 4, Step 4: Flush advisor - predicts carryover risk on a recipe queue before the fill.

Usage:
    python scripts/flush_advisor.py 6 7 8
    python scripts/flush_advisor.py 11 12 13 --after 10

Reads:
- outputs/card3/baseline_results.csv (clean 3rd-vial reference patch colors)
- outputs/card4/risk_model.json (fitted physical alphas for HIGH and LOW patches)

Prints:
- Per-transition risk evaluation: change, patch used, recipe gap ΔE, risk light, and operator action.
- Reorder suggestion: evaluates all queue permutations starting from --after (if given)
  to find an order with fewer RED changes, or the same number of REDs and fewer AMBERs.
"""

import argparse
import itertools
import json
import sys
from pathlib import Path
import colour
import numpy as np
import pandas as pd

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.vial_check import load_run_references, DEFAULT_VIDEO_MP4

BASELINE_CSV = REPO_ROOT / "outputs" / "card3" / "baseline_results.csv"
RISK_JSON = REPO_ROOT / "outputs" / "card4" / "risk_model.json"

ACTIONS = {
    "GREEN": "proceed",
    "AMBER": "proceed and flag the first vial for inspection",
    "RED": "flush or reorder; a flush needs the plant manager's approval, and its effect isn't measured yet (no flush in our data)",
}


def load_risk_alphas():
    """Load fitted alpha slopes from risk_model.json."""
    if not RISK_JSON.exists():
        print("Missing outputs/card4/risk_model.json. Run scripts/baseline_check.py, then scripts/fit_risk_model.py first.")
        sys.exit(1)

    with open(RISK_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return float(data["high_alpha"]), float(data["low_alpha"])


def load_clean_references():
    """Load clean 3rd-vial CIELAB reference colors for recipes 5 through 14."""
    if not BASELINE_CSV.exists():
        print("Missing outputs/card3/baseline_results.csv. Run scripts/baseline_check.py first.")
        sys.exit(1)

    df = pd.read_csv(BASELINE_CSV)
    ref_df = df[df["batch_pos"] == 3].copy()

    refs = {}
    for _, row in ref_df.iterrows():
        r_id = int(row["recipe_id"])
        has_high = not pd.isna(row["L_high"])

        lab_low = np.array([row["L_low"], row["a_low"], row["b_low"]], dtype=float)
        lab_high = np.array([row["L_high"], row["a_high"], row["b_high"]], dtype=float) if has_high else None

        refs[r_id] = {
            "vial": int(row["vial"]),
            "has_high": has_high,
            "lab_low": lab_low,
            "lab_high": lab_high,
        }

    return refs


def load_run_clean_references(run_name: str, video_mp4: Path = None) -> tuple[dict, list[int]]:
    """
    Load clean reference CIELAB colors (blank-normalized) from a run's vials.csv.

    Reads outputs/runs/<name>/vials.csv, extracts normalized colors for each recipe's
    designated reference vial, and returns the reference dict and the ordered recipe sequence.
    """
    run_dir = REPO_ROOT / "outputs" / "runs" / run_name
    vials_csv = run_dir / "vials.csv"
    if not vials_csv.exists():
        print(f"Missing {vials_csv}. Run scripts/new_run.py first.")
        sys.exit(1)

    if video_mp4 is None:
        cand1 = REPO_ROOT / "data" / "runs" / run_name / "video.mp4"
        cand2 = DEFAULT_VIDEO_MP4
        video_mp4 = cand1 if cand1.exists() else cand2

    raw_run_refs = load_run_references(vials_csv, video_mp4)
    df_vials = pd.read_csv(vials_csv)

    # Determine ordered recipe sequence
    seq = []
    for r in df_vials["recipe_id"]:
        r_int = int(r)
        if len(seq) == 0 or seq[-1] != r_int:
            seq.append(r_int)

    refs = {}
    for rec_id, rec_data in raw_run_refs["recipes"].items():
        ref_v = rec_data["reference_vial"]
        v_rows = df_vials[df_vials["vial"] == ref_v]
        if len(v_rows) == 0:
            continue
        tot_ml = int(v_rows.iloc[0]["total_ml"])
        has_high = (tot_ml >= 60)

        refs[rec_id] = {
            "vial": ref_v,
            "has_high": has_high,
            "lab_low": rec_data["LOW"]["norm_lab"],
            "lab_high": rec_data["HIGH"]["norm_lab"] if has_high else None,
        }

    return refs, seq


def evaluate_transition(prev_r: int, next_r: int, refs: dict, high_alpha: float, low_alpha: float) -> dict:
    """Evaluate carryover risk between two consecutive recipes."""
    if prev_r not in refs or next_r not in refs:
        missing = []
        if prev_r not in refs:
            missing.append(str(prev_r))
        if next_r not in refs:
            missing.append(str(next_r))
        msg = f"unknown recipe ({', '.join(missing)}), no clean reference yet"
        return {
            "status": "unknown",
            "message": msg,
            "light": "GRAY",
            "action": msg,
            "gap": 0.0,
            "pred_err": 0.0,
            "patch": "-",
        }

    # Same recipe running consecutively
    if prev_r == next_r:
        patch = "HIGH" if refs[prev_r]["has_high"] else "LOW"
        return {
            "status": "valid",
            "gap": 0.0,
            "patch": patch,
            "pred_err": 0.0,
            "light": "GREEN",
            "action": ACTIONS["GREEN"],
        }

    # If both recipes have valid HIGH patch measurements (both >= 60 mL), use HIGH patch
    if refs[prev_r]["has_high"] and refs[next_r]["has_high"]:
        patch = "HIGH"
        alpha = high_alpha
        gap = float(colour.delta_E(refs[prev_r]["lab_high"], refs[next_r]["lab_high"], method="CIE 2000"))
    else:
        patch = "LOW"
        alpha = low_alpha
        gap = float(colour.delta_E(refs[prev_r]["lab_low"], refs[next_r]["lab_low"], method="CIE 2000"))

    pred_err = alpha * gap

    if pred_err < 2.0:
        light = "GREEN"
    elif pred_err <= 5.0:
        light = "AMBER"
    else:
        light = "RED"

    return {
        "status": "valid",
        "gap": gap,
        "patch": patch,
        "pred_err": pred_err,
        "light": light,
        "action": ACTIONS[light],
    }


def evaluate_order(queue_order: list, start_recipe: int | None, refs: dict, high_alpha: float, low_alpha: float):
    """Evaluate all transitions for a specific queue ordering."""
    if start_recipe is not None:
        full_seq = [start_recipe] + list(queue_order)
    else:
        full_seq = list(queue_order)

    evaluations = []
    has_unknown = False

    for i in range(len(full_seq) - 1):
        res = evaluate_transition(full_seq[i], full_seq[i + 1], refs, high_alpha, low_alpha)
        evaluations.append((full_seq[i], full_seq[i + 1], res))
        if res["status"] == "unknown":
            has_unknown = True

    if has_unknown:
        return evaluations, None, None, None

    num_red = sum(1 for _, _, res in evaluations if res["light"] == "RED")
    num_amber = sum(1 for _, _, res in evaluations if res["light"] == "AMBER")
    total_err = sum(res["pred_err"] for _, _, res in evaluations)
    return evaluations, num_red, num_amber, total_err


def main():
    parser = argparse.ArgumentParser(
        description="Flush Advisor: predict carryover risk on a recipe queue and suggest optimal queue ordering."
    )
    parser.add_argument("queue", nargs="*", type=int, help="Queue of recipe IDs to run (e.g. 6 7 8)")
    parser.add_argument("--run", type=str, default=None, help="Name of run in outputs/runs/<name> to load clean references from")
    parser.add_argument("--video", type=Path, default=None, help="Optional video path override for --run")
    parser.add_argument("--after", type=int, default=None, help="Recipe ID currently in the station (starting point)")
    parser.add_argument("--compare", action="store_true", help="Compare run's lights side-by-side with Card 3 baseline")
    args = parser.parse_args()

    if not RISK_JSON.exists():
        print("Missing outputs/card4/risk_model.json. Run scripts/baseline_check.py, then scripts/fit_risk_model.py first.")
        sys.exit(1)

    high_alpha, low_alpha = load_risk_alphas()

    if args.run is not None:
        refs, run_seq = load_run_clean_references(args.run, video_mp4=args.video)
        queue = args.queue if len(args.queue) > 0 else run_seq
        ref_source = f"Run '{args.run}' (blank-normalized 3rd vials)"
    else:
        if not BASELINE_CSV.exists():
            print("Missing outputs/card3/baseline_results.csv. Run scripts/baseline_check.py first.")
            sys.exit(1)
        refs = load_clean_references()
        if len(args.queue) == 0:
            print("Please specify a queue of recipe IDs (e.g. python scripts/flush_advisor.py 6 7 8) or use --run <name>")
            sys.exit(1)
        queue = args.queue
        ref_source = "Card 3 baseline_results.csv"

    print("=" * 80)
    print("FLUID MIXING STATION 3: CARRYOVER FLUSH ADVISOR")
    print("=" * 80)
    print(f"Clean references: {ref_source}")
    if args.after is not None:
        print(f"Station state:    currently filled with Recipe {args.after}")
    print(f"Input queue:      {' -> '.join(str(r) for r in queue)}")
    print("-" * 80)

    # Optional side-by-side comparison with baseline
    if args.compare and BASELINE_CSV.exists():
        base_refs = load_clean_references()
        print("COMPARISON: CARD 3 BASELINE vs RUN-NORMALIZED LIGHTS\n")
        print(f"{'Change':<12} {'Patch':<6} {'Base Gap':<10} {'Base Light':<12} {'Run Gap':<10} {'Run Light':<12} {'Match?'}")
        print("-" * 75)
        comp_seq = ([args.after] + list(queue)) if args.after is not None else list(queue)
        all_match = True
        for i in range(len(comp_seq) - 1):
            r1, r2 = comp_seq[i], comp_seq[i + 1]
            e_base = evaluate_transition(r1, r2, base_refs, high_alpha, low_alpha)
            e_run = evaluate_transition(r1, r2, refs, high_alpha, low_alpha)
            match = (e_base["light"] == e_run["light"])
            if not match:
                all_match = False
            m_str = "YES" if match else "DIFF"
            b_gap_str = f"{e_base['gap']:.2f}" if e_base["status"] == "valid" else "-"
            r_gap_str = f"{e_run['gap']:.2f}" if e_run["status"] == "valid" else "-"
            print(f"{r1}->{r2:<9} {e_base['patch']:<6} {b_gap_str:<10} {e_base['light']:<12} {r_gap_str:<10} {e_run['light']:<12} {m_str}")
        print("-" * 75)
        print(f"All lights match: {all_match}\n")
        print("-" * 80)

    # If only 1 recipe in queue and no --after, nothing to evaluate
    if len(queue) < 2 and args.after is None:
        print("Queue contains only 1 recipe and no --after recipe was provided.")
        print("Specify at least two recipes or use --after <recipe_id> to evaluate transitions.")
        return

    # 1. Evaluate Current Order
    evaluations, current_red, current_amber, current_err = evaluate_order(queue, args.after, refs, high_alpha, low_alpha)

    print("STEP 1: PLANNED QUEUE TRANSITION CHECKS\n")
    for r1, r2, res in evaluations:
        change_label = f"Change {r1} -> {r2}:"
        if res["status"] == "unknown":
            print(f"  {change_label:<18} {res['message']}")
        else:
            print(f"  {change_label:<18} Patch: {res['patch']:<4} | Recipe gap: ΔE {res['gap']:.1f} | Light: {res['light']:<5}")
            print(f"    Action: {res['action']}")
        print()

    # 2. Reordering Suggestion
    print("-" * 80)
    print("STEP 2: REORDERING ADVICE\n")

    # If queue contains unknown recipes or has <= 1 item, cannot reorder
    if current_red is None or current_err is None:
        print("Cannot evaluate queue reordering: queue contains unknown recipe(s).")
        return

    if len(queue) <= 1:
        print("Current order is already the best (only 1 recipe in queue).")
        return

    if len(queue) > 6:
        print("Reorder check skipped: more than 6 recipes in the queue (the Batch Scheduler holds up to 3).")
        return

    # Find unique permutations of the queue
    unique_perms = sorted(list(set(itertools.permutations(queue))))

    best_perm = tuple(queue)
    best_red = current_red
    best_amber = current_amber
    best_err = current_err
    found_improvement = False

    for perm in unique_perms:
        if perm == tuple(queue):
            continue
        _, num_red, num_amber, tot_err = evaluate_order(perm, args.after, refs, high_alpha, low_alpha)
        if num_red is None:
            continue

        # Rule: suggest a different order only if it has fewer red changes,
        # or the same number of reds and fewer ambers. Never suggest a reorder
        # just because the total score is lower (predictions can be off by ~13 ΔE).
        is_strictly_fewer_red = num_red < best_red
        is_fewer_amber = (num_red == best_red) and (num_amber < best_amber)
        # Tie-break among candidate improvements using total score
        is_tie_break_among_improvements = (num_red == best_red) and (num_amber == best_amber) and found_improvement and (tot_err < best_err - 1e-4)

        if is_strictly_fewer_red or is_fewer_amber or is_tie_break_among_improvements:
            best_perm = perm
            best_red = num_red
            best_amber = num_amber
            best_err = tot_err
            found_improvement = True

    if found_improvement:
        suggested_str = " -> ".join(str(r) for r in best_perm)
        if args.after is not None:
            full_suggested = f"{args.after} -> {suggested_str}"
        else:
            full_suggested = suggested_str

        print(f"Suggested order (needs the planner's OK): {suggested_str}")
        if args.after is not None:
            print(f"  Full sequence: {full_suggested}")
        print(f"  Comparison vs current order:")
        print(f"    - Current order:   {current_red} RED, {current_amber} AMBER change(s)")
        print(f"    - Suggested order: {best_red} RED, {best_amber} AMBER change(s)")
    else:
        if current_red > 0:
            print("No order removes a red change; consider a flush (needs the plant manager's approval).")
        else:
            print("Current order is already the best.")


if __name__ == "__main__":
    main()

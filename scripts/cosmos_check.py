"""
scripts/cosmos_check.py
Card 3b, Step 2: Cosmos runner for in-context recipe match verification.

Evaluates Cosmos 3 Nano Reasoner on the 18 baseline vials (1st and 2nd vials
of recipes 6–14; 3rd vials are clean references, recipe 5 vials 1–3 are clear).

Prompt versions:
- V0: Text only (baseline for Cosmos)
- V1: Direct visual comparison against reference vial crop
- V2: Visual comparison against reference vial crop + recipe amounts
- V3: Visual comparison + recipe amounts + leave-one-recipe-out carryover example

Truthful batch context used in V0, V2, and V3:
- 1st vial: "This is the first vial after a recipe change; the previous vial was Recipe P: <amounts>."
- 2nd vial: "This is the second vial of this batch; the previous vial was also Recipe R, and the recipe before this batch was Recipe P: <amounts>."

Reads:
- manifest.csv (or outputs/card3b/manifest.csv)
- crops/vialNN.png (or outputs/card3b/crops/vialNN.png)

Writes:
- cosmos_check_answers.csv (or outputs/card3b/cosmos_check_answers.csv)
"""

import argparse
import csv
import os
from pathlib import Path
import sys

# Import ask_cosmos (support both local Brev directory and repo root)
try:
    from ask_cosmos import ask_cosmos, split_reasoning, DEFAULT_SYSTEM_PROMPT
except ImportError:
    try:
        from scripts.ask_cosmos import ask_cosmos, split_reasoning, DEFAULT_SYSTEM_PROMPT
    except ImportError:
        ask_cosmos = None
        split_reasoning = None
        DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

BASELINE_VIALS = [4, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28, 29]
PROMPT_VERSIONS = ["V0", "V1", "V2", "V3"]
DEFAULT_REPEATS = 3


def format_amounts(t100: int, t200: int, t400: int) -> str:
    """Formats recipe volumes in plain English, skipping 0 mL components."""
    parts = []
    if t200 > 0:
        parts.append(f"{t200} mL orange")
    if t400 > 0:
        parts.append(f"{t400} mL blue")
    if t100 > 0:
        parts.append(f"{t100} mL clear")
    return " + ".join(parts) if parts else "0 mL"


def parse_decision(answer_text: str) -> str:
    """Parses initial yes/no from Cosmos answer text; non-yes/no counts as unclear."""
    clean = answer_text.strip()
    if not clean:
        return "unclear"
    first_token = clean.split()[0].lower().strip(".,!;:\"'()[]")
    if first_token == "yes":
        return "yes"
    if first_token == "no":
        return "no"
    lower = clean.lower()
    if lower.startswith("yes"):
        return "yes"
    if lower.startswith("no"):
        return "no"
    return "unclear"


def build_prompt_and_media(
    vial_info: dict,
    version: str,
    crops_dir: Path,
) -> tuple[list[Path], str]:
    """
    Builds the exact list of image paths and prompt string for a given vial and version.
    """
    v = vial_info["vial"]
    r_id = vial_info["recipe"]
    prev_r_id = vial_info["previous_recipe"]
    batch_pos = vial_info["batch_position"]
    ref_v = vial_info["reference_vial"]

    r_amounts = format_amounts(vial_info["t100_ml"], vial_info["t200_ml"], vial_info["t400_ml"])
    prev_amounts = format_amounts(
        vial_info["prev_t100_ml"], vial_info["prev_t200_ml"], vial_info["prev_t400_ml"]
    )

    test_crop = crops_dir / f"vial{v:02d}.png"
    ref_crop = crops_dir / f"vial{ref_v:02d}.png"

    # Truthful batch context for 1st vs 2nd vials
    if batch_pos == 1:
        batch_context = (
            f"This is the first vial after a recipe change; "
            f"the previous vial was Recipe {prev_r_id}: {prev_amounts}."
        )
    else:
        batch_context = (
            f"This is the second vial of this batch; "
            f"the previous vial was also Recipe {r_id}, and the recipe before this batch was Recipe {prev_r_id}: {prev_amounts}."
        )

    if version == "V0":
        # Text only
        media = [test_crop]
        text = (
            f"This vial should be Recipe {r_id}: {r_amounts}. "
            f"{batch_context} "
            "Does the liquid's color match this recipe? "
            "Answer yes or no first, then one sentence."
        )
    elif version == "V1":
        # Compare (no recipe text)
        media = [test_crop, ref_crop]
        text = (
            "Image 2 shows a correct vial. "
            "Is the liquid in Image 1 the same color as the liquid in Image 2? "
            "Ignore labels, barcodes and the holder. "
            "Answer yes or no first, then one sentence."
        )
    elif version == "V2":
        # Compare + recipes
        media = [test_crop, ref_crop]
        text = (
            f"Both vials should be Recipe {r_id}: {r_amounts}. "
            f"Image 2 is a correct Recipe {r_id} vial, so it shows exactly what this recipe looks like; "
            "judge Image 1 by comparing it with Image 2, not by what you expect the dye mix to look like. "
            f"{batch_context} "
            "Does Image 1 match? "
            "Answer yes or no first, then one sentence."
        )
    elif version == "V3":
        # Compare + recipes + one example (leave-one-recipe-out)
        if r_id in (6, 7):
            # Use Recipe 12's carryover (vial 22 and vial 24)
            ex_test = crops_dir / "vial22.png"
            ex_ref = crops_dir / "vial24.png"
        else:
            # Use Recipe 7's carryover (vial 07 and vial 09)
            ex_test = crops_dir / "vial07.png"
            ex_ref = crops_dir / "vial09.png"

        media = [ex_test, ex_ref, test_crop, ref_crop]
        text = (
            "Images 1 and 2 are a worked example from a different recipe: "
            "Image 1 does NOT match Image 2, because leftover from the previous recipe tinted it. "
            "Now judge Image 3 against Image 4. "
            f"Both vials should be Recipe {r_id}: {r_amounts}. "
            f"Image 4 is a correct Recipe {r_id} vial, so it shows exactly what this recipe looks like; "
            "judge Image 3 by comparing it with Image 4, not by what you expect the dye mix to look like. "
            f"{batch_context} "
            "Does Image 3 match? "
            "Answer yes or no first, then one sentence."
        )
    else:
        raise ValueError(f"Unknown version: {version}")

    return media, text


def resolve_manifest_path(path_arg: str | None) -> Path:
    if path_arg:
        p = Path(path_arg)
        if not p.exists():
            raise FileNotFoundError(f"Manifest not found: {p}")
        return p
    for candidate in [Path("manifest.csv"), Path("outputs/card3b/manifest.csv")]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find manifest.csv. Run export_vial_crops.py first.")


def resolve_crops_dir(dir_arg: str | None) -> Path:
    if dir_arg:
        p = Path(dir_arg)
        if not p.is_dir():
            raise FileNotFoundError(f"Crops directory not found: {p}")
        return p
    for candidate in [Path("crops"), Path("outputs/card3b/crops")]:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Could not find crops directory. Run export_vial_crops.py first.")


def resolve_output_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg)
    if Path("outputs/card3b").is_dir():
        return Path("outputs/card3b/cosmos_check_answers.csv")
    return Path("cosmos_check_answers.csv")


def load_manifest(manifest_path: Path) -> dict[int, dict]:
    vial_data = {}
    with open(manifest_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = int(row["vial"])
            vial_data[v] = {
                "vial": v,
                "recipe": int(row["recipe"]),
                "previous_recipe": int(row["previous_recipe"]) if row["previous_recipe"] else None,
                "batch_position": int(row["batch_position"]),
                "t100_ml": int(row["t100_ml"]) if row["t100_ml"] else 0,
                "t200_ml": int(row["t200_ml"]) if row["t200_ml"] else 0,
                "t400_ml": int(row["t400_ml"]) if row["t400_ml"] else 0,
                "prev_t100_ml": int(row["prev_t100_ml"]) if row["prev_t100_ml"] else 0,
                "prev_t200_ml": int(row["prev_t200_ml"]) if row["prev_t200_ml"] else 0,
                "prev_t400_ml": int(row["prev_t400_ml"]) if row["prev_t400_ml"] else 0,
                "reference_vial": int(row["reference_vial"]),
            }
    return vial_data


def run_dry_run(
    manifest: dict[int, dict],
    crops_dir: Path,
    vials: list[int] | None = None,
    versions: list[str] | None = None,
):
    dry_run_vials = vials if vials else [7, 13]
    active_versions = versions if versions else PROMPT_VERSIONS

    print("=" * 80)
    print(f"COSMOS CHECK -- DRY RUN (vials {dry_run_vials}, versions {active_versions})")
    print("=" * 80)
    print(f"Crops directory: {crops_dir.resolve()}\n")

    for v in dry_run_vials:
        if v not in manifest:
            print(f"Vial {v} not found in manifest!")
            continue
        info = manifest[v]
        r_id = info["recipe"]
        pos = info["batch_position"]
        prev_r = info["previous_recipe"]
        print(f"########################################")
        print(f"VIAL {v:02d} | Recipe {r_id} (batch pos #{pos}) | Previous Recipe {prev_r}")
        print(f"########################################")

        for ver in active_versions:
            media, prompt_text = build_prompt_and_media(info, ver, crops_dir)
            print(f"\n--- Version {ver} ---")
            print("Media files:")
            for idx, p in enumerate(media, 1):
                exists_flag = "[EXISTS]" if p.exists() else "[MISSING]"
                print(f"  Image {idx}: {p} {exists_flag}")
            print("Prompt text:")
            print(f"  \"{prompt_text}\"")
        print()


def run_cosmos_check(args):
    manifest_path = resolve_manifest_path(args.manifest)
    crops_dir = resolve_crops_dir(args.crops_dir)
    manifest = load_manifest(manifest_path)

    if args.dry_run:
        run_dry_run(manifest, crops_dir, args.vials, args.versions)
        return

    if ask_cosmos is None:
        sys.exit(
            "Could not import ask_cosmos. Make sure ask_cosmos.py is in the current directory or scripts/."
        )

    output_csv = resolve_output_path(args.output)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    # Load already recorded keys to support resumption
    completed_keys = set()
    csv_exists = output_csv.exists() and output_csv.stat().st_size > 0
    if csv_exists:
        with open(output_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                v = int(row["vial"])
                ver = row["prompt_version"]
                rep = int(row["repeat"])
                completed_keys.add((v, ver, rep))
        print(f"Resuming: found {len(completed_keys)} completed combinations in {output_csv}")

    fieldnames = [
        "vial",
        "recipe",
        "batch_position",
        "prompt_version",
        "repeat",
        "answer_text",
        "decision",
        "raw_response",
    ]

    active_vials = args.vials if args.vials else [v for v in BASELINE_VIALS if v in manifest]
    active_versions = args.versions if args.versions else PROMPT_VERSIONS

    # Open CSV for appending
    with open(output_csv, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not csv_exists:
            writer.writeheader()
            f.flush()

        total_runs = len(active_vials) * len(active_versions) * args.repeats
        print(f"Running Cosmos check: {len(active_vials)} vials x {len(active_versions)} versions x {args.repeats} repeats = {total_runs} total calls.")

        call_idx = len(completed_keys)
        for v in active_vials:
            v_info = manifest[v]
            for ver in active_versions:
                for rep in range(args.repeats):
                    if (v, ver, rep) in completed_keys:
                        continue

                    call_idx += 1
                    media, prompt_text = build_prompt_and_media(v_info, ver, crops_dir)

                    print(f"[{call_idx}/{total_runs}] Vial {v:02d} | {ver} | Repeat {rep} ...", end=" ", flush=True)

                    try:
                        raw_response = ask_cosmos(
                            paths=media,
                            prompt=prompt_text,
                            system_prompt=DEFAULT_SYSTEM_PROMPT,
                            think=False,
                            fps=4.0,
                            max_tokens=512,
                        )
                        _, answer_text = split_reasoning(raw_response)
                        decision = parse_decision(answer_text)
                        print(f"-> {decision} | \"{answer_text}\"")
                    except Exception as err:
                        print(f"-> ERROR: {err}")
                        raw_response = f"ERROR: {err}"
                        answer_text = f"ERROR: {err}"
                        decision = "unclear"

                    row_data = {
                        "vial": v,
                        "recipe": v_info["recipe"],
                        "batch_position": v_info["batch_position"],
                        "prompt_version": ver,
                        "repeat": rep,
                        "answer_text": answer_text,
                        "decision": decision,
                        "raw_response": raw_response,
                    }
                    writer.writerow(row_data)
                    f.flush()
                    completed_keys.add((v, ver, rep))

    print(f"\nFinished. Results saved in {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description="Run in-context Cosmos check across baseline vials and prompt versions."
    )
    parser.add_argument(
        "--manifest", default=None, help="Path to manifest.csv (defaults to manifest.csv or outputs/card3b/manifest.csv)"
    )
    parser.add_argument(
        "--crops-dir", default=None, help="Path to crops directory (defaults to crops/ or outputs/card3b/crops/)"
    )
    parser.add_argument(
        "--output", default=None, help="Output CSV path (defaults to outputs/card3b/cosmos_check_answers.csv or cosmos_check_answers.csv)"
    )
    parser.add_argument(
        "--vials", nargs="+", type=int, default=None, help="Specific vial numbers to run (default: 18 baseline vials)"
    )
    parser.add_argument(
        "--versions", nargs="+", default=None, help="Specific prompt versions to run (default: V0 V1 V2 V3)"
    )
    parser.add_argument(
        "--repeats", type=int, default=DEFAULT_REPEATS, help="Number of repeats per combination (default 3)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print exact prompts and image paths without calling Cosmos.",
    )
    args = parser.parse_args()
    run_cosmos_check(args)


if __name__ == "__main__":
    main()

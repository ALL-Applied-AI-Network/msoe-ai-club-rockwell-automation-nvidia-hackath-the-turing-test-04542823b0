"""
scripts/explain.py
Card 9, Step 1: Physical AI explanations for flagged carryover vials using
NVIDIA Cosmos 3 Nano Reasoner (Version C prompt).

Inputs per vial:
- Image 1: Liquid crop of the vial being checked (outputs/card3b/crops/vial<NN>.png)
- Image 2: Liquid crop of the clean reference vial of its recipe (outputs/card3b/crops/vial<REF>.png)
- Text evidence:
  - Intended recipe (recipe number and mL from orange, blue, clear)
  - Previous recipe (same)
  - Dispense order (T-200 orange -> T-400 blue -> T-100 clear through one shared pipe and nozzle)
  - Measurement patch used (HIGH for tall vials >= 60 mL, LOW for short vials)
  - Measured CIELAB ΔE2000 against the clean reference vial
  - In-line inspection verdict (FAIL)
  - Flush advisor pre-fill prediction (RED / AMBER)

Outputs:
- outputs/card9/explanations.csv: All explanations, parsed fields, and call timings across repeats.
- outputs/explanations_cache.json: Cached explanation (1st repeat) for each recipe change (with --cache).

Usage:
  python scripts/explain.py --dry-run --vials 7
  python scripts/explain.py --dry-run
  python scripts/explain.py --vials 4 7 10 16 19 22 25 28 --repeats 3 --cache
"""

import argparse
import csv
import json
import os
from pathlib import Path
import re
import sys
import time

# Portable encoding support for stdout/stderr
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import helpers from ask_cosmos and explanation_cache
try:
    from scripts.ask_cosmos import (
        DEFAULT_BASE_URL,
        DEFAULT_MODEL,
        build_media_parts,
        file_to_data_uri,
    )
except ImportError:
    from ask_cosmos import (
        DEFAULT_BASE_URL,
        DEFAULT_MODEL,
        build_media_parts,
        file_to_data_uri,
    )

try:
    from scripts import explanation_cache
except ImportError:
    import explanation_cache

import pandas as pd
from dotenv import load_dotenv

# Default flagged test set of first vials from Video 5
# (Vial 13 passed the color check with ΔE < 2.0, so it never reaches Cosmos)
DEFAULT_FLAGGED_VIALS = [4, 7, 10, 16, 19, 22, 25, 28]

SYSTEM_PROMPT = (
    "You inspect vials on a color-mixing line. "
    "Image 1 is the vial being checked, image 2 is a clean vial of the same recipe. "
    "Use only the facts given; do not invent numbers or say a flush has been tested. "
    "Answer only in JSON with keys matches_recipe (true/false), observed_color, "
    "likely_cause, operator_action, confidence (low/medium/high)."
)

# Known advisor pre-fill risk lights for the 8 flagged changes
ADVISOR_LIGHTS = {
    "5->6": "RED",
    "6->7": "RED",
    "7->8": "RED",
    "9->10": "RED",
    "10->11": "RED",
    "11->12": "RED",
    "12->13": "RED",
    "13->14": "RED",
}


def format_recipe_desc(rec_id: int, t200: float, t400: float, t100: float) -> str:
    """Formats recipe into plain English: Recipe R (X mL orange + Y mL blue + Z mL clear)."""
    parts = []
    if t200 > 0:
        vol = int(t200) if float(t200).is_integer() else t200
        parts.append(f"{vol} mL orange")
    if t400 > 0:
        vol = int(t400) if float(t400).is_integer() else t400
        parts.append(f"{vol} mL blue")
    if t100 > 0:
        vol = int(t100) if float(t100).is_integer() else t100
        parts.append(f"{vol} mL clear")
    if not parts:
        parts.append("0 mL")
    return f"Recipe {int(rec_id)} ({' + '.join(parts)})"


def load_vial_metadata(
    manifest_path: Path,
    baseline_path: Path,
    crops_dir: Path,
) -> dict[int, dict]:
    """Loads and joins manifest, baseline results, and crop image paths for all vials."""
    manifest_path = Path(manifest_path)
    baseline_path = Path(baseline_path)
    crops_dir = Path(crops_dir)

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    if not baseline_path.exists():
        raise FileNotFoundError(f"Missing baseline results: {baseline_path}")

    df_man = pd.read_csv(manifest_path)
    df_base = pd.read_csv(baseline_path)

    merged = pd.merge(
        df_man,
        df_base[["vial", "total_ml", "delta_e_low", "delta_e_high"]],
        on="vial",
        how="inner",
    )

    metadata = {}
    for _, r in merged.iterrows():
        v = int(r["vial"])
        rec_id = int(r["recipe"])
        prev_rec = int(r["previous_recipe"]) if pd.notna(r["previous_recipe"]) else None
        ref_vial = int(r["reference_vial"])
        tot_ml = int(r["total_ml"])

        # Determine active patch and ΔE
        if tot_ml >= 60 and pd.notna(r["delta_e_high"]):
            patch_name = "HIGH"
            delta_e = float(r["delta_e_high"])
        else:
            patch_name = "LOW"
            delta_e = float(r["delta_e_low"])

        verdict = "FAIL" if delta_e > 5.0 else ("UNSURE" if delta_e >= 2.0 else "PASS")

        # Formatted descriptions
        rec_desc = format_recipe_desc(
            rec_id,
            float(r.get("t200_ml", 0) or 0),
            float(r.get("t400_ml", 0) or 0),
            float(r.get("t100_ml", 0) or 0),
        )

        if prev_rec is not None:
            prev_desc = format_recipe_desc(
                prev_rec,
                float(r.get("prev_t200_ml", 0) or 0),
                float(r.get("prev_t400_ml", 0) or 0),
                float(r.get("prev_t100_ml", 0) or 0),
            )
            change_key = f"{prev_rec}->{rec_id}"
            advisor_light = ADVISOR_LIGHTS.get(change_key, "RED")
        else:
            prev_desc = "None (first vial of run)"
            change_key = "unknown"
            advisor_light = "UNKNOWN"

        vial_crop = crops_dir / f"vial{v:02d}.png"
        ref_crop = crops_dir / f"vial{ref_vial:02d}.png"

        metadata[v] = {
            "vial": v,
            "recipe_id": rec_id,
            "previous_recipe_id": prev_rec,
            "reference_vial": ref_vial,
            "total_ml": tot_ml,
            "patch": patch_name,
            "delta_e": round(delta_e, 1),
            "verdict": verdict,
            "change_key": change_key,
            "advisor_light": advisor_light,
            "recipe_desc": rec_desc,
            "prev_recipe_desc": prev_desc,
            "vial_crop": vial_crop,
            "ref_crop": ref_crop,
        }

    return metadata


def build_prompt_text(meta: dict) -> str:
    """Builds the Version C user prompt text for Cosmos."""
    text = (
        f"Inspect this vial:\n"
        f"- Intended recipe: {meta['recipe_desc']}\n"
        f"- Previous recipe: {meta['prev_recipe_desc']}\n"
        f"- Dispense order: T-200 (orange) -> T-400 (blue) -> T-100 (clear) through one shared pipe and nozzle\n"
        f"- Measurement patch: {meta['patch']}\n"
        f"- Measured color difference: ΔE2000 = {meta['delta_e']:.1f} against the clean reference vial (Image 2)\n"
        f"- Color check verdict: {meta['verdict']}\n"
        f"- Flush advisor pre-fill prediction: {meta['advisor_light']}\n\n"
        f"Image 1 is the vial being inspected. Image 2 is the clean reference vial of the intended recipe.\n"
        f"Explain why this vial failed inspection and what the operator should do. Answer only in JSON with keys:\n"
        f"matches_recipe, observed_color, likely_cause, operator_action, confidence."
    )
    return text


def parse_cosmos_json(raw_text: str) -> dict:
    """Parses Cosmos response into JSON dictionary, handling optional markdown code fences."""
    cleaned = raw_text.strip()
    # Strip markdown code blocks if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Fallback regex extraction for individual keys if full JSON parse fails
    fallback = {}
    m_match = re.search(r'"matches_recipe"\s*:\s*(true|false)', raw_text, re.IGNORECASE)
    if m_match:
        fallback["matches_recipe"] = m_match.group(1).lower() == "true"

    for key in ["observed_color", "likely_cause", "operator_action", "confidence"]:
        k_match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', raw_text)
        if k_match:
            fallback[key] = k_match.group(1).strip()

    return fallback


def call_cosmos(
    image_paths: list[Path],
    user_text: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> tuple[str, float]:
    """Calls Cosmos 3 Reasoner NIM endpoint and returns (raw_response, elapsed_seconds)."""
    import openai

    load_dotenv()
    base_url = os.getenv("COSMOS_BASE_URL", DEFAULT_BASE_URL)
    model = os.getenv("COSMOS_MODEL", DEFAULT_MODEL)
    api_key = os.getenv("NVIDIA_API_KEY") or "not-used"

    content = build_media_parts(image_paths) + [{"type": "text", "text": user_text}]

    sampling = {"temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5}
    extra_body = {"top_k": 20, "repetition_penalty": 1.0}

    client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=300)

    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        max_tokens=2048,
        extra_body=extra_body,
        **sampling,
    )
    t1 = time.perf_counter()
    raw_answer = response.choices[0].message.content or ""
    return raw_answer, round(t1 - t0, 2)


def run_explain(
    vials: list[int],
    repeats: int = 3,
    dry_run: bool = False,
    cache_results: bool = False,
    out_csv: Path = Path("outputs/card9/explanations.csv"),
    crops_dir: Path = Path("outputs/card3b/crops"),
    manifest_path: Path = Path("outputs/card3b/manifest.csv"),
    baseline_path: Path = Path("outputs/card3/baseline_results.csv"),
):
    metadata = load_vial_metadata(manifest_path, baseline_path, crops_dir)

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("CARD 9: COSMOS REASON PHYSICAL AI EXPLANATIONS (VERSION C)")
    print("=" * 80)
    print(f"Target Vials:  {vials}")
    print(f"Repeats:       {repeats}")
    print(f"Dry Run:       {dry_run}")
    print(f"Cache to JSON: {cache_results}")
    print(f"Output CSV:    {out_csv}")
    print("=" * 80 + "\n")

    if dry_run:
        for v in vials:
            if v not in metadata:
                print(f"ERROR: Vial {v} not found in metadata.", file=sys.stderr)
                continue
            meta = metadata[v]
            prompt_text = build_prompt_text(meta)
            img1 = meta["vial_crop"]
            img2 = meta["ref_crop"]

            print(f"--------------------------------------------------------------------------------")
            print(f"DRY RUN PROMPT: VIAL {v} (Change: {meta['change_key']})")
            print(f"--------------------------------------------------------------------------------")
            print(f"[SYSTEM PROMPT]\n{SYSTEM_PROMPT}\n")
            print(f"[MEDIA INPUTS]")
            print(f"  Image 1 (vial under test): {img1} (exists: {img1.exists()})")
            print(f"  Image 2 (clean reference): {img2} (exists: {img2.exists()})\n")
            print(f"[USER PROMPT (TEXT GOES AFTER IMAGES IN REQUEST)]")
            print(prompt_text)
            print(f"--------------------------------------------------------------------------------\n")
        return

    # Real run (calling Cosmos)
    csv_rows = []
    fieldnames = [
        "vial",
        "change",
        "repeat",
        "matches_recipe",
        "observed_color",
        "likely_cause",
        "operator_action",
        "confidence",
        "seconds",
        "raw_answer",
    ]

    for v in vials:
        if v not in metadata:
            print(f"Skipping unknown vial: {v}")
            continue

        meta = metadata[v]
        img_paths = [meta["vial_crop"], meta["ref_crop"]]
        user_text = build_prompt_text(meta)
        change_key = meta["change_key"]
        prev_r = meta["previous_recipe_id"]
        next_r = meta["recipe_id"]

        print(f"\nEvaluating Vial {v} (Change {change_key}) ...")

        for rep in range(1, repeats + 1):
            print(f"  Repeat {rep}/{repeats} ...", end=" ", flush=True)
            try:
                raw_text, duration = call_cosmos(img_paths, user_text, SYSTEM_PROMPT)
                print(f"done ({duration:.2f}s)")
            except Exception as e:
                print(f"FAILED: {e}")
                raw_text = f"ERROR: {e}"
                duration = 0.0

            parsed = parse_cosmos_json(raw_text)

            row = {
                "vial": v,
                "change": change_key,
                "repeat": rep,
                "matches_recipe": parsed.get("matches_recipe", ""),
                "observed_color": parsed.get("observed_color", ""),
                "likely_cause": parsed.get("likely_cause", ""),
                "operator_action": parsed.get("operator_action", ""),
                "confidence": parsed.get("confidence", ""),
                "seconds": duration,
                "raw_answer": raw_text,
            }
            csv_rows.append(row)

            # With --cache, cache the FIRST repeat of each change
            if cache_results and rep == 1 and prev_r is not None:
                exp_entry = {
                    "matches_recipe": parsed.get("matches_recipe", False),
                    "observed_color": parsed.get("observed_color", ""),
                    "likely_cause": parsed.get("likely_cause", ""),
                    "operator_action": parsed.get("operator_action", ""),
                    "confidence": parsed.get("confidence", "high"),
                    "vial": v,
                    "change": change_key,
                    "delta_e": meta["delta_e"],
                    "patch": meta["patch"],
                }
                explanation_cache.put(prev_r, next_r, exp_entry)
                print(f"    -> Cached repeat 1 to {explanation_cache.DEFAULT_CACHE_PATH}")

    # Write output CSV
    write_header = not out_csv.exists()
    with open(out_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for r in csv_rows:
            writer.writerow(r)

    print(f"\nSaved {len(csv_rows)} explanation records to: {out_csv}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Cosmos Physical AI explanations for flagged carryover vials."
    )
    parser.add_argument(
        "--vials",
        nargs="+",
        type=int,
        default=DEFAULT_FLAGGED_VIALS,
        help="List of vial numbers to explain (default: 4 7 10 16 19 22 25 28)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of repeat explanations to generate per vial (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the full prompt for each vial without calling Cosmos",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Put the first repeat of each recipe change into outputs/explanations_cache.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/card9/explanations.csv"),
        help="Output CSV path (default: outputs/card9/explanations.csv)",
    )
    parser.add_argument(
        "--crops-dir",
        type=Path,
        default=Path("outputs/card3b/crops"),
        help="Directory containing vial liquid crops",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("outputs/card3b/manifest.csv"),
        help="Path to manifest CSV",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("outputs/card3/baseline_results.csv"),
        help="Path to baseline results CSV",
    )

    args = parser.parse_args()
    run_explain(
        vials=args.vials,
        repeats=args.repeats,
        dry_run=args.dry_run,
        cache_results=args.cache,
        out_csv=args.out,
        crops_dir=args.crops_dir,
        manifest_path=args.manifest,
        baseline_path=args.baseline,
    )


if __name__ == "__main__":
    main()

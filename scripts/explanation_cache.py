"""
scripts/explanation_cache.py
Card 10, Step 3: Explanation cache for Cosmos recipe change explanations.

Stores and looks up Cosmos explanations per recipe change.
- get(prev_recipe, next_recipe) -> dict or None
- put(prev_recipe, next_recipe, explanation_dict, is_test=False) -> updates cache and logs to CSV

Storage:
- Cache: outputs/explanations_cache.json (keys like "6->7")
- Log: outputs/cosmos_log.csv (append-only with timestamps, skips test entries)

Error handling:
A missing, empty, or broken/corrupted file must NEVER crash: get() returns None,
and --show reports the file as unreadable and treats the cache as empty.

CLI:
- python scripts/explanation_cache.py --show
- python scripts/explanation_cache.py --put-test
- python scripts/explanation_cache.py --clear-test
"""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# Portable encoding support for stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_CACHE_PATH = Path("outputs/explanations_cache.json")
DEFAULT_LOG_PATH = Path("outputs/cosmos_log.csv")


def get(
    prev_recipe: int | str,
    next_recipe: int | str,
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> dict | None:
    """
    Looks up a cached explanation for the recipe transition prev_recipe -> next_recipe.
    Returns the explanation dict, or None if not found or if the cache file is unreadable.
    """
    key = f"{prev_recipe}->{next_recipe}"
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get(key)
        return None
    except Exception:
        # A corrupted or unreadable cache file must never crash the system
        return None


def put(
    prev_recipe: int | str,
    next_recipe: int | str,
    explanation_dict: dict,
    cache_path: Path = DEFAULT_CACHE_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
    is_test: bool = False,
):
    """
    Saves an explanation in the JSON cache and appends a record to the CSV log.
    If is_test is True (or explanation_dict has 'test': True), does NOT write to cosmos_log.csv.
    """
    key = f"{prev_recipe}->{next_recipe}"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Update JSON cache
    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, dict):
                    cache = content
        except Exception:
            cache = {}

    entry = dict(explanation_dict)
    if is_test:
        entry["test"] = True

    cache[key] = entry

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

    # 2. Append to CSV log (only for non-test entries)
    if entry.get("test") is True:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    log_exists = log_path.exists() and log_path.stat().st_size > 0

    fieldnames = [
        "timestamp",
        "prev_recipe",
        "next_recipe",
        "likely_cause",
        "operator_action",
        "observed_color",
        "matches_recipe",
        "confidence",
        "raw_json",
    ]

    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not log_exists:
            writer.writeheader()

        writer.writerow({
            "timestamp": now_iso,
            "prev_recipe": str(prev_recipe),
            "next_recipe": str(next_recipe),
            "likely_cause": str(entry.get("likely_cause", "")),
            "operator_action": str(entry.get("operator_action", "")),
            "observed_color": str(entry.get("observed_color", "")),
            "matches_recipe": str(entry.get("matches_recipe", "")),
            "confidence": str(entry.get("confidence", "")),
            "raw_json": json.dumps(entry),
        })


def clear_test_entries(cache_path: Path = DEFAULT_CACHE_PATH) -> int:
    """
    Removes only entries marked 'test': True from the cache.
    Never touches real explanations.
    Returns the count of removed test entries.
    """
    if not cache_path.exists():
        return 0

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0

    if not isinstance(data, dict):
        return 0

    real_entries = {k: v for k, v in data.items() if not (isinstance(v, dict) and v.get("test") is True)}
    removed_count = len(data) - len(real_entries)

    if len(real_entries) == 0:
        cache_path.unlink()
    else:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(real_entries, f, indent=2)

    return removed_count


def show_cache(cache_path: Path = DEFAULT_CACHE_PATH):
    """Prints all cached explanations, or 'no explanations cached yet' if empty or unreadable."""
    if not cache_path.exists():
        print("no explanations cached yet")
        return

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as err:
        print(f"Warning: Cache file '{cache_path}' is unreadable ({err}). Treating cache as empty.")
        print("no explanations cached yet")
        return

    if not isinstance(data, dict) or len(data) == 0:
        print("no explanations cached yet")
        return

    print("=" * 70)
    print(f"EXPLANATION CACHE ({len(data)} entries in {cache_path})")
    print("=" * 70)
    for key, val in data.items():
        is_test_flag = " [TEST ENTRY]" if isinstance(val, dict) and val.get("test") is True else ""
        print(f"\n--- Recipe Change: {key}{is_test_flag} ---")
        if isinstance(val, dict):
            for k, v in val.items():
                print(f"  {k}: {v}")
        else:
            print(f"  {val}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Cosmos explanation cache manager.")
    parser.add_argument("--show", action="store_true", help="Print all cached explanations")
    parser.add_argument("--put-test", action="store_true", help="Put a test entry for 6->7 (marked 'test': true, not logged to CSV)")
    parser.add_argument("--clear-test", action="store_true", help="Remove only test entries ('test': true) from cache")
    args = parser.parse_args()

    if args.put_test:
        test_exp = {
            "matches_recipe": "no",
            "observed_color": "green",
            "likely_cause": "Carryover from Recipe 6 (orange dye) tinted the initial Recipe 7 fill (blue dye), producing green liquid.",
            "operator_action": "Quarantine vial 7 and verify vial 8 is clear blue before continuing.",
            "confidence": "high",
        }
        put(6, 7, test_exp, is_test=True)
        print("Put test explanation for '6->7' with 'test': true (log skipped).")

    elif args.clear_test:
        removed = clear_test_entries()
        print(f"Cleared {removed} test entries from cache.")

    elif args.show:
        show_cache()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

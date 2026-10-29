"""scripts/new_run.py
New-recording mode Step 2: Turns a raw recording and a recipe list into a verified run table.

Reads:
- --video: Path to vial_fill video (.mp4)
- --recipes: Path to recipe list CSV (matching annotations/run_recipes_template.csv)
- --name: Name of run (outputs saved to outputs/runs/<name>/)
- --min-fill-de: Optional float threshold for liquid detection (default 4.6)

Workflow:
1. Loads and validates the recipe list:
   - Refuses any recipe with fewer than 2 vials.
   - Refuses any vial with total_ml > 80 mL (station limit).
   - Warns if T-300 is called (out of service).
   - Warns if > 50 mL is called from T-200 (station limit).
2. Runs detect_parked_vials to locate all filled vials and rejected empty intervals.
3. Compares counts:
   - If counts differ, stops with a clear message listing both counts, pointing to the
     contact sheet, listing every rejected parked interval (frame and LOW change),
     and explaining the --min-fill-de option.
4. Checks camera alignment (glass-edge check):
   - Runs detect_glass_edges on every found frame.
   - Stops with a clear message if LOW or HIGH patch touches or exceeds the vial glass walls.
5. Assigns reference vials:
   - If is_reference is empty, automatically designates the last vial of each contiguous
     recipe run as is_reference=True.
6. Writes outputs/runs/<name>/vials.csv with standard columns:
   vial, recipe_id, total_ml, t200_ml, t400_ml, t100_ml, last_parked_frame, last_parked_mp4_s, is_reference

Usage:
  python scripts/new_run.py --video data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4 --recipes data/runs/video5_practice/recipes.csv --name video5_practice
"""

import argparse
from pathlib import Path
import sys
import cv2
import pandas as pd

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.crop_vial import detect_glass_edges, HIGH_PATCH, LOW_PATCH
from scripts.detect_parked_vials import DEFAULT_MIN_FILL_DE, detect_parked_vials

# Portable stdout and stderr encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# Allowed recipe columns (matches template and dataset format)
KNOWN_RECIPE_COLUMNS = {
    "vial",
    "recipe_id",
    "t200_ml",
    "t400_ml",
    "t100_ml",
    "t300_ml",
    "total_ml",
    "is_reference",
    "dispense_order",
    "color_purpose",
    "type",
    "start_time",
    "end_time",
    "start_s",
    "end_s",
    "duration_s",
    "start_frame",
    "end_frame",
}


def validate_recipes(df_recipes: pd.DataFrame) -> tuple[bool, str, pd.DataFrame]:
    """
    Validates recipe table against physical station constraints.

    Returns:
        (is_valid, error_message, validated_df)
    """
    df = df_recipes.copy()

    # Check for unrecognized columns (e.g. typos like recipe_idx, t200ml)
    for col in df.columns:
        if col not in KNOWN_RECIPE_COLUMNS:
            return (
                False,
                f"Unrecognized column '{col}' in recipe CSV.\n"
                f"Expected columns matching annotations/run_recipes_template.csv:\n"
                f"  vial, recipe_id, t200_ml, t400_ml, t100_ml, is_reference",
                df,
            )

    required_cols = ["vial", "recipe_id"]
    for col in required_cols:
        if col not in df.columns:
            return (
                False,
                f"Missing required column '{col}' in recipe CSV.\n"
                f"Please ensure your CSV matches annotations/run_recipes_template.csv.",
                df,
            )

    # Fill volume columns if missing or null
    for tank in ["t200_ml", "t400_ml", "t100_ml"]:
        if tank not in df.columns:
            df[tank] = 0.0
        else:
            df[tank] = pd.to_numeric(df[tank], errors="coerce").fillna(0.0)

    # Compute total_ml if not present
    if "total_ml" not in df.columns:
        df["total_ml"] = df["t200_ml"] + df["t400_ml"] + df["t100_ml"]
    else:
        df["total_ml"] = pd.to_numeric(df["total_ml"], errors="coerce").fillna(
            df["t200_ml"] + df["t400_ml"] + df["t100_ml"]
        )

    # 1. Refuse any vial with total_ml > 80 mL
    overfill = df[df["total_ml"] > 80.0]
    if len(overfill) > 0:
        bad_vial = overfill.iloc[0]["vial"]
        bad_vol = overfill.iloc[0]["total_ml"]
        bad_rec = overfill.iloc[0]["recipe_id"]
        return (
            False,
            f"Vial {bad_vial} (Recipe {bad_rec}) requests {bad_vol} mL, exceeding the station limit of 80 mL per vial.",
            df,
        )

    # 2. Refuse any recipe with fewer than 2 vials
    counts_by_recipe = df.groupby("recipe_id")["vial"].count()
    for rec_id, cnt in counts_by_recipe.items():
        if cnt < 2:
            return (
                False,
                f"Recipe {rec_id} has only {cnt} vial(s). Each recipe must have at least 2 vials so a clean reference vial can be established.",
                df,
            )

    # 3. Warn about T-300
    if "t300_ml" in df.columns:
        t300_used = df[pd.to_numeric(df["t300_ml"], errors="coerce").fillna(0.0) > 0.0]
        if len(t300_used) > 0:
            print("  [WARNING] Recipe list specifies T-300 volume, but Tank 300 is OUT OF SERVICE at CSI Station 3!")

    # 4. Warn about > 50 mL from T-200
    over_t200 = df[df["t200_ml"] > 50.0]
    if len(over_t200) > 0:
        print(f"  [WARNING] {len(over_t200)} vial(s) request > 50 mL from T-200 (station limit is <= 50 mL).")

    return True, "", df


def assign_references(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns is_reference boolean column.
    If is_reference is missing or empty, designates the last vial of each
    contiguous run of the same recipe as True, and others False.
    """
    df = df.copy()

    # Check if is_reference is present and populated
    has_valid_refs = False
    if "is_reference" in df.columns:
        valid_series = df["is_reference"].dropna().astype(str).str.strip().str.lower()
        if len(valid_series) > 0 and valid_series.iloc[0] in ["true", "false", "1", "0"]:
            df["is_reference"] = valid_series.isin(["true", "1"])
            has_valid_refs = True

    if not has_valid_refs:
        # Auto-assign: last vial of each contiguous block of same recipe
        is_ref_list = []
        n = len(df)
        for i in range(n):
            curr_rec = df.iloc[i]["recipe_id"]
            if i == n - 1:
                is_ref_list.append(True)
            else:
                next_rec = df.iloc[i + 1]["recipe_id"]
                is_ref_list.append(bool(curr_rec != next_rec))
        df["is_reference"] = is_ref_list

    return df


def check_camera_alignment(
    video_path: Path,
    df_vials: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Verifies that the camera has not moved by checking that measurement
    patches do not collide with or touch the detected glass edges on any vial frame.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False, f"Could not open video file: {video_path}"

    violations = []
    for idx, r in df_vials.iterrows():
        v = int(r["vial"])
        f = int(r["frame"])

        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            cap.release()
            return False, f"Could not read frame {f} for vial {v}"

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Check LOW patch
        l_low, r_low = detect_glass_edges(gray, LOW_PATCH["y_min"], LOW_PATCH["y_max"])
        if LOW_PATCH["x_min"] <= l_low:
            violations.append(f"Vial {v} (frame {f}): LOW patch touches left glass wall ({LOW_PATCH['x_min']} <= {l_low})")
        if LOW_PATCH["x_max"] >= r_low:
            violations.append(f"Vial {v} (frame {f}): LOW patch touches right glass wall ({LOW_PATCH['x_max']} >= {r_low})")

        # Check HIGH patch
        l_high, r_high = detect_glass_edges(gray, HIGH_PATCH["y_min"], HIGH_PATCH["y_max"])
        if HIGH_PATCH["x_min"] <= l_high:
            violations.append(f"Vial {v} (frame {f}): HIGH patch touches left glass wall ({HIGH_PATCH['x_min']} <= {l_high})")
        if HIGH_PATCH["x_max"] >= r_high:
            violations.append(f"Vial {v} (frame {f}): HIGH patch touches right glass wall ({HIGH_PATCH['x_max']} >= {r_high})")

    cap.release()

    if len(violations) > 0:
        msg = (
            "Camera alignment check failed! One or more measurement patches touch the vial glass walls:\n"
            + "\n".join(f"  - {viol}" for viol in violations[:5])
        )
        if len(violations) > 5:
            msg += f"\n  ... and {len(violations) - 5} more violations."
        msg += "\nThe camera may have been bumped or re-aimed since calibration."
        return False, msg

    return True, ""


def build_new_run(
    video_path: Path,
    recipes_csv: Path,
    name: str,
    min_fill_de: float = DEFAULT_MIN_FILL_DE,
) -> Path:
    """
    Main pipeline function for Step 2.
    """
    video_path = Path(video_path)
    recipes_csv = Path(recipes_csv)
    out_dir = REPO_ROOT / "outputs" / "runs" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=======================================================")
    print(f"BUILDING NEW RUN: {name}")
    print(f"Video:   {video_path}")
    print(f"Recipes: {recipes_csv}")
    print(f"Output:  {out_dir}")
    print(f"=======================================================\n")

    if not video_path.exists():
        print(
            f"ERROR: Video file not found: {video_path}\n"
            f"Please check the path to your vial_fill recording (.mp4).",
            file=sys.stderr,
        )
        sys.exit(1)

    cap_test = cv2.VideoCapture(str(video_path))
    if not cap_test.isOpened():
        print(
            f"ERROR: Could not open video file: {video_path}\n"
            f"Please verify that the file is a valid, readable MP4 video.",
            file=sys.stderr,
        )
        sys.exit(1)
    cap_test.release()

    if not recipes_csv.exists():
        print(
            f"ERROR: Recipe list file not found: {recipes_csv}\n"
            f"Please create one using annotations/run_recipes_template.csv as a guide.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        df_recipes_raw = pd.read_csv(recipes_csv)
    except Exception as e:
        print(
            f"ERROR: Failed to read recipe list CSV ({recipes_csv}):\n  {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    is_valid, err_msg, df_recipes = validate_recipes(df_recipes_raw)
    if not is_valid:
        print(f"\nERROR in recipe list:\n{err_msg}\n", file=sys.stderr)
        sys.exit(1)

    print(f"1. Validated recipe list ({len(df_recipes)} rows).")

    # 2. Run detect_parked_vials
    print(f"2. Detecting parked vials in video...")
    df_vials, df_rejected = detect_parked_vials(
        video_path=video_path,
        name=name,
        out_dir=out_dir,
        save_outputs=True,
        min_fill_de=min_fill_de,
        return_rejected=True,
    )

    n_vials = len(df_vials)
    n_recipes = len(df_recipes)

    # 3. Check counts
    if n_vials != n_recipes:
        contact_sheet_path = out_dir / "contact_sheet.png"
        print("\n" + "=" * 70, file=sys.stderr)
        print("COUNT MISMATCH ERROR: PARKED VIALS != RECIPES", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(f"Detected parked vials from video: {n_vials}", file=sys.stderr)
        print(f"Vials in recipe list:             {n_recipes}\n", file=sys.stderr)
        print(f"Please inspect the contact sheet to check which vial(s) were missed or extra:", file=sys.stderr)
        print(f"  {contact_sheet_path}\n", file=sys.stderr)

        print("Rejected parked intervals in video:", file=sys.stderr)
        if len(df_rejected) == 0:
            print("  (None — all candidate intervals met the fill threshold)", file=sys.stderr)
        else:
            for _, rej in df_rejected.iterrows():
                int_num = int(rej["interval"])
                f_num = int(rej["frame"])
                s_num = float(rej["mp4_s"])
                de_val = float(rej["fill_dE"])
                l_val = float(rej["low_L"])
                print(
                    f"  - Interval {int_num:2d}: Frame {f_num:5d} ({s_num:6.1f}s) | "
                    f"LOW dE: {de_val:5.2f} | L*: {l_val:4.1f}",
                    file=sys.stderr,
                )

        print(
            f"\nTip: If a pale or clear fill was rejected, lower the fill threshold using:\n"
            f"  python scripts/new_run.py --video <video.mp4> --recipes <recipes.csv> --name {name} --min-fill-de <value>\n"
            f"  (Current cut point: {min_fill_de:.1f})\n",
            file=sys.stderr,
        )
        print("=" * 70 + "\n", file=sys.stderr)
        sys.exit(1)

    print(f"3. Vial count matches recipe list: exactly {n_vials} vials.")

    # 4. Check camera alignment
    print("4. Checking camera alignment (glass edge detection on all vials)...")
    cam_ok, cam_msg = check_camera_alignment(video_path, df_vials)
    if not cam_ok:
        print(f"\nERROR: {cam_msg}\n", file=sys.stderr)
        sys.exit(1)
    print("   Camera alignment verified: all patches remain cleanly inside glass edges.")

    # 5. Assign reference vials
    df_recipes = assign_references(df_recipes)
    ref_count = int(df_recipes["is_reference"].sum())
    print(f"5. Reference vials assigned: {ref_count} reference vials.")

    # 6. Build combined run table
    df_out = pd.DataFrame()
    df_out["vial"] = df_recipes["vial"].astype(int)
    df_out["recipe_id"] = df_recipes["recipe_id"].astype(int)
    df_out["total_ml"] = df_recipes["total_ml"].astype(int)
    df_out["t200_ml"] = df_recipes["t200_ml"].astype(float)
    df_out["t400_ml"] = df_recipes["t400_ml"].astype(float)
    df_out["t100_ml"] = df_recipes["t100_ml"].astype(float)
    df_out["last_parked_frame"] = df_vials["frame"].astype(int)
    df_out["last_parked_mp4_s"] = df_vials["mp4_s"].astype(float)
    df_out["is_reference"] = df_recipes["is_reference"].astype(bool)

    out_csv = out_dir / "vials.csv"
    df_out.to_csv(out_csv, index=False)
    print(f"\nSaved run table: {out_csv} ({len(df_out)} rows)\n")

    # Print summary table
    print("Run Table Summary:")
    print(f"{'Vial':4s}  {'Recipe':6s}  {'tot_ml':6s}  {'Frame':7s}  {'mp4_s':7s}  {'Reference?'}")
    print("-" * 50)
    for _, r in df_out.iterrows():
        ref_str = "YES (clean reference)" if r["is_reference"] else "no"
        print(
            f"{int(r['vial']):4d}  {int(r['recipe_id']):6d}  {int(r['total_ml']):6d}  "
            f"{int(r['last_parked_frame']):7d}  {float(r['last_parked_mp4_s']):7.1f}  {ref_str}"
        )
    print("-" * 50)

    return out_csv


def main():
    parser = argparse.ArgumentParser(
        description="Turn a vial_fill recording and a recipe list into a verified run table."
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
        help="Path to vial_fill video .mp4 file",
    )
    parser.add_argument(
        "--recipes",
        type=Path,
        required=True,
        help="Path to recipe CSV file (matching annotations/run_recipes_template.csv)",
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Run name (output directory outputs/runs/<name>/)",
    )
    parser.add_argument(
        "--min-fill-de",
        "--min_fill_de",
        dest="min_fill_de",
        type=float,
        default=DEFAULT_MIN_FILL_DE,
        help=f"Minimum ΔE2000 in LOW patch between start and end of parked interval to count as filled (default: {DEFAULT_MIN_FILL_DE})",
    )

    args = parser.parse_args()
    build_new_run(
        video_path=args.video,
        recipes_csv=args.recipes,
        name=args.name,
        min_fill_de=args.min_fill_de,
    )


if __name__ == "__main__":
    main()

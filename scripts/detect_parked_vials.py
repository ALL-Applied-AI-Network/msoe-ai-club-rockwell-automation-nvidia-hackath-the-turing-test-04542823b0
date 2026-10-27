"""scripts/detect_parked_vials.py
New-recording mode Step 1: Finds the last parked frame of every filled vial directly
from any vial_fill MP4 video, without any label file.

Algorithm:
1. Scans video sequentially measuring frame-to-frame motion in the starwheel and neighbour
   regions outside the center filling stream:
   - Left starwheel pocket: x in [140, 270], y in [300, 460]
   - Right starwheel pocket / neighbour: x in [350, 480], y in [300, 460]
2. Computes average frame diff and smoothes with a 5-frame moving window.
3. Detects sustained starwheel indexing moves (smoothed motion > 2.0 for >= 20 frames).
4. For each index move, examines the parked candidate interval between the previous rotation
   and this index move:
   - first_parked_frame: frame right after previous rotation ended (prev_end + 5)
   - last_parked_frame: frame right before this rotation begins (start - 3)
5. Verifies liquid fill by measuring CIELAB ΔE2000 in the LOW patch (x: 302-318, y: 352-372)
   between first and last parked frames:
   - Liquid fill produces a robust color/absorption change (ΔE >= 8.0, Video 5 vials range 13.9 - 24.3).
   - Empty pockets or bare conveyor have near-zero change during parked interval (ΔE <= 2.6).
   - Keeps L* only as a diagnostic.
6. Outputs:
   - outputs/runs/<name>/parked_vials.csv (vial, frame, mp4_s)
   - outputs/runs/<name>/contact_sheet.png (all detected frames with LOW and HIGH patches)
7. If comparing against ground truth (e.g. Video 5 corrected annotations):
   - Reports vial count, extras, misses, frame deltas, and runs scripts/vial_check.py
     color check at found vs known frames.

Usage:
  python scripts/detect_parked_vials.py --video data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4 --name video5_practice
  python scripts/detect_parked_vials.py --video data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_1.mp4 --name video1
"""

import argparse
import math
from pathlib import Path
import sys
import colour
import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Portable stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Fixed measurement patch coordinates
LOW_PATCH = {
    "x_min": 302,
    "x_max": 318,
    "y_min": 352,
    "y_max": 372,
    "name": "LOW",
}

HIGH_PATCH = {
    "x_min": 302,
    "x_max": 318,
    "y_min": 268,
    "y_max": 288,
    "name": "HIGH",
}

# Cut point midway between largest empty pocket change (2.63) and smallest fill change (6.54)
DEFAULT_MIN_FILL_DE = 4.6


def extract_low_patch_lab(frame: np.ndarray) -> np.ndarray:
    """Extracts median CIELAB color of the LOW patch."""
    low_crop = frame[
        LOW_PATCH["y_min"] : LOW_PATCH["y_max"],
        LOW_PATCH["x_min"] : LOW_PATCH["x_max"],
    ]
    rgb_crop = cv2.cvtColor(low_crop, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(rgb_crop, axis=(0, 1)) / 255.0
    xyz = colour.sRGB_to_XYZ(med_srgb)
    lab = colour.XYZ_to_Lab(xyz)
    return lab


def detect_parked_vials(
    video_path: Path,
    name: str = "run",
    out_dir: Path | None = None,
    save_outputs: bool = True,
    lead_frames: int = 3,
    min_fill_de: float = DEFAULT_MIN_FILL_DE,
    return_rejected: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    """
    Finds last parked frames for all filled vials in the video.

    Parameters:
        video_path: Path to vial_fill video (.mp4)
        name: Name of run (subfolder in outputs/runs/)
        out_dir: Optional custom output directory (defaults to outputs/runs/<name>)
        save_outputs: If True, writes parked_vials.csv and contact_sheet.png
        lead_frames: Number of frames before index motion onset to sample parked vial (default 3)
        min_fill_de: Minimum ΔE2000 change in LOW patch during parked interval to count as filled (default 4.6)
        return_rejected: If True, returns (df_vials, df_rejected) tuple instead of just df_vials

    Returns:
        pd.DataFrame with columns ['vial', 'frame', 'mp4_s', 'fill_dE', 'low_L']
        (or tuple of (df_vials, df_rejected) if return_rejected is True).
        Note: df_vials.attrs['rejected'] also always contains df_rejected.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print(f"Scanning video: {video_path.name} ({total_frames} frames, {fps:.1f} fps)...")

    # Read first frame
    ret, prev = cap.read()
    if not ret:
        cap.release()
        raise RuntimeError("Failed to read first frame from video.")

    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    prev_left = prev_gray[300:460, 140:270]
    prev_right = prev_gray[300:460, 350:480]

    diffs = []
    f = 1
    # Sequential scan measuring starwheel motion
    while f < total_frames:
        ret, curr = cap.read()
        if not ret:
            break
        curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
        curr_left = curr_gray[300:460, 140:270]
        curr_right = curr_gray[300:460, 350:480]

        d_l = np.mean(np.abs(curr_left.astype(float) - prev_left.astype(float)))
        d_r = np.mean(np.abs(curr_right.astype(float) - prev_right.astype(float)))
        diffs.append((d_l + d_r) / 2.0)

        prev_left = curr_left
        prev_right = curr_right
        f += 1

    diffs = np.array(diffs)
    # 5-frame moving average smoothing
    smoothed = np.convolve(diffs, np.ones(5) / 5.0, mode="same")

    # Detect sustained motion events (index moves)
    is_motion = smoothed > 2.0
    blocks = []
    in_block = False
    block_start = 0

    for i, m in enumerate(is_motion):
        frame_num = i + 1
        if m:
            if not in_block:
                in_block = True
                block_start = frame_num
        else:
            if in_block:
                in_block = False
                duration = frame_num - block_start
                # Starwheel rotation lasts >= 20 frames
                if duration >= 20:
                    blocks.append((block_start, frame_num, duration))

    print(f"Detected {len(blocks)} candidate index moves.")

    # Check each candidate move for liquid fill change in LOW patch during parked interval
    detected_vials = []
    rejected_intervals = []
    saved_frames = {}
    prev_end = 0

    for idx, (s, e, dur) in enumerate(blocks):
        first_frame = min(prev_end + 5, max(0, s - 30))
        target_frame = max(0, s - lead_frames)

        cap.set(cv2.CAP_PROP_POS_FRAMES, first_frame)
        ret1, frame_first = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret2, frame_last = cap.read()

        if not (ret1 and ret2):
            prev_end = e
            continue

        lab_first = extract_low_patch_lab(frame_first)
        lab_last = extract_low_patch_lab(frame_last)
        fill_dE = float(colour.delta_E(lab_first, lab_last, method="CIE 2000"))
        l_star = float(lab_last[0])

        is_filled = bool(fill_dE >= min_fill_de)

        if is_filled:
            vial_num = len(detected_vials) + 1
            mp4_s = round(target_frame / fps, 3)
            detected_vials.append(
                {
                    "vial": vial_num,
                    "frame": target_frame,
                    "mp4_s": mp4_s,
                    "fill_dE": round(fill_dE, 2),
                    "low_L": round(l_star, 1),
                }
            )
            saved_frames[vial_num] = frame_last
        else:
            rejected_intervals.append(
                {
                    "interval": idx + 1,
                    "first_frame": first_frame,
                    "frame": target_frame,
                    "mp4_s": round(target_frame / fps, 3),
                    "fill_dE": round(fill_dE, 2),
                    "low_L": round(l_star, 1),
                }
            )

        prev_end = e

    cap.release()

    df_results = pd.DataFrame(detected_vials)
    df_rejected = pd.DataFrame(rejected_intervals)
    df_results.attrs["rejected"] = df_rejected

    if save_outputs:
        if out_dir is None:
            repo_root = Path(__file__).resolve().parent.parent
            target_out = repo_root / "outputs" / "runs" / name
        else:
            target_out = Path(out_dir)

        target_out.mkdir(parents=True, exist_ok=True)

        # 1. Save parked_vials.csv
        csv_path = target_out / "parked_vials.csv"
        df_to_save = df_results[["vial", "frame", "mp4_s"]]
        df_to_save.to_csv(csv_path, index=False)
        print(f"Saved: {csv_path} ({len(df_results)} vials)")

        # 2. Save rejected_intervals.csv if any
        if len(df_rejected) > 0:
            rej_path = target_out / "rejected_intervals.csv"
            df_rejected.to_csv(rej_path, index=False)

        # 3. Generate contact sheet
        if len(detected_vials) > 0:
            sheet_path = target_out / "contact_sheet.png"
            create_contact_sheet(detected_vials, saved_frames, sheet_path, name)
            print(f"Saved contact sheet: {sheet_path}")

    if return_rejected:
        return df_results, df_rejected
    return df_results


def create_contact_sheet(
    vials_list: list[dict],
    frames_dict: dict[int, np.ndarray],
    out_path: Path,
    title_name: str,
):
    """Generates contact sheet with LOW and HIGH patches clearly drawn."""
    n_vials = len(vials_list)
    if n_vials == 0:
        return

    n_cols = 5 if n_vials >= 10 else min(n_vials, 4)
    n_rows = math.ceil(n_vials / n_cols)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 3.2 * n_rows))
    if n_rows == 1 and n_cols == 1:
        axes = np.array([axes])
    axes = np.array(axes).flatten()

    for i, vial_info in enumerate(vials_list):
        ax = axes[i]
        v_num = vial_info["vial"]
        f_num = vial_info["frame"]
        s_time = vial_info["mp4_s"]
        fill_de = vial_info.get("fill_dE", 0.0)
        l_star = vial_info.get("low_L", 0.0)
        frame = frames_dict[v_num].copy()

        # Draw LOW patch (blue / cyan box)
        cv2.rectangle(
            frame,
            (LOW_PATCH["x_min"], LOW_PATCH["y_min"]),
            (LOW_PATCH["x_max"], LOW_PATCH["y_max"]),
            (255, 0, 0),
            2,
        )
        cv2.putText(
            frame,
            "LOW",
            (LOW_PATCH["x_min"] - 38, LOW_PATCH["y_min"] + 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 0, 0),
            1,
            cv2.LINE_AA,
        )

        # Draw HIGH patch (lime green box)
        cv2.rectangle(
            frame,
            (HIGH_PATCH["x_min"], HIGH_PATCH["y_min"]),
            (HIGH_PATCH["x_max"], HIGH_PATCH["y_max"]),
            (0, 255, 0),
            2,
        )
        cv2.putText(
            frame,
            "HIGH",
            (HIGH_PATCH["x_min"] - 42, HIGH_PATCH["y_min"] + 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )

        # Convert to RGB for matplotlib
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ax.imshow(frame_rgb)
        ax.set_title(
            f"Vial {v_num:02d} | F:{f_num} ({s_time:.1f}s)\nΔE_fill:{fill_de:.1f} | L*:{l_star:.1f}",
            fontsize=9,
            fontweight="bold",
        )
        ax.axis("off")

    # Turn off any unused subplots
    for j in range(n_vials, len(axes)):
        axes[j].axis("off")

    fig.suptitle(f"Detected Parked Vials — Run: {title_name} ({n_vials} vials)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def verify_against_ground_truth(
    df_found: pd.DataFrame,
    annotations_csv: Path,
    video_path: Path,
):
    """
    Compares found frames against known ground truth annotations.
    Checks:
    1. Count of found vs known
    2. Extras / misses
    3. Frame delta for each vial
    4. scripts/vial_check.py color check verdicts at found vs known frames
    """
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.vial_check import load_references, check_vial

    df_known = pd.read_csv(annotations_csv)
    n_known = len(df_known)
    n_found = len(df_found)

    print("\n" + "=" * 70)
    print("VERIFICATION AGAINST GROUND TRUTH ANNOTATIONS")
    print("=" * 70)
    print(f"Known vials in annotations: {n_known}")
    print(f"Detected vials by script:  {n_found}")

    extras = max(0, n_found - n_known)
    misses = max(0, n_known - n_found)
    print(f"Extras: {extras}")
    print(f"Misses: {misses}")

    cap = cv2.VideoCapture(str(video_path))
    refs = load_references(times_csv=annotations_csv, video_mp4=video_path)
    ref_vials = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30]

    print("\nPer-vial Frame Comparison & Color Check Verdicts:")
    print(
        f"{'Vial':4s}  {'Recipe':6s}  {'tot_ml':6s}  {'Known_F':7s}  {'Found_F':7s}  {'Delta':6s}  |  "
        f"{'Fill_dE':7s}  {'low_L':5s}  |  {'Known_dE':8s}  {'Found_dE':8s}  {'Verdict':8s}  | {'Match?'}"
    )
    print("-" * 105)

    diff_verdict_count = 0
    max_abs_delta = 0

    for i in range(min(n_known, n_found)):
        r_known = df_known.iloc[i]
        r_found = df_found.iloc[i]

        v_num = int(r_known["vial"])
        rec_id = int(r_known["recipe_id"])
        tot_ml = int(r_known["total_ml"])
        kf = int(r_known["last_parked_frame"])
        ff = int(r_found["frame"])
        fill_de = float(r_found["fill_dE"]) if "fill_dE" in r_found else 0.0
        low_l = float(r_found["low_L"]) if "low_L" in r_found else 0.0
        delta = ff - kf
        max_abs_delta = max(max_abs_delta, abs(delta))

        is_ref = (v_num in ref_vials)

        # Check known frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, kf)
        ret, frame_k = cap.read()
        res_k = check_vial(frame_k, rec_id, tot_ml, refs, is_reference=is_ref)

        # Check found frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, ff)
        ret, frame_f = cap.read()
        res_f = check_vial(frame_f, rec_id, tot_ml, refs, is_reference=is_ref)

        v_match = (res_k["verdict"] == res_f["verdict"])
        if not v_match:
            diff_verdict_count += 1
        match_str = "YES" if v_match else f"DIFF ({res_k['verdict']} vs {res_f['verdict']})"

        print(
            f"{v_num:4d}  {rec_id:6d}  {tot_ml:6d}  {kf:7d}  {ff:7d}  {delta:+6d}  |  "
            f"{fill_de:7.1f}  {low_l:5.1f}  |  "
            f"{res_k['delta_e']:8.2f}  {res_f['delta_e']:8.2f}  {res_k['verdict']:8s}  | {match_str}"
        )

    cap.release()

    print("-" * 105)
    print(f"Maximum frame delta: {max_abs_delta} frames (threshold: within 15 frames)")
    print(f"Color check verdict differences: {diff_verdict_count} / {min(n_known, n_found)}")

    within_15 = max_abs_delta <= 15
    counts_match = (n_found == n_known)
    verdicts_match = (diff_verdict_count == 0)

    print("\nVerification Checklist:")
    print(f"  [ {'OK' if counts_match else 'FAIL'} ] Exactly {n_known} vials found (0 extras, 0 misses)")
    print(f"  [ {'OK' if within_15 else 'FAIL'} ] All frames within 15 frames of known (max delta = {max_abs_delta})")
    print(f"  [ {'OK' if verdicts_match else 'FAIL'} ] 100% of color check verdicts match at found frames")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Detect last parked frames of filled vials from vial_fill video."
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
        help="Path to vial_fill video .mp4 file",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="run",
        help="Run name for output directory outputs/runs/<name>/",
    )
    parser.add_argument(
        "--out_dir",
        type=Path,
        default=None,
        help="Custom output directory (overrides outputs/runs/<name>/)",
    )
    parser.add_argument(
        "--min-fill-de",
        "--min_fill_de",
        dest="min_fill_de",
        type=float,
        default=DEFAULT_MIN_FILL_DE,
        help=f"Minimum ΔE2000 in LOW patch between start and end of parked interval to count as filled (default: {DEFAULT_MIN_FILL_DE})",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="Path to ground truth annotations CSV to compare against (e.g. video5_vial_times_corrected.csv)",
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    # Detect vials
    df_found = detect_parked_vials(
        video_path=args.video,
        name=args.name,
        out_dir=args.out_dir,
        save_outputs=True,
        min_fill_de=args.min_fill_de,
    )

    # Auto-compare against Video 5 ground truth if applicable or requested
    annotations_csv = args.compare
    if annotations_csv is None and "video_5" in str(args.video):
        cand = repo_root / "annotations" / "video5_vial_times_corrected.csv"
        if cand.exists():
            annotations_csv = cand

    if annotations_csv is not None and annotations_csv.exists():
        verify_against_ground_truth(df_found, annotations_csv, args.video)


if __name__ == "__main__":
    main()

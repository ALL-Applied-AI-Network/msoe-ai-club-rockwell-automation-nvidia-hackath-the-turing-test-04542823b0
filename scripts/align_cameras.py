"""
scripts/align_cameras.py
Aligns images across all three camera stations (cap_seal, tank_level, vial_fill)
to the moment each labeled vial finishes filling (Video 5).

For each of the 30 labeled vials:
1. Calculates the exact fill end timestamp.
2. Scans the image folders for all 3 cameras and reads the timestamp from each filename.
3. Finds the single nearest frame for each camera.
4. Calculates the time gap (in seconds) between the nearest frame and the fill end time.
5. Saves the aligned table to outputs/aligned_camera_frames.csv.
"""

import sys
from datetime import datetime
from pathlib import Path
import re
import pandas as pd

# Import time base conversion
sys.path.insert(0, str(Path(__file__).resolve().parent))
from time_base import mp4_to_real, MP4_T0_DATETIME

# Regex pattern to extract YYYYMMDD_HHMMSS_microseconds from filenames
TIMESTAMP_PATTERN = re.compile(r"(\d{8})_(\d{6})_(\d{6})")


def parse_timestamp_from_filename(filename: str) -> datetime:
    """Extracts datetime from filename: {camera}_{YYYYMMDD}_{HHMMSS}_{microseconds}.jpg"""
    match = TIMESTAMP_PATTERN.search(filename)
    if not match:
        raise ValueError(
            f"Could not extract timestamp from filename: {filename}"
        )
    date_str, time_str, us_str = match.group(1), match.group(2), match.group(3)
    return datetime.strptime(
        f"{date_str}_{time_str}_{us_str}", "%Y%m%d_%H%M%S_%f"
    )


def load_camera_frames(camera_images_dir: Path) -> pd.DataFrame:
    """Loads all frames for a camera, extracts timestamps from filenames, and sorts by time."""
    records = []
    for img_path in camera_images_dir.glob("*.jpg"):
        # Ignore duplicate download copies if present (e.g., '(1)')
        if "(1)" in img_path.name:
            continue
        try:
            ts = parse_timestamp_from_filename(img_path.name)
            records.append({"filename": img_path.name, "timestamp": ts})
        except ValueError:
            continue

    df = pd.DataFrame(records)
    if df.empty:
        raise RuntimeError(f"No valid images found in {camera_images_dir}")

    return df.sort_values("timestamp").reset_index(drop=True)


def align_cameras():
    # Set up project paths
    base_dir = Path(__file__).resolve().parent.parent
    dataset_dir = base_dir / "data" / "csi-vial-fill-dataset"
    recipes_file = (
        dataset_dir / "vial_fill" / "labels" / "video5_vial_recipes.csv"
    )
    frame_labels_file = (
        dataset_dir / "vial_fill" / "labels" / "video5_frame_labels.csv"
    )
    output_dir = base_dir / "outputs"
    output_csv = output_dir / "aligned_camera_frames.csv"

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load ground truth recipe labels
    recipes_df = pd.read_csv(recipes_file)

    video_t0 = MP4_T0_DATETIME
    print(
        f"Video 5 MP4 start reference time (t=0): {video_t0.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
    )

    # 2. Load all available camera frames by parsing timestamps from filenames
    cameras = ["cap_seal", "tank_level", "vial_fill"]
    camera_frames = {}
    for cam in cameras:
        cam_dir = dataset_dir / cam / "images"
        camera_frames[cam] = load_camera_frames(cam_dir)
        print(f"Loaded {len(camera_frames[cam])} frames for camera: {cam}")

    # 3. For each labeled vial, find the nearest frame in each camera
    alignment_records = []
    for _, vial_row in recipes_df.iterrows():
        vial_num = int(vial_row["vial"])
        recipe_id = int(vial_row["recipe_id"])
        fill_end_mp4_s = float(vial_row["end_s"])

        # Convert MP4 playback seconds to real wall-clock datetime using time_base.py
        fill_end_ts = mp4_to_real(fill_end_mp4_s, as_datetime=True)
        fill_end_real_s = mp4_to_real(fill_end_mp4_s, as_datetime=False)

        record = {
            "vial": vial_num,
            "recipe_id": recipe_id,
            "fill_end_s": round(fill_end_mp4_s, 3),
            "fill_end_real_s": round(fill_end_real_s, 3),
            "fill_end_timestamp": fill_end_ts.strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        # Find nearest frame in each of the 3 cameras
        for cam in cameras:
            cam_df = camera_frames[cam]
            time_diffs = (cam_df["timestamp"] - fill_end_ts).abs()
            nearest_idx = time_diffs.idxmin()
            nearest_row = cam_df.iloc[nearest_idx]

            gap_seconds = (
                nearest_row["timestamp"] - fill_end_ts
            ).total_seconds()

            record[f"{cam}_filename"] = nearest_row["filename"]
            record[f"{cam}_time_gap_s"] = round(gap_seconds, 3)

        alignment_records.append(record)

    # 4. Save results to CSV
    aligned_df = pd.DataFrame(alignment_records)
    aligned_df.to_csv(output_csv, index=False)

    print(f"\nAlignment complete! Saved {len(aligned_df)} rows to: {output_csv}")
    print("\nFirst 3 aligned vials preview:")
    preview_cols = [
        "vial",
        "recipe_id",
        "cap_seal_filename",
        "cap_seal_time_gap_s",
        "vial_fill_filename",
        "vial_fill_time_gap_s",
    ]
    print(aligned_df[preview_cols].head(3).to_string(index=False))


if __name__ == "__main__":
    align_cameras()

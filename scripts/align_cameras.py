"""
scripts/align_cameras.py
Aligns images across all three camera stations (cap_seal, tank_level, vial_fill)
to the moment each labeled vial finishes filling (Video 5).

For each of the 30 labeled vials:
1. Calculates the exact fill end timestamp (converting MP4 seconds to real time via scripts/time_base.py).
2. For vials 1–24: matches the nearest captured still image across all 3 cameras (all within < 1.0 s).
3. For vials 25–30 (where still camera stopped saving after 20:15:27): extracts the exact frame
   from each camera's Video 5 MP4 file (all within < 0.04 s).
4. Saves extracted MP4 frames to outputs/aligned_mp4_frames/.
5. Adds a 'source' column ('still' or 'mp4') and saves the aligned table to outputs/aligned_camera_frames.csv.
"""

from datetime import datetime
from pathlib import Path
import re
import sys
import cv2
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
    output_dir = base_dir / "outputs"
    output_csv = output_dir / "aligned_camera_frames.csv"
    mp4_frames_dir = output_dir / "aligned_mp4_frames"

    output_dir.mkdir(parents=True, exist_ok=True)
    mp4_frames_dir.mkdir(parents=True, exist_ok=True)

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

    # Open MP4 video captures for fallback alignment
    video_caps = {}
    for cam in cameras:
        vid_path = dataset_dir / cam / "videos" / f"{cam}_video_5.mp4"
        if vid_path.exists():
            video_caps[cam] = cv2.VideoCapture(str(vid_path))
        else:
            print(f"Warning: MP4 video not found: {vid_path}")
            video_caps[cam] = None

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

        # Check nearest still frame in each camera
        still_gaps = {}
        still_rows = {}
        for cam in cameras:
            cam_df = camera_frames[cam]
            time_diffs = (cam_df["timestamp"] - fill_end_ts).abs()
            nearest_idx = time_diffs.idxmin()
            nearest_row = cam_df.iloc[nearest_idx]
            gap_seconds = (
                nearest_row["timestamp"] - fill_end_ts
            ).total_seconds()
            still_gaps[cam] = gap_seconds
            still_rows[cam] = nearest_row

        # If any camera has no still frame within 2.0s, take frame from MP4 video instead
        use_mp4 = any(abs(gap) > 2.0 for gap in still_gaps.values())
        source = "mp4" if use_mp4 else "still"
        record["source"] = source

        if not use_mp4:
            for cam in cameras:
                record[f"{cam}_filename"] = still_rows[cam]["filename"]
                record[f"{cam}_time_gap_s"] = round(still_gaps[cam], 3)
        else:
            # Extract frame from MP4 video for each camera
            # All three share 50,942 frames at 30.0 fps container rate and 1.2158x time base
            target_frame_idx = int(round(fill_end_mp4_s * 30.0))
            frame_mp4_s = target_frame_idx / 30.0
            frame_ts = mp4_to_real(frame_mp4_s, as_datetime=True)
            mp4_gap_s = (frame_ts - fill_end_ts).total_seconds()

            for cam in cameras:
                cap = video_caps[cam]
                frame_filename = f"{cam}_video5_vial{vial_num}_frame{target_frame_idx}.jpg"
                out_frame_path = mp4_frames_dir / frame_filename

                if cap is not None and not out_frame_path.exists():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
                    ret, frame_img = cap.read()
                    if ret:
                        cv2.imwrite(str(out_frame_path), frame_img)
                    else:
                        print(f"Warning: Could not read frame {target_frame_idx} from {cam} video.")

                record[f"{cam}_filename"] = frame_filename
                record[f"{cam}_time_gap_s"] = round(mp4_gap_s, 3)

        alignment_records.append(record)

    # Release video captures
    for cap in video_caps.values():
        if cap is not None:
            cap.release()

    # 4. Save results to CSV
    aligned_df = pd.DataFrame(alignment_records)
    aligned_df.to_csv(output_csv, index=False)

    print(f"\nAlignment complete! Saved {len(aligned_df)} rows to: {output_csv}")
    print("\nPreview of aligned table (first 3 and last 3 vials):")
    preview_cols = [
        "vial",
        "recipe_id",
        "source",
        "vial_fill_filename",
        "vial_fill_time_gap_s",
    ]
    print(pd.concat([aligned_df.head(3), aligned_df.tail(3)])[preview_cols].to_string(index=False))


if __name__ == "__main__":
    align_cameras()

"""
scripts/replay_feed.py
Card 10, Step 2: Replay feed for Video 5.

Hands out the 30 recorded vials of Video 5 in order, as if they were arriving live.
Reads frame at last_parked_frame from annotations/video5_vial_times_corrected.csv
and data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4.

Each vial item provides:
- vial: number (1 to 30)
- recipe_id: target recipe ID (5 to 14)
- previous_vial_recipe: recipe of previous vial (None for vial 1)
- batch_previous_recipe: recipe before this vial's batch started (None for Recipe 5)
- total_ml: total liquid volume in mL
- mp4_time: elapsed video time (seconds)
- frame: BGR image (or None if with_frames=False)

CLI:
- python scripts/replay_feed.py --vial 7 --save scratch/replay_v7.jpg
- python scripts/replay_feed.py --list
"""

import argparse
from pathlib import Path
import sys
from typing import Generator, NamedTuple
import cv2
import numpy as np
import pandas as pd

# Portable encoding support for stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_TIMES_CSV = Path("annotations/video5_vial_times_corrected.csv")
DEFAULT_VIDEO_MP4 = Path("data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4")


class VialFeedItem(NamedTuple):
    vial: int
    recipe_id: int
    previous_vial_recipe: int | None
    batch_previous_recipe: int | None
    total_ml: int
    mp4_time: float
    frame: np.ndarray | None


def get_batch_previous_recipe(recipe_id: int) -> int | None:
    """Returns the recipe before this recipe batch began (None for Recipe 5)."""
    if recipe_id <= 5:
        return None
    return recipe_id - 1


def iter_vials(
    times_csv: Path = DEFAULT_TIMES_CSV,
    video_mp4: Path = DEFAULT_VIDEO_MP4,
    with_frames: bool = True,
) -> Generator[VialFeedItem, None, None]:
    """
    Yields each of the 30 vials from Video 5 in sequential order.

    Yields:
        VialFeedItem with (vial, recipe_id, previous_vial_recipe, batch_previous_recipe, total_ml, mp4_time, frame)
    """
    df = pd.read_csv(times_csv).sort_values("vial").reset_index(drop=True)

    cap = None
    if with_frames:
        cap = cv2.VideoCapture(str(video_mp4))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {video_mp4}")

    try:
        for idx, row in df.iterrows():
            v = int(row["vial"])
            rec_id = int(row["recipe_id"])
            tot_ml = int(row["total_ml"])
            mp4_s = round(float(row["last_parked_mp4_s"]), 3)
            f_idx = int(row["last_parked_frame"])

            # previous_vial_recipe: None for vial 1, else recipe of previous vial
            prev_vial_rec = None if idx == 0 else int(df.loc[idx - 1, "recipe_id"])
            # batch_previous_recipe: recipe that ran before this batch (None for Recipe 5)
            batch_prev_rec = get_batch_previous_recipe(rec_id)

            frame = None
            if with_frames and cap is not None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                ret, frame = cap.read()
                if not ret:
                    raise RuntimeError(f"Could not read frame {f_idx} for vial {v}")

            yield VialFeedItem(
                vial=v,
                recipe_id=rec_id,
                previous_vial_recipe=prev_vial_rec,
                batch_previous_recipe=batch_prev_rec,
                total_ml=tot_ml,
                mp4_time=mp4_s,
                frame=frame,
            )
    finally:
        if cap is not None:
            cap.release()


def get_vial(
    vial_num: int,
    times_csv: Path = DEFAULT_TIMES_CSV,
    video_mp4: Path = DEFAULT_VIDEO_MP4,
    with_frame: bool = True,
) -> VialFeedItem:
    """Fetches a single vial item by vial number."""
    df = pd.read_csv(times_csv).set_index("vial")
    if vial_num not in df.index:
        raise ValueError(f"Vial {vial_num} not found in {times_csv}")

    row = df.loc[vial_num]
    rec_id = int(row["recipe_id"])
    tot_ml = int(row["total_ml"])
    mp4_s = round(float(row["last_parked_mp4_s"]), 3)
    f_idx = int(row["last_parked_frame"])

    prev_vial_rec = None if vial_num == 1 else int(df.loc[vial_num - 1, "recipe_id"])
    batch_prev_rec = get_batch_previous_recipe(rec_id)

    frame = None
    if with_frame:
        cap = cv2.VideoCapture(str(video_mp4))
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {video_mp4}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"Could not read frame {f_idx} for vial {vial_num}")

    return VialFeedItem(
        vial=vial_num,
        recipe_id=rec_id,
        previous_vial_recipe=prev_vial_rec,
        batch_previous_recipe=batch_prev_rec,
        total_ml=tot_ml,
        mp4_time=mp4_s,
        frame=frame,
    )


def run_list(times_csv: Path = DEFAULT_TIMES_CSV):
    """Prints all 30 vials without reading frames from the MP4 video."""
    print("=" * 82)
    print("VIDEO 5 REPLAY FEED: 30 VIALS IN ORDER")
    print("=" * 82)
    print(f"{'Vial':<6} {'Recipe':<8} {'Batch Pos':<11} {'Prev Vial Rec':<15} {'Batch Prev Rec':<16} {'Total mL':<10} {'MP4 Time':<10}")
    print("-" * 82)

    for item in iter_vials(times_csv=times_csv, with_frames=False):
        batch_pos = ((item.vial - 1) % 3) + 1
        prev_v_str = str(item.previous_vial_recipe) if item.previous_vial_recipe is not None else "None"
        batch_prev_str = str(item.batch_previous_recipe) if item.batch_previous_recipe is not None else "None"
        print(
            f"{item.vial:<6d} {item.recipe_id:<8d} {batch_pos:<11d} {prev_v_str:<15} "
            f"{batch_prev_str:<16} {item.total_ml:<10d} {item.mp4_time:>7.2f} s"
        )
    print("=" * 82)


def run_single(vial_num: int, save_path: str | None = None):
    """Prints details of a single vial and optionally saves its frame."""
    item = get_vial(vial_num, with_frame=True)
    prev_v_str = str(item.previous_vial_recipe) if item.previous_vial_recipe is not None else "None"
    batch_prev_str = str(item.batch_previous_recipe) if item.batch_previous_recipe is not None else "None"
    batch_pos = ((item.vial - 1) % 3) + 1

    print("=" * 60)
    print(f"REPLAY FEED: Vial {item.vial}")
    print("=" * 60)
    print(f"Recipe ID             : {item.recipe_id}")
    print(f"Batch Position        : {batch_pos} of 3")
    print(f"Previous Vial Recipe  : {prev_v_str}")
    print(f"Batch Previous Recipe : {batch_prev_str}")
    print(f"Total Volume          : {item.total_ml} mL")
    print(f"MP4 Time              : {item.mp4_time:.3f} s ({int(item.mp4_time // 60)}m {item.mp4_time % 60:04.1f}s)")
    if item.frame is not None:
        print(f"Frame Shape           : {item.frame.shape} (H x W x C)")

    if save_path:
        out_p = Path(save_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if item.frame is not None:
            cv2.imwrite(str(out_p), item.frame)
            print(f"Saved Frame Image     : {out_p}")
        else:
            print(f"Warning: No frame captured to save to {out_p}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Replay feed for Video 5 vials.")
    parser.add_argument("--vial", type=int, default=None, help="Vial number (1 to 30) to inspect")
    parser.add_argument("--save", type=str, default=None, help="Path to save frame image (e.g. scratch/replay_v7.jpg)")
    parser.add_argument("--list", action="store_true", help="Print all 30 vials without reading video frames")
    args = parser.parse_args()

    if args.list:
        run_list()
    elif args.vial is not None:
        run_single(args.vial, args.save)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

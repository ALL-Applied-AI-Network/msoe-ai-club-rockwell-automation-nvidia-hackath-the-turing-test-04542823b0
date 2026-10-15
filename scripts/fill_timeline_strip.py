"""
scripts/fill_timeline_strip.py
Generates visual timeline contact strips for vial_fill frames from Video 5.
1. outputs/card2/fill_timeline_250_340.png (frames between 250s and 340s)
2. outputs/card2/fill_timeline_0_90.png (frames between 0s and 90s, vials 1-3)

Gets vial numbers and in_fill status from annotations/video5_vial_times_corrected.csv
using time_base.py to convert real timestamps to MP4 time.
"""

from datetime import datetime
import math
from pathlib import Path
import sys
import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from time_base import real_to_mp4, MP4_T0_DATETIME


def make_timeline_strip(
    df: pd.DataFrame,
    start_s: float,
    end_s: float,
    output_path: Path,
    title: str,
    images_dir: Path,
):
    sub = (
        df[(df["video_s"] >= start_s) & (df["video_s"] <= end_s)]
        .sort_values("video_s")
        .reset_index(drop=True)
    )
    n_frames = len(sub)
    if n_frames == 0:
        print(f"No frames found between {start_s}s and {end_s}s.")
        return

    n_cols = 9
    n_rows = math.ceil(n_frames / n_cols)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(22, n_rows * 2.6))
    fig.patch.set_facecolor("#f8f9fa")
    axes_flat = axes.flatten()

    for idx, (_, row) in enumerate(sub.iterrows()):
        ax = axes_flat[idx]
        img_path = images_dir / row["filename"]

        if img_path.exists():
            img_bgr = cv2.imread(str(img_path))
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            ax.imshow(img_rgb)
        else:
            ax.text(
                0.5,
                0.5,
                "Image Missing",
                ha="center",
                va="center",
                fontsize=8,
            )

        ax.set_xticks([])
        ax.set_yticks([])

        # Determine label text from corrected vial annotations
        vial_val = (
            f"Vial {int(row['vial'])}" if pd.notna(row["vial"]) else "No Vial"
        )
        in_fill_val = int(row["in_fill"])
        video_s_val = row["video_s"]

        # Color-code border depending on in_fill
        border_color = "#198754" if in_fill_val == 1 else "#6c757d"
        for spine in ax.spines.values():
            spine.set_color(border_color)
            spine.set_linewidth(2 if in_fill_val == 1 else 1)

        label_text = f"{video_s_val:.1f}s | {vial_val} | in_fill={in_fill_val}"
        ax.set_xlabel(
            label_text,
            fontsize=8,
            fontweight="bold",
            color="#212529",
            labelpad=4,
        )

    for idx in range(n_frames, len(axes_flat)):
        axes_flat[idx].axis("off")

    plt.suptitle(
        f"{title} ({n_frames} frames, ~2s interval)",
        fontsize=15,
        fontweight="bold",
        y=0.99,
        color="#1a1a1a",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.98])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved: {output_path} ({n_frames} frames)")


def main():
    base_dir = Path(__file__).resolve().parent.parent
    vial_times_file = base_dir / "annotations" / "video5_vial_times_corrected.csv"
    frame_labels_raw = (
        base_dir
        / "data"
        / "csi-vial-fill-dataset"
        / "vial_fill"
        / "labels"
        / "video5_frame_labels.csv"
    )
    images_dir = (
        base_dir / "data" / "csi-vial-fill-dataset" / "vial_fill" / "images"
    )
    outputs_dir = base_dir / "outputs" / "card2"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    if not vial_times_file.exists():
        raise FileNotFoundError(f"Vial times file not found: {vial_times_file}")
    if not frame_labels_raw.exists():
        raise FileNotFoundError(f"Raw frame labels not found: {frame_labels_raw}")

    vial_times = pd.read_csv(vial_times_file)
    raw_df = pd.read_csv(frame_labels_raw)

    # Recompute vial number and in_fill for each frame from annotations/video5_vial_times_corrected.csv
    corrected_records = []
    for _, row in raw_df.iterrows():
        ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
        real_s = (ts - MP4_T0_DATETIME).total_seconds()
        mp4_s = real_to_mp4(ts)

        matching = vial_times[
            (vial_times["mp4_start_s"] <= mp4_s)
            & (mp4_s <= vial_times["mp4_end_s"])
        ]
        if len(matching) > 0:
            v_match = matching.iloc[0]
            vial_num = int(v_match["vial"])
            in_fill = 1
        else:
            vial_num = None
            in_fill = 0

        corrected_records.append(
            {
                "filename": row["filename"],
                "timestamp": row["timestamp"],
                "video_s": real_s,
                "mp4_s": mp4_s,
                "in_fill": in_fill,
                "vial": vial_num,
            }
        )

    df = pd.DataFrame(corrected_records)

    # 1. Strip between 250s and 340s
    strip_250_340 = outputs_dir / "fill_timeline_250_340.png"
    make_timeline_strip(
        df=df,
        start_s=250.0,
        end_s=340.0,
        output_path=strip_250_340,
        title="vial_fill Timeline: 250s to 340s (Corrected Vials)",
        images_dir=images_dir,
    )

    # 2. Strip between 0s and 90s (vials 1-3)
    strip_0_90 = outputs_dir / "fill_timeline_0_90.png"
    make_timeline_strip(
        df=df,
        start_s=0.0,
        end_s=90.0,
        output_path=strip_0_90,
        title="vial_fill Timeline: 0s to 90s (Vials 1–3, Corrected Vials)",
        images_dir=images_dir,
    )


if __name__ == "__main__":
    main()

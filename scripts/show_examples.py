"""
scripts/show_examples.py
Generates a contact sheet (a 3x4 grid) of 12 sample frames from the vial_fill
station during active dosing, labeled with each frame's Recipe ID, Vial number,
and timestamp.

Vial numbers and Recipe IDs are resolved from annotations/video5_vial_times_corrected.csv
using time_base.py.
Saves the resulting image to outputs/card1/vial_fill_examples.png.
"""

from datetime import datetime
from pathlib import Path
import sys
import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from time_base import real_to_mp4, MP4_T0_DATETIME
import re

TIMESTAMP_PATTERN = re.compile(r"(\d{8})_(\d{6})_(\d{6})")


def generate_contact_sheet():
    base_dir = Path(__file__).resolve().parent.parent
    vial_times_path = base_dir / "annotations" / "video5_vial_times_corrected.csv"
    frame_labels_path = (
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
    output_dir = base_dir / "outputs" / "card1"
    output_file = output_dir / "vial_fill_examples.png"

    output_dir.mkdir(parents=True, exist_ok=True)

    if not vial_times_path.exists():
        raise FileNotFoundError(f"Vial times file not found: {vial_times_path}")
    if not images_dir.exists():
        raise FileNotFoundError(f"Images folder not found: {images_dir}")

    vial_times_df = pd.read_csv(vial_times_path)

    # Load video 5 still frames
    if frame_labels_path.exists():
        frames_df = pd.read_csv(frame_labels_path)
    else:
        # Fallback to scanning directory
        records = []
        for p in sorted(images_dir.glob("vial_fill_*.jpg")):
            m = TIMESTAMP_PATTERN.search(p.name)
            if m:
                ts_str = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]} {m.group(2)[:2]}:{m.group(2)[2:4]}:{m.group(2)[4:6]}.{m.group(3)}"
                records.append({"filename": p.name, "timestamp": ts_str})
        frames_df = pd.DataFrame(records)

    # Determine vial and in_fill using annotations/video5_vial_times_corrected.csv
    filled_frames = []
    for _, row in frames_df.iterrows():
        ts = datetime.strptime(str(row["timestamp"]), "%Y-%m-%d %H:%M:%S.%f")
        mp4_s = real_to_mp4(ts)

        match = vial_times_df[
            (vial_times_df["mp4_start_s"] <= mp4_s)
            & (mp4_s <= vial_times_df["mp4_end_s"])
        ]
        if len(match) > 0:
            v_info = match.iloc[0]
            filled_frames.append(
                {
                    "filename": row["filename"],
                    "timestamp": row["timestamp"],
                    "vial": int(v_info["vial"]),
                    "recipe_id": int(v_info["recipe_id"]),
                }
            )

    filled_df = pd.DataFrame(filled_frames)

    if len(filled_df) < 12:
        raise ValueError(
            f"Expected at least 12 filled frames, found {len(filled_df)}"
        )

    # Select 12 evenly spaced frames across the dataset
    indices = np.linspace(0, len(filled_df) - 1, 12, dtype=int)
    selected_frames = filled_df.iloc[indices]

    # Create a 3x4 grid figure
    fig, axes = plt.subplots(3, 4, figsize=(16, 11))
    fig.patch.set_facecolor("#f8f9fa")

    for ax, (_, row) in zip(axes.flatten(), selected_frames.iterrows()):
        image_path = images_dir / row["filename"]
        if not image_path.exists():
            print(f"Warning: Image file not found: {image_path}")
            continue

        img = cv2.imread(str(image_path))
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        ax.imshow(img_rgb)
        ax.axis("off")

        recipe_id = int(row["recipe_id"])
        vial_num = int(row["vial"])
        raw_ts = str(row["timestamp"])
        display_ts = raw_ts.split(".")[0] if "." in raw_ts else raw_ts

        title_text = (
            f"Recipe {recipe_id} (Vial {vial_num})\nTimestamp: {display_ts}"
        )
        ax.set_title(
            title_text,
            fontsize=10,
            fontweight="bold",
            pad=8,
            color="#212529",
        )

    plt.suptitle(
        "CSI Vial-Fill Station — 12 Sample Dosing Frames (Video 5, Corrected Labels)",
        fontsize=16,
        fontweight="bold",
        y=0.98,
        color="#1a1a1a",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    plt.savefig(output_file, dpi=200, facecolor=fig.get_facecolor())
    plt.close()

    print(f"Contact sheet successfully saved to: {output_file}")


if __name__ == "__main__":
    generate_contact_sheet()

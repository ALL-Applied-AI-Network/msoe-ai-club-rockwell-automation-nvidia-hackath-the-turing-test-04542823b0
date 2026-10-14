"""
scripts/fill_timeline_strip.py
Generates visual timeline contact strips for vial_fill frames from Video 5.
1. outputs/fill_timeline_250_340.png (frames between 250s and 340s)
2. outputs/fill_timeline_0_90.png (frames between 0s and 90s, vials 1-3)

Each frame displays the image with its video_s, vial number, and in_fill value printed underneath.
"""

import math
from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


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

    # Determine grid layout: aim for ~8-9 columns
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

        # Determine label text
        vial_val = (
            f"Vial {int(row['vial'])}" if pd.notna(row["vial"]) else "No Vial"
        )
        in_fill_val = int(row["in_fill"])
        video_s_val = row["video_s"]

        # Color-code border or text depending on in_fill
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

    # Turn off unused subplots
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
    labels_file = (
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
    outputs_dir = base_dir / "outputs"

    if not labels_file.exists():
        raise FileNotFoundError(f"Labels file not found: {labels_file}")

    df = pd.read_csv(labels_file)

    # 1. Strip between 250s and 340s
    strip_250_340 = outputs_dir / "fill_timeline_250_340.png"
    make_timeline_strip(
        df=df,
        start_s=250.0,
        end_s=340.0,
        output_path=strip_250_340,
        title="vial_fill Timeline: 250s to 340s",
        images_dir=images_dir,
    )

    # 2. Strip between 0s and 90s (vials 1-3)
    strip_0_90 = outputs_dir / "fill_timeline_0_90.png"
    make_timeline_strip(
        df=df,
        start_s=0.0,
        end_s=90.0,
        output_path=strip_0_90,
        title="vial_fill Timeline: 0s to 90s (Vials 1–3)",
        images_dir=images_dir,
    )


if __name__ == "__main__":
    main()

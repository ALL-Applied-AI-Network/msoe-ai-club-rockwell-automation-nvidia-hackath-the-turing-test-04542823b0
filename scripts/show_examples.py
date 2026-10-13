"""
scripts/show_examples.py
Generates a contact sheet (a 3x4 grid) of 12 sample frames from the vial_fill
station during dosing, labeled with each frame's Recipe ID and timestamp.
Saves the resulting image to the outputs/ directory.
"""

from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def generate_contact_sheet():
    # Define project directories
    base_dir = Path(__file__).resolve().parent.parent
    labels_path = (
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
    output_dir = base_dir / "outputs"
    output_file = output_dir / "vial_fill_examples.png"

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if dataset files exist
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels file not found at: {labels_path}")
    if not images_dir.exists():
        raise FileNotFoundError(f"Images folder not found at: {images_dir}")

    # Load frame labels and filter for frames captured during active vial fills
    df = pd.read_csv(labels_path)
    filled_frames = df[df["in_fill"] == 1].reset_index(drop=True)

    if len(filled_frames) < 12:
        raise ValueError(
            f"Expected at least 12 filled frames, found {len(filled_frames)}"
        )

    # Select 12 evenly spaced frames across the dataset
    indices = np.linspace(0, len(filled_frames) - 1, 12, dtype=int)
    selected_frames = filled_frames.iloc[indices]

    # Create a 3x4 grid figure
    fig, axes = plt.subplots(3, 4, figsize=(16, 11))
    fig.patch.set_facecolor("#f8f9fa")

    for ax, (_, row) in zip(axes.flatten(), selected_frames.iterrows()):
        image_path = images_dir / row["filename"]
        if not image_path.exists():
            print(f"Warning: Image file not found: {image_path}")
            continue

        # Read image using OpenCV and convert BGR to RGB
        img = cv2.imread(str(image_path))
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Display image
        ax.imshow(img_rgb)
        ax.axis("off")

        # Label each image with Recipe ID, Vial number, and Timestamp
        recipe_id = int(row["recipe_id"])
        vial_num = int(row["vial"])
        # Format timestamp to readable string (drop microsecond fraction if desired)
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
        "CSI Vial-Fill Station — 12 Sample Dosing Frames (Video 5)",
        fontsize=16,
        fontweight="bold",
        y=0.98,
        color="#1a1a1a",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    # Save final contact sheet
    plt.savefig(output_file, dpi=200, facecolor=fig.get_facecolor())
    plt.close()

    print(f"Contact sheet successfully saved to: {output_file}")


if __name__ == "__main__":
    generate_contact_sheet()

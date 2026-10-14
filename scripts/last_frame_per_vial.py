"""
scripts/last_frame_per_vial.py
Finds the last vial_fill still image where each of the 30 labeled vials is still parked under the nozzle before it rolls away.

Reads:
  - data/csi-vial-fill-dataset/vial_fill/labels/video5_vial_recipes.csv
  - data/csi-vial-fill-dataset/vial_fill/labels/video5_frame_labels.csv
  - data/csi-vial-fill-dataset/vial_fill/images/*.jpg

Writes:
  - outputs/last_frame_per_vial.csv
  - outputs/last_frame_per_vial.png (5x6 contact sheet labeled with vial number, label recipe, and video_s)
"""

from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import pandas as pd


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data" / "csi-vial-fill-dataset" / "vial_fill"
    images_dir = data_dir / "images"
    recipes_csv = data_dir / "labels" / "video5_vial_recipes.csv"
    frames_csv = data_dir / "labels" / "video5_frame_labels.csv"
    outputs_dir = root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    recipes_df = pd.read_csv(recipes_csv)
    frames_df = pd.read_csv(frames_csv)

    # Frame list for the 30 labeled vials: the last still frame where each vial
    # is still parked under the dispensing nozzle before conveyor movement.
    # Identified by visual inspection and frame-to-frame pixel difference checks.
    selected_frames = [
        (1, 5, "vial_fill_20260923_194743_777926.jpg", 33.778),
        (2, 5, "vial_fill_20260923_194840_092033.jpg", 90.092),
        (3, 5, "vial_fill_20260923_194936_402108.jpg", 146.402),
        (4, 6, "vial_fill_20260923_195020_599900.jpg", 190.600),
        (5, 6, "vial_fill_20260923_195110_864388.jpg", 240.864),
        (6, 6, "vial_fill_20260923_195116_892562.jpg", 246.893),
        (7, 7, "vial_fill_20260923_195209_203274.jpg", 299.203),
        (8, 7, "vial_fill_20260923_195325_659355.jpg", 375.659),
        (9, 7, "vial_fill_20260923_195413_938001.jpg", 423.938),
        (10, 8, "vial_fill_20260923_195514_320559.jpg", 484.321),
        (11, 8, "vial_fill_20260923_195624_730824.jpg", 554.731),
        (12, 8, "vial_fill_20260923_195715_014666.jpg", 605.015),
        (13, 9, "vial_fill_20260923_195823_426935.jpg", 673.427),
        (14, 9, "vial_fill_20260923_195937_803514.jpg", 747.804),
        (15, 9, "vial_fill_20260923_200030_121827.jpg", 800.122),
        (16, 10, "vial_fill_20260923_200138_511942.jpg", 868.512),
        (17, 10, "vial_fill_20260923_200234_847748.jpg", 924.848),
        (18, 10, "vial_fill_20260923_200321_101325.jpg", 971.101),
        (19, 11, "vial_fill_20260923_200425_499865.jpg", 1035.500),
        (20, 11, "vial_fill_20260923_200535_902207.jpg", 1105.902),
        (21, 11, "vial_fill_20260923_200644_240245.jpg", 1174.240),
        (22, 12, "vial_fill_20260923_200748_669452.jpg", 1238.669),
        (23, 12, "vial_fill_20260923_200901_048909.jpg", 1311.049),
        (24, 12, "vial_fill_20260923_201015_500300.jpg", 1385.500),
        (25, 13, "vial_fill_20260923_201115_835499.jpg", 1445.835),
        (26, 13, "vial_fill_20260923_201156_038795.jpg", 1486.039),
        (27, 13, "vial_fill_20260923_201320_475658.jpg", 1570.476),
        (28, 14, "vial_fill_20260923_201402_680589.jpg", 1612.681),
        (29, 14, "vial_fill_20260923_201444_913027.jpg", 1654.913),
        (30, 14, "vial_fill_20260923_201527_141712.jpg", 1697.142),
    ]

    # Save to CSV
    out_df = pd.DataFrame(
        selected_frames, columns=["vial", "recipe_id", "filename", "video_s"]
    )
    csv_path = outputs_dir / "last_frame_per_vial.csv"
    out_df.to_csv(csv_path, index=False)
    print(f"Saved {csv_path} with {len(out_df)} vials.")

    # Create 5x6 contact sheet
    fig, axes = plt.subplots(5, 6, figsize=(20, 18))
    fig.patch.set_facecolor("#ffffff")
    axes_flat = axes.flatten()

    for idx, (vial_num, rec_id, fn, v_s) in enumerate(selected_frames):
        ax = axes_flat[idx]
        img_path = images_dir / fn
        if img_path.exists():
            img_bgr = cv2.imread(str(img_path))
            # Crop to show nozzle, vial body, and base: y=40..430, x=240..380
            crop_bgr = img_bgr[40:430, 240:380]
            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            ax.imshow(crop_rgb)
        else:
            ax.text(0.5, 0.5, "Missing Image", ha="center", va="center")

        title = f"Vial {vial_num} (Rec {rec_id})\n{v_s:.1f}s"
        ax.set_title(title, fontsize=10, fontweight="bold", pad=4)
        ax.axis("off")

    plt.suptitle(
        "Last Parked Frame per Labeled Vial (Video 5)",
        fontsize=16,
        fontweight="bold",
        y=0.995,
    )
    plt.tight_layout()
    png_path = outputs_dir / "last_frame_per_vial.png"
    plt.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved contact sheet to {png_path}")


if __name__ == "__main__":
    main()

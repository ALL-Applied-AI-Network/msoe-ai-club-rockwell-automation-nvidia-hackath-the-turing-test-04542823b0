"""
scripts/show_aligned_frames.py
Generates a side-by-side visual comparison for vials 1, 7, and 20.
For each vial, displays frames from vial_fill, tank_level, and cap_seal
side by side in a 3x3 grid, reading image filenames from outputs/card2/aligned_camera_frames.csv.
Saves the resulting image to outputs/card2/aligned_check.png.
"""

from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import pandas as pd


def show_aligned_frames():
    base_dir = Path(__file__).resolve().parent.parent
    csv_path = base_dir / "outputs" / "card2" / "aligned_camera_frames.csv"
    data_dir = base_dir / "data" / "csi-vial-fill-dataset"
    mp4_frames_dir = base_dir / "outputs" / "card2" / "aligned_mp4_frames"
    output_png = base_dir / "outputs" / "card2" / "aligned_check.png"

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Aligned frames CSV not found at: {csv_path}\nPlease run scripts/align_cameras.py first."
        )

    df = pd.read_csv(csv_path)

    # Filter for target vials 1, 7, and 20
    target_vials = [1, 7, 20]
    subset = df[df["vial"].isin(target_vials)].sort_values("vial")

    if len(subset) != len(target_vials):
        raise ValueError(
            f"Expected {len(target_vials)} vials, found {len(subset)}"
        )

    # Order of cameras across columns: vial_fill, tank_level, cap_seal
    camera_order = ["vial_fill", "tank_level", "cap_seal"]

    fig, axes = plt.subplots(len(target_vials), 3, figsize=(15, 12))
    fig.patch.set_facecolor("#f8f9fa")

    for row_idx, (_, row) in enumerate(subset.iterrows()):
        vial_num = int(row["vial"])
        recipe_id = int(row["recipe_id"])

        for col_idx, cam in enumerate(camera_order):
            ax = axes[row_idx, col_idx]
            filename = row[f"{cam}_filename"]
            img_path = data_dir / cam / "images" / filename
            if not img_path.exists():
                mp4_img_path = mp4_frames_dir / filename
                if mp4_img_path.exists():
                    img_path = mp4_img_path

            if not img_path.exists():
                ax.text(
                    0.5,
                    0.5,
                    f"Image not found:\n{filename}",
                    ha="center",
                    va="center",
                )
                ax.axis("off")
                continue

            img_bgr = cv2.imread(str(img_path))
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

            ax.imshow(img_rgb)
            ax.axis("off")

            # Label each picture with vial number, recipe, and camera name
            gap = row[f"{cam}_time_gap_s"]
            ax.set_title(
                f"Vial {vial_num} (Recipe {recipe_id}) — {cam}\nGap: {gap:+.3f}s",
                fontsize=11,
                fontweight="bold",
                pad=6,
                color="#1a1a1a",
            )

    plt.suptitle(
        "Aligned Camera Frames Check: Vials 1, 7, 20 (vial_fill | tank_level | cap_seal)",
        fontsize=15,
        fontweight="bold",
        y=0.98,
        color="#111827",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    output_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_png, dpi=200, facecolor=fig.get_facecolor())
    plt.close()

    print(f"Aligned frames check image saved to: {output_png}")


if __name__ == "__main__":
    show_aligned_frames()

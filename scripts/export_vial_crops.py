"""
scripts/export_vial_crops.py
Card 3b, Step 1: Export liquid-only crops for all 30 vials and build manifest.

Extracts liquid-only regions between the inner glass walls (x in [288, 330]),
from 5 px below the meniscus to 5 px above the base, from the exact last parked
mp4 frame recorded in annotations/video5_vial_times_corrected.csv.
Resizes crops so the short side is at least 224 px (aspect ratio preserved).

Reads:
- annotations/video5_vial_times_corrected.csv
- data/csi-vial-fill-dataset/vial_fill/labels/video5_vial_recipes.csv
- data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4

Writes:
- outputs/card3b/crops/vial01.png ... vial30.png
- outputs/card3b/manifest.csv
- scratch/card3b_crops.png (30-crop contact sheet)
"""

from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Inner glass wall boundaries in 640x480 frame pixels (inside inner glass walls for all 30 vials)
INNER_X_MIN = 296
INNER_X_MAX = 322
MIN_SHORT_SIDE = 224


def export_vial_crops():
    times_csv = Path("annotations/video5_vial_times_corrected.csv")
    recipes_csv = Path("data/csi-vial-fill-dataset/vial_fill/labels/video5_vial_recipes.csv")
    video_mp4 = Path("data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4")

    crops_dir = Path("outputs/card3b/crops")
    crops_dir.mkdir(parents=True, exist_ok=True)
    scratch_dir = Path("scratch")
    scratch_dir.mkdir(parents=True, exist_ok=True)

    df_times = pd.read_csv(times_csv).set_index("vial")
    df_recipes = pd.read_csv(recipes_csv).set_index("vial")

    cap = cv2.VideoCapture(str(video_mp4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_mp4}")

    # Build unique recipe definition lookup (t100, t200, t400)
    recipe_lookup = {}
    for v in df_recipes.index:
        r_id = int(df_recipes.loc[v, "recipe_id"])
        if r_id not in recipe_lookup:
            t100 = 0 if pd.isna(df_recipes.loc[v, "t100_ml"]) else int(df_recipes.loc[v, "t100_ml"])
            t200 = 0 if pd.isna(df_recipes.loc[v, "t200_ml"]) else int(df_recipes.loc[v, "t200_ml"])
            t400 = 0 if pd.isna(df_recipes.loc[v, "t400_ml"]) else int(df_recipes.loc[v, "t400_ml"])
            recipe_lookup[r_id] = (t100, t200, t400)

    manifest_rows = []
    crops_for_sheet = []

    for v in range(1, 31):
        row_time = df_times.loc[v]
        f = int(row_time["last_parked_frame"])
        men_y = float(row_time["meniscus_y"])
        base_y = float(row_time["base_y"])
        r_id = int(row_time["recipe_id"])
        batch_pos = ((v - 1) % 3) + 1
        ref_vial = ((v - 1) // 3 + 1) * 3

        # Read exact last parked frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Could not read frame {f} for vial {v}")

        # Crop between inner glass walls and liquid boundaries
        y1 = int(round(men_y)) + 5
        y2 = int(round(base_y)) - 5
        crop = frame[y1:y2, INNER_X_MIN:INNER_X_MAX]

        # Resize so short side is at least 224 px (maintaining aspect ratio)
        h, w = crop.shape[:2]
        scale = float(MIN_SHORT_SIDE) / min(h, w)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        # Save individual crop
        crop_path = crops_dir / f"vial{v:02d}.png"
        cv2.imwrite(str(crop_path), resized)

        crops_for_sheet.append((v, r_id, batch_pos, resized))

        # Recipe amounts
        t100, t200, t400 = recipe_lookup[r_id]

        # Prior recipe amounts
        if r_id == 5:
            prev_recipe = ""
            prev_t100 = ""
            prev_t200 = ""
            prev_t400 = ""
        else:
            prev_r_id = r_id - 1
            prev_recipe = prev_r_id
            pt100, pt200, pt400 = recipe_lookup[prev_r_id]
            prev_t100 = pt100
            prev_t200 = pt200
            prev_t400 = pt400

        manifest_rows.append({
            "vial": v,
            "recipe": r_id,
            "previous_recipe": prev_recipe,
            "batch_position": batch_pos,
            "t100_ml": t100,
            "t200_ml": t200,
            "t400_ml": t400,
            "prev_t100_ml": prev_t100,
            "prev_t200_ml": prev_t200,
            "prev_t400_ml": prev_t400,
            "reference_vial": ref_vial,
        })

    cap.release()

    # Save manifest.csv
    manifest_df = pd.DataFrame(manifest_rows)
    manifest_path = Path("outputs/card3b/manifest.csv")
    manifest_df.to_csv(manifest_path, index=False)
    print(f"Saved manifest: {manifest_path} ({len(manifest_df)} rows)")

    # Save 30-crop contact sheet (3 rows x 10 cols)
    fig, axes = plt.subplots(3, 10, figsize=(20, 10))
    axes_flat = axes.flatten()

    for idx, (v, r_id, batch_pos, crop_bgr) in enumerate(crops_for_sheet):
        ax = axes_flat[idx]
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        ax.imshow(crop_rgb)
        ax.set_title(f"Vial {v:02d} (R{r_id} #{batch_pos})", fontsize=8, fontweight="bold")
        ax.axis("off")

    plt.suptitle("Card 3b: Liquid-Only Crops Across All 30 Vials (Inner Glass, No Labels/Holders)",
                 fontsize=12, fontweight="bold")
    plt.tight_layout()
    sheet_path = scratch_dir / "card3b_crops.png"
    plt.savefig(sheet_path, dpi=150)
    plt.close()
    print(f"Saved contact sheet: {sheet_path}")


if __name__ == "__main__":
    export_vial_crops()

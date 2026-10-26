"""Build feature table from twin dataset images for vial model training.

Card 8 Step 1:
One job: Extracts features from twin dataset labels for training regressors to predict
orange share, blue share, and detect recipe mismatch.

Features per twin image:
- Blank-normalized linear RGB of LOW patch (with camera-response gain applied)
- Blank-normalized linear RGB of HIGH patch (with camera-response gain applied; empty if fill < 60 mL)
- Fill volume (mL)
- Labels: orange_share, blue_share, category, is_clean, clean_recipe_id, mix_type
- Filter: keeps only unmixed images (mixing == 0.0) due to inverted twin mixing gradient

Reads:
- Dataset labels: outputs/card7/card7_dataset/batch_*/labels.csv
- Camera response curve: outputs/card7/camera_response.json (gain-only model)

Writes:
- Copied dataset labels: outputs/card7/dataset_labels/
- Feature table: outputs/card8/twin_features.csv

Execution:
    python scripts/build_twin_features.py
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Portable encoding support for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import colour
    HAS_COLOUR = True
except ImportError:
    HAS_COLOUR = False

DATASET_DIR = REPO_ROOT / "outputs" / "card7" / "card7_dataset"
LABELS_COPY_DIR = REPO_ROOT / "outputs" / "card7" / "dataset_labels"
CAMERA_RESP_JSON = REPO_ROOT / "outputs" / "card7" / "camera_response.json"
OUT_CSV = REPO_ROOT / "outputs" / "card8" / "twin_features.csv"

# Liquid volume threshold where HIGH patch is fully submerged (consistent with baseline_check.py)
HIGH_PATCH_MIN_ML = 60.0


def lab_to_linear(lab: np.ndarray) -> np.ndarray:
    """Convert CIELAB (D65) to linear RGB [0..1]."""
    if HAS_COLOUR:
        xyz = colour.Lab_to_XYZ(lab)
        srgb = colour.XYZ_to_sRGB(xyz)
        srgb_clipped = np.clip(srgb, 0.0, 1.0)
        return colour.models.eotf_sRGB(srgb_clipped)
    else:
        # Fallback approximation if colour-science is unavailable
        L, a, b = lab[0], lab[1], lab[2]
        fy = (L + 16.0) / 116.0
        fx = fy + (a / 500.0)
        fz = fy - (b / 200.0)
        delta = 6.0 / 29.0

        def f_inv(t):
            return t ** 3 if t > delta else 3.0 * (delta ** 2) * (t - 4.0 / 29.0)

        xr = f_inv(fx) * 0.95047
        yr = f_inv(fy) * 1.00000
        zr = f_inv(fz) * 1.08883
        xyz = np.array([xr, yr, zr])

        M_inv = np.array([
            [3.2404542, -1.5371385, -0.4985314],
            [-0.9692660, 1.8760108, 0.0415560],
            [0.0556434, -0.2040259, 1.0572252],
        ])
        srgb = np.clip(xyz @ M_inv.T, 0.0, 1.0)
        # Linear light
        return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)


def copy_labels_to_dataset_labels() -> List[Path]:
    """Copy all labels.csv from batches to outputs/card7/dataset_labels/."""
    LABELS_COPY_DIR.mkdir(parents=True, exist_ok=True)
    src_csvs = sorted(DATASET_DIR.glob("batch_*/labels.csv"))
    copied = []
    for p in src_csvs:
        batch_name = p.parent.name
        dst_flat = LABELS_COPY_DIR / f"{batch_name}_labels.csv"
        shutil.copy2(p, dst_flat)
        dst_sub = LABELS_COPY_DIR / batch_name / "labels.csv"
        dst_sub.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst_sub)
        copied.append(dst_flat)
    return copied


def load_gain_coefficients() -> np.ndarray:
    """Load gain-only camera response coefficients (a_R, a_G, a_B)."""
    if not CAMERA_RESP_JSON.is_file():
        raise FileNotFoundError(f"Missing camera response file: {CAMERA_RESP_JSON}")
    with open(CAMERA_RESP_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    gains = data["gain_only_model"]["coefficients"]
    return np.array([gains["R"]["a"], gains["G"]["a"], gains["B"]["a"]], dtype=np.float64)


def main():
    print("=" * 75)
    print("CARD 8 STEP 1: BUILD TWIN FEATURES (MIXING == 0 ONLY)")
    print("=" * 75)

    # 1. Copy dataset labels to outputs/card7/dataset_labels/
    copied_files = copy_labels_to_dataset_labels()
    print(f"Copied {len(copied_files)} labels.csv files into: {LABELS_COPY_DIR.relative_to(REPO_ROOT)}")

    # 2. Load all dataset rows
    batch_dfs = []
    for p in sorted(DATASET_DIR.glob("batch_*/labels.csv")):
        batch_dfs.append(pd.read_csv(p))
    if not batch_dfs:
        raise RuntimeError("No labels.csv found in dataset directory!")
    full_df = pd.concat(batch_dfs, ignore_index=True)
    total_rendered = len(full_df)
    print(f"Total synthetic dataset images: {total_rendered}")

    # 3. Filter for mixing == 0.0 only
    # Note: twin mixing gradient is inverted; mixed images used uncalibrated texture path.
    df = full_df[full_df["mixing"] == 0.0].copy()
    filtered_count = len(df)
    print(f"Filtered for unmixed images (mixing == 0.0): {filtered_count} / {total_rendered} rows")

    # 4. Load camera-response gain coefficients
    gains = load_gain_coefficients()
    print(f"Loaded gain-only camera response: R={gains[0]:.5f}, G={gains[1]:.5f}, B={gains[2]:.5f}")

    # 5. Extract features
    records = []
    for _, row in df.iterrows():
        fill_ml = float(row["fill_ml"])

        # LOW patch is always submerged and valid
        lab_low = np.array([float(row["norm_low_L"]), float(row["norm_low_a"]), float(row["norm_low_b"])])
        lin_low = lab_to_linear(lab_low)
        lin_low_corr = np.clip(lin_low * gains, 0.0, 1.0)

        # HIGH patch: filled only for tall vials (>= 60 mL)
        has_high = fill_ml >= HIGH_PATCH_MIN_ML
        if has_high:
            lab_high = np.array([float(row["norm_high_L"]), float(row["norm_high_a"]), float(row["norm_high_b"])])
            lin_high = lab_to_linear(lab_high)
            lin_high_corr = np.clip(lin_high * gains, 0.0, 1.0)
            high_r = round(float(lin_high_corr[0]), 6)
            high_g = round(float(lin_high_corr[1]), 6)
            high_b = round(float(lin_high_corr[2]), 6)
        else:
            high_r = np.nan
            high_g = np.nan
            high_b = np.nan

        is_clean = (str(row["category"]).strip().lower() == "clean")
        clean_rec = row["clean_recipe_id"] if pd.notna(row["clean_recipe_id"]) else np.nan

        records.append({
            "file": row["file"],
            "image_id": row["image_id"],
            "category": row["category"],
            "is_clean": is_clean,
            "clean_recipe_id": int(clean_rec) if pd.notna(clean_rec) else "",
            "mix_type": row["mix_type"],
            "fill_ml": round(fill_ml, 1),
            "orange_share": round(float(row["orange_share"]), 4),
            "blue_share": round(float(row["blue_share"]), 4),
            "mixing": float(row["mixing"]),
            "mixing_filter": "mixing==0",
            "has_high_patch": has_high,
            "low_r": round(float(lin_low_corr[0]), 6),
            "low_g": round(float(lin_low_corr[1]), 6),
            "low_b": round(float(lin_low_corr[2]), 6),
            "high_r": high_r,
            "high_g": high_g,
            "high_b": high_b,
            "raw_low_L": row["raw_low_L"],
            "raw_high_L": row["raw_high_L"],
            "norm_low_L": row["norm_low_L"],
            "norm_high_L": row["norm_high_L"],
            "glare": row["glare"],
            "light_brightness": row["light_brightness"],
            "color_temp_k": row["color_temp_k"],
        })

    feat_df = pd.DataFrame(records)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    feat_df.to_csv(OUT_CSV, index=False)
    print(f"Saved feature table: {OUT_CSV.relative_to(REPO_ROOT)} ({len(feat_df)} rows)")

    # 6. Summary Statistics & Reporting
    print("\n" + "-" * 75)
    print("TWIN FEATURES SUMMARY (mixing == 0.0)")
    print("-" * 75)
    print(f"Total row count:           {len(feat_df)}")
    print(f"Orange share range:        [{feat_df['orange_share'].min():.4f}, {feat_df['orange_share'].max():.4f}]")
    print(f"Blue share range:          [{feat_df['blue_share'].min():.4f}, {feat_df['blue_share'].max():.4f}]")
    print(f"Fill volume range:         [{feat_df['fill_ml'].min():.1f}, {feat_df['fill_ml'].max():.1f}] mL")

    # Clean recipe counts
    clean_sub = feat_df[feat_df["is_clean"]]
    print(f"\nClean vials total:         {len(clean_sub)}")
    print("Clean vials per recipe:")
    rec_counts = clean_sub["clean_recipe_id"].value_counts().sort_index()
    for rec_id, cnt in rec_counts.items():
        nom_vol = clean_sub[clean_sub["clean_recipe_id"] == rec_id]["fill_ml"].mean()
        print(f"  Recipe {int(rec_id):2d}: {cnt:2d} images (mean vol: {nom_vol:.1f} mL)")

    # Category breakdown
    print("\nCategory breakdown:")
    for cat, cnt in feat_df["category"].value_counts().items():
        print(f"  {cat:15s}: {cnt:3d} ({cnt / len(feat_df) * 100:.1f}%)")

    # Volume ranges
    v_25_45 = ((feat_df["fill_ml"] >= 25.0) & (feat_df["fill_ml"] <= 45.0)).sum()
    print(f"\nVials in 25–45 mL range:   {v_25_45:3d} ({v_25_45 / len(feat_df) * 100:.1f}%)")

    # High patch coverage
    no_high_60 = (~feat_df["has_high_patch"]).sum()
    with_high_60 = feat_df["has_high_patch"].sum()
    print(f"Vials with NO HIGH patch (< 60 mL):  {no_high_60:3d} ({no_high_60 / len(feat_df) * 100:.1f}%)")
    print(f"Vials with HIGH patch (>= 60 mL):     {with_high_60:3d} ({with_high_60 / len(feat_df) * 100:.1f}%)")

    print("=" * 75)


if __name__ == "__main__":
    main()

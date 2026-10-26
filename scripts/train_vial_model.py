"""Train vial dye-share regression models on digital twin data and choose flag threshold.

Card 8 Step 2:
One job: Trains two small scikit-learn regressors (Random Forest multi-output regressors)
to predict orange share and blue share purely from twin features:
1. Model LOW: trained on all vials using [low_r, low_g, low_b, fill_ml]
2. Model HIGH: trained on tall vials (fill >= 60 mL) using [high_r, high_g, high_b, low_r, low_g, low_b, fill_ml]

Validation split:
Holds out ~20% of twin images, split by whole clean recipes (Recipes 5 and 11, matching Card 7 hold-outs)
and whole contamination pairs (all carryover mixes involving Recipes 5 or 11), never random rows.

Threshold selection:
Evaluates share distance d = sqrt((pred_orange - rec_orange)^2 + (pred_blue - rec_blue)^2)
to intended recipe nominal shares on the twin hold-out set only.
Selects the decision threshold that best separates clean vials from carryover-contaminated vials.

Reads:
- Feature table: outputs/card8/twin_features.csv

Writes:
- Model LOW: outputs/card8/model_low.joblib
- Model HIGH: outputs/card8/model_high.joblib
- Threshold config: outputs/card8/model_threshold.json
- Hold-out predictions: outputs/card8/twin_holdout_predictions.csv

Execution:
    python scripts/train_vial_model.py
"""

import json
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, roc_auc_score
from sklearn.multioutput import MultiOutputRegressor

# Portable encoding support for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

FEATURES_CSV = REPO_ROOT / "outputs" / "card8" / "twin_features.csv"
OUT_DIR = REPO_ROOT / "outputs" / "card8"
MODEL_LOW_PATH = OUT_DIR / "model_low.joblib"
MODEL_HIGH_PATH = OUT_DIR / "model_high.joblib"
THRESHOLD_JSON_PATH = OUT_DIR / "model_threshold.json"
HOLDOUT_CSV_PATH = OUT_DIR / "twin_holdout_predictions.csv"

# CSI Station 3 Recipe Master Definitions (Dosing nominal shares and volumes)
PLANT_RECIPES = {
    5: {"orange": 0.3333, "blue": 0.3333, "ml": 30.0},
    6: {"orange": 0.2500, "blue": 0.0000, "ml": 40.0},
    7: {"orange": 0.0000, "blue": 0.7143, "ml": 70.0},
    8: {"orange": 0.3333, "blue": 0.3333, "ml": 60.0},
    9: {"orange": 0.4375, "blue": 0.4375, "ml": 80.0},
    10: {"orange": 0.2000, "blue": 0.2000, "ml": 75.0},
    11: {"orange": 0.1429, "blue": 0.7143, "ml": 70.0},
    12: {"orange": 0.7143, "blue": 0.1429, "ml": 70.0},
    13: {"orange": 0.7143, "blue": 0.2857, "ml": 70.0},
    14: {"orange": 0.0000, "blue": 0.1429, "ml": 70.0},
}

HELD_OUT_RECIPES = [5, 11]  # Clean recipes held out (one short 30 mL, one tall 70 mL)


def parse_contamination_pair(mix_type: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Parse carryover transition pair from mix_type string (e.g. carryover_R10->R13_a0.08)."""
    m = re.match(r"carryover_R(\d+)->R(\d+)", str(mix_type))
    if m:
        r_from = int(m.group(1))
        r_to = int(m.group(2))
        return f"R{r_from:02d}->R{r_to:02d}", r_from, r_to
    return None, None, None


def main():
    print("=" * 75)
    print("CARD 8 STEP 2: TRAIN VIAL REGRESSORS & CHOOSE THRESHOLD ON TWIN DATA")
    print("=" * 75)

    if not FEATURES_CSV.is_file():
        raise FileNotFoundError(f"Missing features file: {FEATURES_CSV}")

    df = pd.read_csv(FEATURES_CSV)
    print(f"Loaded features table: {FEATURES_CSV.relative_to(REPO_ROOT)} ({len(df)} rows)")

    # 1. Parse contamination pairs and assign intended recipes
    pairs, r_froms, r_tos = [], [], []
    intended_recipes = []
    for _, row in df.iterrows():
        p, rf, rt = parse_contamination_pair(row["mix_type"])
        pairs.append(p)
        r_froms.append(rf)
        r_tos.append(rt)

        if row["is_clean"]:
            intended_recipes.append(int(row["clean_recipe_id"]))
        elif row["category"] == "contaminated":
            intended_recipes.append(int(rt))
        else:
            intended_recipes.append(None)

    df["contam_pair"] = pairs
    df["r_from"] = r_froms
    df["r_to"] = r_tos
    df["intended_recipe"] = intended_recipes

    # 2. Split train vs. hold-out by whole clean recipe and contamination pair
    # Hold out whole Clean Recipes 5 & 11 (2 of 10 clean recipes = 20%)
    clean_held = df["is_clean"] & df["clean_recipe_id"].isin([float(r) for r in HELD_OUT_RECIPES])

    # Hold out all contamination pairs that involve Recipe 5 or Recipe 11 (from or to)
    contam_held = (df["category"] == "contaminated") & (
        df["r_from"].isin(HELD_OUT_RECIPES) | df["r_to"].isin(HELD_OUT_RECIPES)
    )

    df["is_held_out"] = clean_held | contam_held

    train_df = df[~df["is_held_out"]].copy()
    test_df = df[df["is_held_out"]].copy()

    n_total = len(df)
    n_train = len(train_df)
    n_test = len(test_df)
    pct_held = (n_test / n_total) * 100.0

    print(f"\nDataset Split (grouped by clean recipe and contamination pair):")
    print(f"  Training set:     {n_train:3d} images ({100 - pct_held:4.1f}%)")
    print(f"  Hold-out set:     {n_test:3d} images ({pct_held:4.1f}%)")
    print(f"    - Clean hold-out:       {clean_held.sum():2d} images (Recipes {HELD_OUT_RECIPES})")
    print(f"    - Contaminated hold-out:{contam_held.sum():2d} images (pairs involving {HELD_OUT_RECIPES})")

    # 3. Train Model LOW: [low_r, low_g, low_b, fill_ml] -> [orange_share, blue_share]
    features_low = ["low_r", "low_g", "low_b", "fill_ml"]
    X_train_low = train_df[features_low].values
    y_train_low = train_df[["orange_share", "blue_share"]].values

    print("\nTraining Model LOW (features: low_r, low_g, low_b, fill_ml)...")
    model_low = MultiOutputRegressor(RandomForestRegressor(n_estimators=100, random_state=42))
    model_low.fit(X_train_low, y_train_low)

    # 4. Train Model HIGH: [high_r, high_g, high_b, low_r, low_g, low_b, fill_ml] -> [orange_share, blue_share]
    # Trained on tall vials only (has_high_patch == True, i.e. fill_ml >= 60 mL)
    features_high = ["high_r", "high_g", "high_b", "low_r", "low_g", "low_b", "fill_ml"]
    train_tall = train_df[train_df["has_high_patch"]].copy()
    X_train_high = train_tall[features_high].values
    y_train_high = train_tall[["orange_share", "blue_share"]].values

    print(f"Training Model HIGH (features: high_r/g/b, low_r/g/b, fill_ml; n={len(train_tall)} tall images)...")
    model_high = MultiOutputRegressor(RandomForestRegressor(n_estimators=100, random_state=42))
    model_high.fit(X_train_high, y_train_high)

    # 5. Evaluate Regressors on Twin Hold-Out
    # Cascade rule: use model_high for tall vials, model_low for short vials
    preds_test = []
    used_models = []
    for _, row in test_df.iterrows():
        if row["has_high_patch"]:
            feat = row[features_high].values.reshape(1, -1)
            p = model_high.predict(feat)[0]
            used_models.append("HIGH")
        else:
            feat = row[features_low].values.reshape(1, -1)
            p = model_low.predict(feat)[0]
            used_models.append("LOW")
        preds_test.append(p)

    preds_test = np.array(preds_test)
    y_true_test = test_df[["orange_share", "blue_share"]].values

    # Absolute errors in share units
    err_orange = np.abs(y_true_test[:, 0] - preds_test[:, 0])
    err_blue = np.abs(y_true_test[:, 1] - preds_test[:, 1])
    mae_orange = float(np.mean(err_orange))
    mae_blue = float(np.mean(err_blue))
    mean_mae = (mae_orange + mae_blue) / 2.0
    rmse_orange = float(np.sqrt(mean_squared_error(y_true_test[:, 0], preds_test[:, 0])))
    rmse_blue = float(np.sqrt(mean_squared_error(y_true_test[:, 1], preds_test[:, 1])))

    print("\n" + "-" * 75)
    print("TWIN HOLD-OUT REGRESSION PERFORMANCE (in dye share units [0..0.72])")
    print("-" * 75)
    print(f"Orange Share: MAE = {mae_orange:.4f}  |  RMSE = {rmse_orange:.4f}")
    print(f"Blue Share:   MAE = {mae_blue:.4f}  |  RMSE = {rmse_blue:.4f}")
    print(f"Combined:     Mean MAE = {mean_mae:.4f} (target: well under 0.1)")

    # 6. Compute Share Distance to Intended Recipe Nominal Shares
    # d = sqrt((pred_orange - rec_orange)^2 + (pred_blue - rec_blue)^2)
    share_distances = []
    for i, (_, row) in enumerate(test_df.iterrows()):
        rec_id = int(row["intended_recipe"])
        nom_orange = PLANT_RECIPES[rec_id]["orange"]
        nom_blue = PLANT_RECIPES[rec_id]["blue"]
        po, pb = preds_test[i]
        d = float(np.sqrt((po - nom_orange) ** 2 + (pb - nom_blue) ** 2))
        share_distances.append(d)

    test_df["pred_orange"] = preds_test[:, 0]
    test_df["pred_blue"] = preds_test[:, 1]
    test_df["model_used"] = used_models
    test_df["share_dist"] = share_distances
    test_df["is_contaminated"] = (test_df["category"] == "contaminated")

    # 7. Select Decision Threshold on Twin Hold-Out Only
    clean_dists = test_df[~test_df["is_contaminated"]]["share_dist"].values
    contam_dists = test_df[test_df["is_contaminated"]]["share_dist"].values

    y_binary_true = test_df["is_contaminated"].values.astype(int)  # 0 = clean, 1 = contaminated
    y_scores = test_df["share_dist"].values
    auc = float(roc_auc_score(y_binary_true, y_scores))

    # Grid search for best threshold maximizing Youden's J = TPR - FPR (balanced separation)
    candidate_thresholds = np.linspace(0.01, 0.30, 291)
    best_j = -1.0
    chosen_threshold = 0.0
    best_stats = {}

    for th in candidate_thresholds:
        flags = (y_scores >= th).astype(int)
        tp = np.sum((flags == 1) & (y_binary_true == 1))
        fp = np.sum((flags == 1) & (y_binary_true == 0))
        fn = np.sum((flags == 0) & (y_binary_true == 1))
        tn = np.sum((flags == 0) & (y_binary_true == 0))

        tpr = tp / len(contam_dists) if len(contam_dists) > 0 else 0.0
        fpr = fp / len(clean_dists) if len(clean_dists) > 0 else 0.0
        acc = (tp + tn) / len(y_binary_true)
        j = tpr - fpr

        if j > best_j:
            best_j = j
            chosen_threshold = round(float(th), 4)
            best_stats = {
                "threshold": chosen_threshold,
                "youden_j": round(float(j), 4),
                "accuracy": round(float(acc), 4),
                "tpr": round(float(tpr), 4),
                "fpr": round(float(fpr), 4),
                "tp": int(tp),
                "fp": int(fp),
                "fn": int(fn),
                "tn": int(tn),
            }

    print("\n" + "-" * 75)
    print("TWIN HOLD-OUT CLASSIFICATION & THRESHOLD SELECTION")
    print("-" * 75)
    print(f"ROC AUC (Clean vs Contaminated): {auc:.4f}")
    print(f"Clean vials share distance:        median={np.median(clean_dists):.4f}, mean={np.mean(clean_dists):.4f}, max={np.max(clean_dists):.4f}")
    print(f"Contaminated vials share distance: median={np.median(contam_dists):.4f}, mean={np.mean(contam_dists):.4f}, min={np.min(contam_dists):.4f}")
    print(f"\nChosen Flag Threshold:             {chosen_threshold:.3f}")
    print(f"  Hold-out Accuracy at threshold:  {best_stats['accuracy'] * 100:.1f}%")
    print(f"  True Positive Rate (Caught):     {best_stats['tpr'] * 100:.1f}% ({best_stats['tp']}/{len(contam_dists)})")
    print(f"  False Positive Rate (Alarms):    {best_stats['fpr'] * 100:.1f}% ({best_stats['fp']}/{len(clean_dists)})")

    # Clean Recipe breakdown in hold-out
    print("\nHeld-out Clean Recipe Performance:")
    for rec_id in HELD_OUT_RECIPES:
        rec_clean = test_df[test_df["clean_recipe_id"] == float(rec_id)]
        rec_dists = rec_clean["share_dist"].values
        rec_alarms = np.sum(rec_dists >= chosen_threshold)
        model_tag = "LOW" if rec_id == 5 else "HIGH"
        print(
            f"  Recipe {rec_id:2d} ({model_tag}): n={len(rec_clean)} | "
            f"Mean distance={np.mean(rec_dists):.4f} | Max distance={np.max(rec_dists):.4f} | "
            f"False alarms={rec_alarms}/{len(rec_clean)}"
        )

    # 8. Save Models and Metadata
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_low, MODEL_LOW_PATH)
    joblib.dump(model_high, MODEL_HIGH_PATH)
    print(f"\nSaved models: {MODEL_LOW_PATH.relative_to(REPO_ROOT)}, {MODEL_HIGH_PATH.relative_to(REPO_ROOT)}")

    threshold_metadata = {
        "threshold": chosen_threshold,
        "metric": "Euclidean share distance: sqrt((pred_orange - rec_orange)^2 + (pred_blue - rec_blue)^2)",
        "features_low": features_low,
        "features_high": features_high,
        "model_type": "MultiOutputRegressor(RandomForestRegressor(n_estimators=100, random_state=42))",
        "training_subset": "mixing == 0.0 (unmixed twin renders)",
        "train_samples_count": n_train,
        "hold_out_samples_count": n_test,
        "held_out_clean_recipes": HELD_OUT_RECIPES,
        "hold_out_regression_errors": {
            "orange_mae": round(mae_orange, 4),
            "blue_mae": round(mae_blue, 4),
            "mean_mae": round(mean_mae, 4),
            "orange_rmse": round(rmse_orange, 4),
            "blue_rmse": round(rmse_blue, 4),
        },
        "hold_out_classification": {
            "roc_auc": round(auc, 4),
            "youden_j": best_stats["youden_j"],
            "accuracy": best_stats["accuracy"],
            "tpr": best_stats["tpr"],
            "fpr": best_stats["fpr"],
            "clean_median_dist": round(float(np.median(clean_dists)), 4),
            "clean_max_dist": round(float(np.max(clean_dists)), 4),
            "contam_median_dist": round(float(np.median(contam_dists)), 4),
            "contam_min_dist": round(float(np.min(contam_dists)), 4),
        },
    }

    with open(THRESHOLD_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(threshold_metadata, f, indent=2)
    print(f"Saved threshold metadata: {THRESHOLD_JSON_PATH.relative_to(REPO_ROOT)}")

    # Save hold-out predictions table
    test_df.to_csv(HOLDOUT_CSV_PATH, index=False)
    print(f"Saved hold-out predictions: {HOLDOUT_CSV_PATH.relative_to(REPO_ROOT)}")
    print("=" * 75)


if __name__ == "__main__":
    main()

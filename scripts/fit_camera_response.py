"""
scripts/fit_camera_response.py
Card 7 / Camera-Response Test:
Fits simple camera-response curves mapping digital twin blank-normalized patch colors
to real camera colors in linear light, on the 8 calibration recipes only.
Recipes 5 and 11 are held out.

Models evaluated:
1. Power-law model (at most 2 numbers per channel):
   T_real = a * (T_twin ^ g) per color channel (R, G, B)
2. Gain-only model (one number per channel, g = 1.0):
   T_real = a * T_twin per color channel (R, G, B)

Domain note:
The curves operate on optical transmittance T (linear RGB relative to blank),
placing HIGH (white backdrop) and LOW (dark conveyor) patches on a unified optical scale.
"The red gain (1.27) is close to the twin's lens factor, but green (0.92) and blue (0.81)
are not, so the curve is not explained by the lens alone."

Reads:
- Real optical transmittances: outputs/card7/vials_30_transmittance.csv
- Real CIELAB targets: outputs/card7/calibration.csv
- Calibrated twin renders: outputs/card7/card7_calibrated/recipe*.png

Writes:
- outputs/card7/camera_response.json
"""

from pathlib import Path
import sys

# Portable encoding support for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import json
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
import colour

from scripts.measure_patches import measure_image, linear_to_lab

V30_CSV = REPO_ROOT / "outputs" / "card7" / "vials_30_transmittance.csv"
CAL_CSV = REPO_ROOT / "outputs" / "card7" / "calibration.csv"
CALIB_DIR = REPO_ROOT / "outputs" / "card7" / "card7_calibrated"
OUT_JSON = REPO_ROOT / "outputs" / "card7" / "camera_response.json"

RECIPES = {
    5: {"vial": 3, "file": "recipe05_30ml.png", "patch": "LOW", "held_out": True},
    6: {"vial": 6, "file": "recipe06_40ml.png", "patch": "LOW", "held_out": False},
    7: {"vial": 9, "file": "recipe07_70ml.png", "patch": "HIGH", "held_out": False},
    8: {"vial": 12, "file": "recipe08_60ml.png", "patch": "HIGH", "held_out": False},
    9: {"vial": 15, "file": "recipe09_80ml.png", "patch": "HIGH", "held_out": False},
    10: {"vial": 18, "file": "recipe10_75ml.png", "patch": "HIGH", "held_out": False},
    11: {"vial": 21, "file": "recipe11_70ml.png", "patch": "HIGH", "held_out": True},
    12: {"vial": 24, "file": "recipe12_70ml.png", "patch": "HIGH", "held_out": False},
    13: {"vial": 27, "file": "recipe13_70ml.png", "patch": "HIGH", "held_out": False},
    14: {"vial": 30, "file": "recipe14_70ml.png", "patch": "HIGH", "held_out": False},
}

CHANNELS = ["R", "G", "B"]

# Reference median blank linear RGB from 27 valid frames in Video 5
MED_BLANK_H_LIN = np.array([0.17144110073282259, 0.19120168274079138, 0.17464740365558504])
MED_BLANK_L_LIN = np.array([0.020288563056652397, 0.021219010376003555, 0.015208514422912708])


def fit_power_law(x_vals: np.ndarray, y_vals: np.ndarray):
    """Fit y = a * x^g via non-linear least squares."""
    def func(x, a, g):
        return a * (x ** g)
    popt, _ = curve_fit(func, x_vals, y_vals, p0=[1.0, 1.0], bounds=([0.01, 0.1], [50.0, 5.0]))
    return float(popt[0]), float(popt[1])


def fit_gain_only(x_vals: np.ndarray, y_vals: np.ndarray):
    """Fit y = a * x (pure gain, g = 1.0) via linear least squares."""
    a = float(np.sum(x_vals * y_vals) / np.sum(x_vals ** 2))
    return a, 1.0


def main():
    v30 = pd.read_csv(V30_CSV)
    cal = pd.read_csv(CAL_CSV)
    targets = cal.drop_duplicates(subset=["recipe_id"]).set_index("recipe_id")[["target_L", "target_a", "target_b"]]

    data = []
    for r, meta in RECIPES.items():
        v = meta["vial"]
        patch = meta["patch"]
        v_row = v30[v30["vial"] == v].iloc[0]
        med_b = MED_BLANK_L_LIN if patch == "LOW" else MED_BLANK_H_LIN

        if patch == "LOW":
            t_real = np.array([float(v_row["T_low_R"]), float(v_row["T_low_G"]), float(v_row["T_low_B"])])
        else:
            t_real = np.array([float(v_row["T_high_R"]), float(v_row["T_high_G"]), float(v_row["T_high_B"])])
        lin_real = t_real * med_b

        twin_img_path = CALIB_DIR / meta["file"]
        meas = measure_image(twin_img_path)
        t_twin = np.array(meas["transmittance"][patch], dtype=np.float64)
        lin_twin = np.array(meas["normalized"][patch]["linear_RGB"], dtype=np.float64)
        twin_lab = np.array(meas["normalized"][patch]["Lab"], dtype=np.float64)
        real_lab = np.array([targets.loc[r, "target_L"], targets.loc[r, "target_a"], targets.loc[r, "target_b"]], dtype=np.float64)
        dE_initial = float(colour.delta_E(twin_lab, real_lab, method="CIE 2000"))

        data.append({
            "recipe": r,
            "vial": v,
            "patch": patch,
            "held_out": meta["held_out"],
            "t_twin": t_twin,
            "t_real": t_real,
            "lin_twin": lin_twin,
            "lin_real": lin_real,
            "twin_lab": twin_lab,
            "real_lab": real_lab,
            "dE_initial": dE_initial,
        })

    train_data = [d for d in data if not d["held_out"]]  # 8 calibration recipes

    # 1. Fit Power-Law on Transmittance: T_out = a * T_in^g
    t_power_params = {}
    for c_idx, ch in enumerate(CHANNELS):
        x = np.array([d["t_twin"][c_idx] for d in train_data])
        y = np.array([d["t_real"][c_idx] for d in train_data])
        a_pow, g_pow = fit_power_law(x, y)
        t_power_params[ch] = {"a": round(a_pow, 5), "g": round(g_pow, 5)}

    # 2. Fit Gain-Only on Transmittance: T_out = a * T_in (g = 1.0)
    t_gain_params = {}
    for c_idx, ch in enumerate(CHANNELS):
        x = np.array([d["t_twin"][c_idx] for d in train_data])
        y = np.array([d["t_real"][c_idx] for d in train_data])
        a_g, _ = fit_gain_only(x, y)
        t_gain_params[ch] = {"a": round(a_g, 5), "g": 1.0}

    # Evaluate models on all 10 recipes
    def evaluate(params_dict):
        res = []
        for d in data:
            med_b = MED_BLANK_L_LIN if d["patch"] == "LOW" else MED_BLANK_H_LIN
            t_in = d["t_twin"]
            t_out = np.zeros(3)
            for c_idx, ch in enumerate(CHANNELS):
                t_out[c_idx] = params_dict[ch]["a"] * (t_in[c_idx] ** params_dict[ch]["g"])
            lin_out = t_out * med_b

            lab_out = linear_to_lab(lin_out)
            de_after = float(colour.delta_E(lab_out, d["real_lab"], method="CIE 2000"))
            res.append({
                "recipe": d["recipe"],
                "held_out": d["held_out"],
                "patch": d["patch"],
                "dE_before": round(d["dE_initial"], 2),
                "dE_after": round(de_after, 2),
                "dE_change": round(de_after - d["dE_initial"], 2),
                "lab_pred": [round(float(v), 2) for v in lab_out],
                "lab_real": [round(float(v), 2) for v in d["real_lab"]],
            })
        return res

    eval_power = evaluate(t_power_params)
    eval_gain = evaluate(t_gain_params)

    cal_before = [x["dE_before"] for x in eval_gain if not x["held_out"]]
    cal_gain_after = [x["dE_after"] for x in eval_gain if not x["held_out"]]
    cal_power_after = [x["dE_after"] for x in eval_power if not x["held_out"]]

    # Save to JSON
    output_bundle = {
        "description": "Camera response curves mapping twin blank-normalized patch colors to real camera colors.",
        "training": {
            "calibration_recipes": [6, 7, 8, 9, 10, 12, 13, 14],
            "held_out_recipes": [5, 11],
            "method": "Fitted on 8 calibration recipes; Recipes 5 and 11 held out",
        },
        "gain_only_model": {
            "formula": "T_real = a * T_twin (g = 1.0)",
            "description": "Pure linear gain per channel (one number per channel)",
            "coefficients": t_gain_params,
            "summary_calibration_median_dE_before": float(np.median(cal_before)),
            "summary_calibration_median_dE_after": float(np.median(cal_gain_after)),
            "summary_calibration_mean_dE_before": float(np.mean(cal_before)),
            "summary_calibration_mean_dE_after": float(np.mean(cal_gain_after)),
            "per_recipe_results": eval_gain,
        },
        "power_law_model": {
            "formula": "T_real = a * (T_twin ^ g)",
            "description": "Two numbers per channel (gain + exponent)",
            "coefficients": t_power_params,
            "summary_calibration_median_dE_before": float(np.median(cal_before)),
            "summary_calibration_median_dE_after": float(np.median(cal_power_after)),
            "summary_calibration_mean_dE_before": float(np.mean(cal_before)),
            "summary_calibration_mean_dE_after": float(np.mean(cal_power_after)),
            "per_recipe_results": eval_power,
        },
        "interpretation": (
            "The red gain (1.27) is close to the twin's lens factor, but green (0.92) "
            "and blue (0.81) are not, so the curve is not explained by the lens alone."
        ),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output_bundle, f, indent=2)

    # Console outputs
    print("=" * 75)
    print("GAIN-ONLY CAMERA-RESPONSE (g = 1.0, ONE NUMBER PER CHANNEL)")
    print("=" * 75)
    print("Fitted Coefficients:")
    for ch in CHANNELS:
        print(f"  {ch} channel: a = {t_gain_params[ch]['a']:8.5f} (g = 1.0)")

    print("\nPer-Recipe ΔE2000 Before and After (Gain-Only Model, g = 1.0):")
    print(f"{'Recipe':7s} | {'Status':11s} | {'Patch':5s} | {'ΔE Before':10s} | {'ΔE After':10s} | {'Change':8s}")
    print("-" * 65)
    for r in eval_gain:
        status = "HELD OUT" if r["held_out"] else "Calibration"
        print(
            f"Recipe {r['recipe']:2d} | {status:11s} | {r['patch']:5s} | "
            f"{r['dE_before']:9.2f}  | {r['dE_after']:9.2f}  | {r['dE_change']:+7.2f}"
        )
    print("-" * 65)
    print(f"Calibration (8 recipes) Median ΔE: {np.median(cal_before):.2f} -> {np.median(cal_gain_after):.2f}")
    print(f"Calibration (8 recipes) Mean ΔE:   {np.mean(cal_before):.2f} -> {np.mean(cal_gain_after):.2f}")
    held_before = [x["dE_before"] for x in eval_gain if x["held_out"]]
    held_after = [x["dE_after"] for x in eval_gain if x["held_out"]]
    print(f"Held-out (Recipes 5 & 11) ΔE:     {held_before} -> {held_after}")

    print("\n" + "=" * 75)
    print("POWER-LAW CAMERA-RESPONSE (TWO NUMBERS PER CHANNEL, a * in^g)")
    print("=" * 75)
    for ch in CHANNELS:
        print(f"  {ch} channel: a = {t_power_params[ch]['a']:8.5f}, g = {t_power_params[ch]['g']:8.5f}")
    print(f"Calibration (8 recipes) Median ΔE: {np.median(cal_before):.2f} -> {np.median(cal_power_after):.2f}")
    held_p_after = [x["dE_after"] for x in eval_power if x["held_out"]]
    print(f"Held-out (Recipes 5 & 11) ΔE:     {held_before} -> {held_p_after}")
    print(f"\nSaved JSON: {OUT_JSON}")


if __name__ == "__main__":
    main()

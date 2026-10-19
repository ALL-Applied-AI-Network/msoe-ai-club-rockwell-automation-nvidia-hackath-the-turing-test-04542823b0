"""
scripts/check_measurements.py
Card 4: Sanity-check color measurements, exposure stability, and physical mixing.

Reads:
- annotations/video5_vial_times_corrected.csv
- data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4
- outputs/card3/baseline_results.csv

Writes:
- outputs/card4/measurement_check.csv
- outputs/card4/mixing_check.png
- outputs/card4/first_vial_strips.png
- outputs/card4/backdrop_patch_grid.png

Checks performed:
1. Exposure check:
   - Measures L* of a BACKDROP patch on the white paper backdrop at HIGH patch height (y: 268-288, x: 200-216).
   - Draws BACKDROP and HIGH patches on a grid of all 30 frames to visually verify patch placement.
   - Reports min, max, spread, median L*, and lists any vial with |L - median| > 2.
2. In-between check (HIGH patch, 7 tall transitions 7->8 ... 13->14):
   - Compares L* and optical absorbance A = -log10(linear RGB) per channel (R, G, B)
     between previous 3rd vial, first vial, and next 3rd vial.
   - Flags any first vial that is darker or lighter than both, or whose absorbance falls outside the bounding range.
3. Color-plane picture (outputs/card4/mixing_check.png):
   - Plots a* vs b* for previous clean vial, next clean vial, and first vial with a straight mixing line.
4. Crop strip picture (outputs/card4/first_vial_strips.png):
   - 9 transitions side by side: previous 3rd vial | first vial | next 3rd vial for visual inspection of streaks/layering.
"""

import sys
from pathlib import Path
import cv2
import colour
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMES_CSV = REPO_ROOT / "annotations" / "video5_vial_times_corrected.csv"
VIDEO_MP4 = REPO_ROOT / "data" / "csi-vial-fill-dataset" / "vial_fill" / "videos" / "vial_fill_video_5.mp4"
BASELINE_CSV = REPO_ROOT / "outputs" / "card3" / "baseline_results.csv"

OUTPUT_DIR = REPO_ROOT / "outputs" / "card4"
MEASUREMENT_CSV = OUTPUT_DIR / "measurement_check.csv"
MIXING_PNG = OUTPUT_DIR / "mixing_check.png"
STRIPS_PNG = OUTPUT_DIR / "first_vial_strips.png"
BACKDROP_GRID_PNG = OUTPUT_DIR / "backdrop_patch_grid.png"

# Patch coordinates in 640x480 frame pixels
HIGH_PATCH = {"x_min": 302, "x_max": 318, "y_min": 268, "y_max": 288, "name": "HIGH"}
BACKDROP_PATCH = {"x_min": 200, "x_max": 216, "y_min": 268, "y_max": 288, "name": "BACKDROP"}

# Vial crop bounding box
CROP_X1, CROP_X2 = 250, 370
CROP_Y1, CROP_Y2 = 130, 420

# 9 transitions in Video 5
ALL_9_TRANSITIONS = [
    {"name": "5→6", "prev_r": 5, "next_r": 6, "prev_v": 3, "first_v": 4, "next_v": 6},
    {"name": "6→7", "prev_r": 6, "next_r": 7, "prev_v": 6, "first_v": 7, "next_v": 9},
    {"name": "7→8", "prev_r": 7, "next_r": 8, "prev_v": 9, "first_v": 10, "next_v": 12},
    {"name": "8→9", "prev_r": 8, "next_r": 9, "prev_v": 12, "first_v": 13, "next_v": 15},
    {"name": "9→10", "prev_r": 9, "next_r": 10, "prev_v": 15, "first_v": 16, "next_v": 18},
    {"name": "10→11", "prev_r": 10, "next_r": 11, "prev_v": 18, "first_v": 19, "next_v": 21},
    {"name": "11→12", "prev_r": 11, "next_r": 12, "prev_v": 21, "first_v": 22, "next_v": 24},
    {"name": "12→13", "prev_r": 12, "next_r": 13, "prev_v": 24, "first_v": 25, "next_v": 27},
    {"name": "13→14", "prev_r": 13, "next_r": 14, "prev_v": 27, "first_v": 28, "next_v": 30},
]

# 7 tall transitions with valid HIGH patch
TALL_TRANSITIONS = ALL_9_TRANSITIONS[2:]


def get_patch_lab_raw(frame: np.ndarray, patch_def: dict) -> np.ndarray:
    """Extract median Lab color for a given patch definition."""
    crop_bgr = frame[patch_def["y_min"]:patch_def["y_max"], patch_def["x_min"]:patch_def["x_max"]]
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(crop_rgb, axis=(0, 1)) / 255.0
    xyz = colour.sRGB_to_XYZ(med_srgb)
    lab = colour.XYZ_to_Lab(xyz)
    return lab


def lab_to_absorbance(lab: np.ndarray) -> np.ndarray:
    """Convert Lab to optical absorbance A = -log10(linear RGB) per channel."""
    xyz = colour.Lab_to_XYZ(lab)
    rgb_lin = colour.XYZ_to_sRGB(xyz, apply_cctf_encoding=False)
    rgb_lin = np.clip(rgb_lin, 1e-7, 1.0)
    return -np.log10(rgb_lin)


def main():
    print("=" * 80)
    print("CARD 4 SANITY CHECK: COLOR MEASUREMENTS, EXPOSURE, & PHYSICAL MIXING")
    print("=" * 80)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not TIMES_CSV.exists():
        raise FileNotFoundError(f"Missing times file: {TIMES_CSV}")
    if not VIDEO_MP4.exists():
        raise FileNotFoundError(f"Missing video file: {VIDEO_MP4}")
    if not BASELINE_CSV.exists():
        raise FileNotFoundError(f"Missing baseline file: {BASELINE_CSV}")

    df_times = pd.read_csv(TIMES_CSV)
    base_df = pd.read_csv(BASELINE_CSV).set_index("vial")

    cap = cv2.VideoCapture(str(VIDEO_MP4))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video {VIDEO_MP4}")

    # =========================================================================
    # CHECK 1: EXPOSURE & BACKDROP L* CHECK ACROSS ALL 30 VIALS
    # =========================================================================
    backdrop_records = []
    vial_frames = {}
    vial_crops = {}

    for _, r in df_times.iterrows():
        v = int(r["vial"])
        f = int(r["last_parked_frame"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            raise RuntimeError(f"Could not read frame {f} for vial {v}")

        vial_frames[v] = frame
        vial_crops[v] = frame[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2].copy()

        lab_backdrop = get_patch_lab_raw(frame, BACKDROP_PATCH)
        backdrop_records.append({
            "vial": v,
            "recipe_id": int(r["recipe_id"]),
            "frame": f,
            "backdrop_L": round(float(lab_backdrop[0]), 2),
            "backdrop_a": round(float(lab_backdrop[1]), 2),
            "backdrop_b": round(float(lab_backdrop[2]), 2),
        })

    cap.release()

    df_backdrop = pd.DataFrame(backdrop_records)
    l_vals = df_backdrop["backdrop_L"]
    med_L = float(l_vals.median())
    min_L = float(l_vals.min())
    max_L = float(l_vals.max())
    spread_L = max_L - min_L

    df_backdrop["L_diff_from_median"] = np.round(df_backdrop["backdrop_L"] - med_L, 2)
    df_backdrop["is_outlier"] = np.abs(df_backdrop["L_diff_from_median"]) > 2.0

    print("\n--- 1. BACKDROP EXPOSURE STABILITY (30 Vials) ---")
    print(f"Backdrop Patch Coordinates: x=[{BACKDROP_PATCH['x_min']}, {BACKDROP_PATCH['x_max']}], y=[{BACKDROP_PATCH['y_min']}, {BACKDROP_PATCH['y_max']}]")
    print(f"  Median L*: {med_L:.2f}")
    print(f"  Min L*:    {min_L:.2f}")
    print(f"  Max L*:    {max_L:.2f}")
    print(f"  Spread:    {spread_L:.2f}")

    outliers = df_backdrop[df_backdrop["is_outlier"]]
    print(f"\nVials with |L* - median| > 2.0 ({len(outliers)} vials):")
    if len(outliers) == 0:
        print("  None! Exposure is exceptionally stable across all 30 vials.")
    else:
        for _, r in outliers.iterrows():
            print(f"  Vial {int(r['vial'])} (Recipe {int(r['recipe_id'])}): L* = {r['backdrop_L']:.2f} (diff = {r['L_diff_from_median']:+.2f})")

    backdrop_csv = OUTPUT_DIR / "backdrop_measurements.csv"
    df_backdrop.to_csv(backdrop_csv, index=False)
    print(f"Saved 30-vial backdrop measurements to {backdrop_csv}")

    # =========================================================================
    # DRAW BACKDROP PATCH VERIFICATION GRID (5x6)
    # =========================================================================
    fig_grid, axes_grid = plt.subplots(5, 6, figsize=(18, 15))
    fig_grid.suptitle(
        "Backdrop Patch Placement Verification (All 30 Parked Frames)\n"
        "Cyan: BACKDROP Patch (x: 200–216, y: 268–288) | Green: HIGH Patch (x: 302–318, y: 268–288)",
        fontsize=14, fontweight="bold", y=0.98
    )

    for idx, r in df_backdrop.iterrows():
        v = int(r["vial"])
        ax = axes_grid.flatten()[idx]
        frame_rgb = cv2.cvtColor(vial_frames[v], cv2.COLOR_BGR2RGB)

        # Zoom into region of interest (x: 170–350, y: 240–320)
        zoom = frame_rgb[240:320, 170:350].copy()
        ax.imshow(zoom)

        # Draw patches relative to zoom crop (x_offset=170, y_offset=240)
        bx1, by1 = BACKDROP_PATCH["x_min"] - 170, BACKDROP_PATCH["y_min"] - 240
        bw, bh = BACKDROP_PATCH["x_max"] - BACKDROP_PATCH["x_min"], BACKDROP_PATCH["y_max"] - BACKDROP_PATCH["y_min"]
        rect_b = patches.Rectangle((bx1, by1), bw, bh, linewidth=1.5, edgecolor="cyan", facecolor="none")
        ax.add_patch(rect_b)

        hx1, hy1 = HIGH_PATCH["x_min"] - 170, HIGH_PATCH["y_min"] - 240
        hw, hh = HIGH_PATCH["x_max"] - HIGH_PATCH["x_min"], HIGH_PATCH["y_max"] - HIGH_PATCH["y_min"]
        rect_h = patches.Rectangle((hx1, hy1), hw, hh, linewidth=1.5, edgecolor="#00ff00", facecolor="none")
        ax.add_patch(rect_h)

        diff_str = f"L*={r['backdrop_L']:.1f} ({r['L_diff_from_median']:+.1f})"
        ax.set_title(f"Vial {v} (R{int(r['recipe_id'])})\n{diff_str}", fontsize=9, fontweight="bold")
        ax.axis("off")

    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    plt.savefig(BACKDROP_GRID_PNG, dpi=180, bbox_inches="tight")
    plt.close()
    print(f"\nSaved backdrop patch verification grid to {BACKDROP_GRID_PNG}")

    # =========================================================================
    # CHECK 2: IN-BETWEEN CHECK (L* and Optical Absorbance A) FOR 7 TALL TRANSITIONS
    # =========================================================================
    print("\n--- 2. IN-BETWEEN CHECK (HIGH Patch: 7 Transitions 7→8 through 13→14) ---")
    print("Does the first vial lie between the previous clean vial and next clean vial in L* and optical absorbance?")

    in_between_rows = []

    for t in TALL_TRANSITIONS:
        prev_v = t["prev_v"]
        first_v = t["first_v"]
        next_v = t["next_v"]

        # Measured Lab colors
        lab_prev = np.array([float(base_df.loc[prev_v, "L_high"]), float(base_df.loc[prev_v, "a_high"]), float(base_df.loc[prev_v, "b_high"])])
        lab_first = np.array([float(base_df.loc[first_v, "L_high"]), float(base_df.loc[first_v, "a_high"]), float(base_df.loc[first_v, "b_high"])])
        lab_next = np.array([float(base_df.loc[next_v, "L_high"]), float(base_df.loc[next_v, "a_high"]), float(base_df.loc[next_v, "b_high"])])

        L_p, L_f, L_n = lab_prev[0], lab_first[0], lab_next[0]
        L_min, L_max = min(L_p, L_n), max(L_p, L_n)

        # L flag: True if first vial is outside [L_min, L_max]
        flag_L_darker = L_f < L_min
        flag_L_lighter = L_f > L_max
        if flag_L_darker:
            l_status = "DARKER than both"
        elif flag_L_lighter:
            l_status = "LIGHTER than both"
        else:
            l_status = "In-between (OK)"

        # Absorbance check per channel
        A_p = lab_to_absorbance(lab_prev)
        A_f = lab_to_absorbance(lab_first)
        A_n = lab_to_absorbance(lab_next)

        flags_A = []
        channel_names = ["R", "G", "B"]
        for c in range(3):
            ch = channel_names[c]
            a_min, a_max = min(A_p[c], A_n[c]), max(A_p[c], A_n[c])
            if A_f[c] < a_min:
                flags_A.append(f"{ch}:low")
            elif A_f[c] > a_max:
                flags_A.append(f"{ch}:high")

        a_status = ", ".join(flags_A) if flags_A else "In-between (OK)"

        # Color-plane geometry: distance from first vial (a*, b*) to segment (a_prev*, b_prev*) -> (a_next*, b_next*)
        p1 = lab_prev[1:3]
        p2 = lab_next[1:3]
        pf = lab_first[1:3]
        # Line segment projection
        seg = p2 - p1
        seg_len_sq = np.dot(seg, seg)
        if seg_len_sq > 1e-6:
            u = np.clip(np.dot(pf - p1, seg) / seg_len_sq, 0.0, 1.0)
            proj = p1 + u * seg
            dist_to_line = float(np.linalg.norm(pf - proj))
        else:
            dist_to_line = float(np.linalg.norm(pf - p1))

        in_between_rows.append({
            "transition": t["name"],
            "prev_recipe": t["prev_r"],
            "next_recipe": t["next_r"],
            "first_vial": first_v,
            "prev_ref_vial": prev_v,
            "next_ref_vial": next_v,
            "L_prev": round(L_p, 2),
            "L_first": round(L_f, 2),
            "L_next": round(L_n, 2),
            "L_status": l_status,
            "A_R_prev": round(A_p[0], 3),
            "A_R_first": round(A_f[0], 3),
            "A_R_next": round(A_n[0], 3),
            "A_G_prev": round(A_p[1], 3),
            "A_G_first": round(A_f[1], 3),
            "A_G_next": round(A_n[1], 3),
            "A_B_prev": round(A_p[2], 3),
            "A_B_first": round(A_f[2], 3),
            "A_B_next": round(A_n[2], 3),
            "A_status": a_status,
            "a_star_first": round(lab_first[1], 2),
            "b_star_first": round(lab_first[2], 2),
            "dist_to_ab_line": round(dist_to_line, 2),
            "lab_prev": [round(x, 2) for x in lab_prev],
            "lab_first": [round(x, 2) for x in lab_first],
            "lab_next": [round(x, 2) for x in lab_next],
        })

    df_in_between = pd.DataFrame(in_between_rows)

    display_cols = [
        "transition", "first_vial", "L_prev", "L_first", "L_next", "L_status", "A_status", "dist_to_ab_line"
    ]
    print(df_in_between[display_cols].to_string(index=False))

    # Save measurement check table
    # Merge backdrop info with transition info
    out_table = []
    for r in in_between_rows:
        vf = r["first_vial"]
        bd_row = df_backdrop[df_backdrop["vial"] == vf].iloc[0]
        out_table.append({
            "transition": r["transition"],
            "first_vial": vf,
            "prev_ref_vial": r["prev_ref_vial"],
            "next_ref_vial": r["next_ref_vial"],
            "first_vial_backdrop_L": bd_row["backdrop_L"],
            "first_vial_backdrop_L_diff": bd_row["L_diff_from_median"],
            "L_prev": r["L_prev"],
            "L_first": r["L_first"],
            "L_next": r["L_next"],
            "L_status": r["L_status"],
            "A_R_prev": r["A_R_prev"],
            "A_R_first": r["A_R_first"],
            "A_R_next": r["A_R_next"],
            "A_G_prev": r["A_G_prev"],
            "A_G_first": r["A_G_first"],
            "A_G_next": r["A_G_next"],
            "A_B_prev": r["A_B_prev"],
            "A_B_first": r["A_B_first"],
            "A_B_next": r["A_B_next"],
            "A_status": r["A_status"],
            "dist_to_ab_line": r["dist_to_ab_line"],
        })
    df_out = pd.DataFrame(out_table)
    df_out.to_csv(MEASUREMENT_CSV, index=False)
    print(f"\nSaved measurement check metrics to {MEASUREMENT_CSV}")

    # =========================================================================
    # CHECK 3: COLOR-PLANE PICTURE (mixing_check.png)
    # =========================================================================
    fig_mix, axes_mix = plt.subplots(4, 2, figsize=(13, 16))
    fig_mix.suptitle(
        "Color-Plane Mixing Check (CIELAB a* vs b*)\n"
        "Testing whether 1st Vial falls along the straight mixing line between Clean Previous & Clean Next vials",
        fontsize=14, fontweight="bold", y=0.98
    )

    axes_flat = axes_mix.flatten()

    for idx, r in df_in_between.iterrows():
        ax = axes_flat[idx]
        t_name = r["transition"]
        first_v = r["first_vial"]

        lp = r["lab_prev"]
        lf = r["lab_first"]
        ln = r["lab_next"]

        # Plot straight line
        ax.plot([lp[1], ln[1]], [lp[2], ln[2]], color="#888888", linestyle="--", linewidth=1.8, label="Linear Mixing Line", zorder=1)

        # Plot Previous Clean (Vial N)
        ax.scatter(lp[1], lp[2], color="#2b5c8f", s=110, marker="o", edgecolor="black", label=f"Prev Clean (V{r['prev_ref_vial']})", zorder=3)
        # Plot Next Clean (Vial N)
        ax.scatter(ln[1], ln[2], color="#2e7d32", s=110, marker="s", edgecolor="black", label=f"Next Clean (V{r['next_ref_vial']})", zorder=3)
        # Plot First Vial (Vial N)
        ax.scatter(lf[1], lf[2], color="#d32f2f", s=160, marker="*", edgecolor="black", label=f"First Vial (V{first_v})", zorder=4)

        # Annotation text
        dist = r["dist_to_ab_line"]
        ax.set_title(f"Transition {t_name} (1st Vial {first_v}) | Line Dist: {dist:.1f}", fontsize=11, fontweight="bold")
        ax.set_xlabel("a* (Green ← → Red)", fontsize=9)
        ax.set_ylabel("b* (Blue ← → Yellow)", fontsize=9)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="best", fontsize=8)

    # Hide 8th empty panel
    axes_flat[7].axis("off")

    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    plt.savefig(MIXING_PNG, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved color-plane mixing picture to {MIXING_PNG}")

    # =========================================================================
    # CHECK 4: CROP STRIP PICTURE (first_vial_strips.png) FOR ALL 9 TRANSITIONS
    # =========================================================================
    fig_strips, axes_strips = plt.subplots(9, 3, figsize=(11, 24))
    fig_strips.suptitle(
        "Card 4 Step 2: First-Vial Visual Strips Across All 9 Transitions\n"
        "Left: Prev 3rd Vial (Clean)  |  Center: 1st Vial  |  Right: Next 3rd Vial (Clean)",
        fontsize=14, fontweight="bold", y=0.99
    )

    for idx, t in enumerate(ALL_9_TRANSITIONS):
        t_name = t["name"]
        prev_v = t["prev_v"]
        first_v = t["first_v"]
        next_v = t["next_v"]

        crop_p = cv2.cvtColor(vial_crops[prev_v], cv2.COLOR_BGR2RGB)
        crop_f = cv2.cvtColor(vial_crops[first_v], cv2.COLOR_BGR2RGB)
        crop_n = cv2.cvtColor(vial_crops[next_v], cv2.COLOR_BGR2RGB)

        ax_p = axes_strips[idx, 0]
        ax_f = axes_strips[idx, 1]
        ax_n = axes_strips[idx, 2]

        ax_p.imshow(crop_p)
        ax_f.imshow(crop_f)
        ax_n.imshow(crop_n)

        for ax in [ax_p, ax_f, ax_n]:
            ax.set_xticks([])
            ax.set_yticks([])

        ax_p.set_ylabel(f"Transition {t_name}", fontsize=11, fontweight="bold", labelpad=10)
        ax_p.set_title(f"Vial {prev_v} (R{t['prev_r']} clean)", fontsize=9.5)
        ax_f.set_title(f"Vial {first_v} (1st vial)", fontsize=9.5, fontweight="bold", color="#b71c1c")
        ax_n.set_title(f"Vial {next_v} (R{t['next_r']} clean)", fontsize=9.5)

    plt.tight_layout(rect=[0, 0.01, 1, 0.98])
    plt.savefig(STRIPS_PNG, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved first-vial crop strips to {STRIPS_PNG}")


if __name__ == "__main__":
    main()

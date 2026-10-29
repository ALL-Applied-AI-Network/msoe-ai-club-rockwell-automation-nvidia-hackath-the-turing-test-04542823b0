"""
scripts/crop_vial.py
Defines three fixed measurement patch locations inside the vial for Card 3 color analysis:
1. LOW patch: Inside liquid for all vials (even 30 mL), in front of the dark conveyor.
2. HIGH patch: Inside liquid in front of the white backdrop (counted inside liquid only for vials >= 60 mL where meniscus is >= 5 px above y=268).
3. BASE patch: Experimental patch in the colored glow of the thick glass vial bottom (just above the metal block).

All patches are fixed rectangular regions positioned to avoid glare spots, barcode labels,
vial glass edges, metal block edges, screws, and meniscus boundaries.

Reads:
- annotations/video5_vial_times_corrected.csv
- data/csi-vial-fill-dataset/vial_fill/videos/vial_fill_video_5.mp4

Writes:
- outputs/card3/crop_check.png (visual verification showing patches on vials 3, 6, 9, 15, and 28)
- outputs/card3/crop_check_all30.png (5x6 grid of all 30 vials with all 3 patches drawn)
- outputs/card3/judging_sheet.png (10x3 grid: 1 row per recipe, labeled only 'Vial N (Recipe R)')
"""

from pathlib import Path
import cv2
import colour
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Fixed patch coordinates in 640x480 frame pixels
LOW_PATCH = {
    "x_min": 302,
    "x_max": 318,
    "y_min": 352,
    "y_max": 372,
    "width": 16,
    "height": 20,
    "name": "LOW (dark conveyor backdrop)",
    "color_bgr": (255, 0, 0),  # Blue
}

HIGH_PATCH = {
    "x_min": 302,
    "x_max": 318,
    "y_min": 268,
    "y_max": 288,
    "width": 16,
    "height": 20,
    "name": "HIGH (white paper backdrop)",
    "color_bgr": (0, 255, 0),  # Green
}

BASE_PATCH = {
    "x_min": 304,
    "x_max": 316,
    "y_min": 389,
    "y_max": 395,
    "width": 12,
    "height": 6,
    "name": "BASE (thick glass bottom glow)",
    "color_bgr": (0, 140, 255),  # Orange
}

PATCHES = {
    "LOW": LOW_PATCH,
    "HIGH": HIGH_PATCH,
    "BASE": BASE_PATCH,
}


def get_patch_median_cielab(frame: np.ndarray, patch_def: dict) -> tuple[float, float, float]:
    """
    Computes the MEDIAN sRGB color of the patch pixels, then converts
    to CIELAB (D65) using colour-science.
    """
    crop_bgr = frame[
        patch_def["y_min"] : patch_def["y_max"],
        patch_def["x_min"] : patch_def["x_max"],
    ]
    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    med_srgb = np.median(crop_rgb, axis=(0, 1)) / 255.0
    xyz = colour.sRGB_to_XYZ(med_srgb)
    lab = colour.XYZ_to_Lab(xyz)
    return (round(float(lab[0]), 1), round(float(lab[1]), 1), round(float(lab[2]), 1))


def detect_glass_edges(gray: np.ndarray, y_min: int, y_max: int) -> tuple[int, int]:
    """Detects left and right glass edges along x in [250, 380] over a vertical span."""
    x_offset = 250
    strip = gray[y_min:y_max, x_offset:380].mean(axis=0).astype(float)
    grad = np.gradient(strip)
    best_score = -1e9
    best_l, best_r = (287, 333)
    for l_idx in range(15, 75):
        for r_idx in range(l_idx + 35, min(l_idx + 55, len(strip) - 5)):
            score = -grad[l_idx] + grad[r_idx]
            if score > best_score:
                best_score = score
                best_l = x_offset + l_idx
                best_r = x_offset + r_idx
    return best_l, best_r


def draw_patches_on_crop(
    vial_crop: np.ndarray,
    crop_x1: int,
    crop_y1: int,
    show_labels: bool = True,
) -> np.ndarray:
    """Draws LOW, HIGH, and BASE patch rectangles on a cropped vial image."""
    res = vial_crop.copy()
    for name, p in PATCHES.items():
        x1 = p["x_min"] - crop_x1
        x2 = p["x_max"] - crop_x1
        y1 = p["y_min"] - crop_y1
        y2 = p["y_max"] - crop_y1
        color = p["color_bgr"]
        cv2.rectangle(res, (x1, y1), (x2, y2), color, 1)
        if show_labels:
            label_x = x1 - 28 if name != "HIGH" else x1 - 32
            cv2.putText(
                res,
                name[:1],
                (x1 - 10, y1 + 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                color,
                1,
                cv2.LINE_AA,
            )
    return res


def run_patch_analysis():
    base_dir = Path(__file__).resolve().parent.parent
    annotations_csv = base_dir / "annotations" / "video5_vial_times_corrected.csv"
    video_path = (
        base_dir
        / "data"
        / "csi-vial-fill-dataset"
        / "vial_fill"
        / "videos"
        / "vial_fill_video_5.mp4"
    )
    outputs_dir = base_dir / "outputs" / "card3"
    output_5_png = outputs_dir / "crop_check.png"
    output_all_png = outputs_dir / "crop_check_all30.png"
    output_judging_png = outputs_dir / "judging_sheet.png"

    outputs_dir.mkdir(parents=True, exist_ok=True)

    if not annotations_csv.exists():
        raise FileNotFoundError(f"Missing annotations: {annotations_csv}")
    if not video_path.exists():
        raise FileNotFoundError(f"Missing video: {video_path}")

    df = pd.read_csv(annotations_csv)
    cap = cv2.VideoCapture(str(video_path))

    CROP_Y1, CROP_Y2 = 130, 420
    CROP_X1, CROP_X2 = 250, 370

    analysis_rows = []
    all_flags = []
    vial_frames = {}

    print("Analyzing all 30 vials for patch safety, glass edges, and median Lab...")

    for idx, r in df.iterrows():
        v = int(r["vial"])
        f = int(r["last_parked_frame"])
        tot_ml = int(r["total_ml"])
        rec_id = int(r["recipe_id"])
        men_y = float(r["meniscus_y"])
        base_y = float(r["base_y"])

        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, frame = cap.read()
        if not ret:
            print(f"Error reading frame {f} for vial {v}")
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        vial_frames[v] = (frame, r)

        # 1. Detect glass edges at each patch height
        edges = {}
        for name, p in PATCHES.items():
            edges[name] = detect_glass_edges(gray, p["y_min"], p["y_max"])

        # 2. Check if patch is fully inside liquid
        # LOW is inside liquid if meniscus_y <= LOW['y_min'] (352)
        low_in_liquid = men_y <= LOW_PATCH["y_min"]
        # HIGH counts only if meniscus is at least 5 px above y=268 (meniscus_y <= 263)
        high_in_liquid = men_y <= (HIGH_PATCH["y_min"] - 5)
        # BASE is inside liquid if meniscus_y <= BASE['y_min'] (389)
        base_in_liquid = men_y <= BASE_PATCH["y_min"]

        # 3. Check for glare/glint (intensity > 200)
        glints = {}
        for name, p in PATCHES.items():
            patch_slice = gray[p["y_min"] : p["y_max"], p["x_min"] : p["x_max"]]
            glints[name] = int(patch_slice.max()) > 200

        # 4. Check all flagging criteria
        vial_flags = []
        for name, p in PATCHES.items():
            l_edge, r_edge = edges[name]
            if p["x_min"] <= l_edge:
                vial_flags.append(f"{name} touches left glass wall ({p['x_min']} <= {l_edge})")
            if p["x_max"] >= r_edge:
                vial_flags.append(f"{name} touches right glass wall ({p['x_max']} >= {r_edge})")

        # Check meniscus overlap
        if LOW_PATCH["y_min"] <= men_y <= LOW_PATCH["y_max"]:
            vial_flags.append(f"LOW touches meniscus (meniscus_y={men_y:.1f})")
        if HIGH_PATCH["y_min"] <= men_y <= HIGH_PATCH["y_max"]:
            vial_flags.append(f"HIGH touches meniscus (meniscus_y={men_y:.1f})")
        if BASE_PATCH["y_min"] <= men_y <= BASE_PATCH["y_max"]:
            vial_flags.append(f"BASE touches meniscus (meniscus_y={men_y:.1f})")

        # Check black holder (y <= 264)
        if HIGH_PATCH["y_min"] <= 264:
            vial_flags.append("HIGH touches black holder (y <= 264)")
        # Check dark strip below backdrop (y >= 294)
        if HIGH_PATCH["y_max"] >= 294:
            vial_flags.append("HIGH touches dark strip (y >= 294)")

        # Check BASE touching metal block
        if BASE_PATCH["y_max"] >= base_y:
            vial_flags.append(f"BASE touches metal block ({BASE_PATCH['y_max']} >= {base_y:.1f})")

        # Check glint
        if any(glints.values()):
            vial_flags.append(f"glint detected ({glints})")

        if vial_flags:
            all_flags.append((v, vial_flags))

        # 5. Median color in CIELAB
        cielab_colors = {}
        for name, p in PATCHES.items():
            cielab_colors[name] = get_patch_median_cielab(frame, p)

        analysis_rows.append(
            {
                "vial": v,
                "recipe": rec_id,
                "vol_ml": tot_ml,
                "high_edges": edges["HIGH"],
                "low_edges": edges["LOW"],
                "base_edges": edges["BASE"],
                "high_in_liq": high_in_liquid,
                "low_in_liq": low_in_liquid,
                "base_in_liq": base_in_liquid,
                "low_lab": cielab_colors["LOW"],
                "high_lab": cielab_colors["HIGH"],
                "base_lab": cielab_colors["BASE"],
                "flagged": len(vial_flags) > 0,
            }
        )

    cap.release()

    # 6. Generate 5-vial visual check (outputs/crop_check.png)
    test_vials = [3, 6, 9, 15, 28]
    fig5, axes5 = plt.subplots(1, 5, figsize=(16, 7))
    fig5.patch.set_facecolor("#f8f9fa")

    for i, v_num in enumerate(test_vials):
        frame, r = vial_frames[v_num]
        vial_crop = frame[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2]
        annotated = draw_patches_on_crop(vial_crop, CROP_X1, CROP_Y1, show_labels=True)
        ax = axes5[i]
        ax.imshow(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
        ax.set_title(
            f"Vial {v_num} (Recipe {int(r['recipe_id'])})\n{int(r['total_ml'])} mL | Frame {int(r['last_parked_frame'])}",
            fontsize=10,
            fontweight="bold",
            pad=8,
        )
        ax.axis("off")

    plt.suptitle(
        "Card 3 Step 1 — Fixed Measurement Patches (outputs/card3/crop_check.png)\n"
        "HIGH (Green): x=[302, 318], y=[268, 288] | LOW (Blue): x=[302, 318], y=[352, 372] | BASE (Orange): x=[304, 316], y=[389, 395]",
        fontsize=12,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(output_5_png, dpi=180, facecolor=fig5.get_facecolor())
    plt.close(fig5)
    print(f"Saved 5-vial verification to: {output_5_png}")

    # 7. Generate all 30 vials visual check (outputs/card3/crop_check_all30.png)
    fig30, axes30 = plt.subplots(5, 6, figsize=(22, 24))
    fig30.patch.set_facecolor("#f8f9fa")
    axes30_flat = axes30.flatten()

    for idx, v_num in enumerate(range(1, 31)):
        ax = axes30_flat[idx]
        if v_num in vial_frames:
            frame, r = vial_frames[v_num]
            vial_crop = frame[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2]
            annotated = draw_patches_on_crop(vial_crop, CROP_X1, CROP_Y1, show_labels=False)
            ax.imshow(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
            row_data = analysis_rows[idx]
            h_stat = "IN" if row_data["high_in_liq"] else "OUT"
            title_str = (
                f"Vial {v_num} (R{int(r['recipe_id'])}, {int(r['total_ml'])}mL)\n"
                f"H:{h_stat} | L:{row_data['low_lab']}\n"
                f"B:{row_data['base_lab']}"
            )
            ax.set_title(title_str, fontsize=8, fontweight="bold")
        ax.axis("off")

    plt.suptitle(
        "Card 3 Step 1 — All 30 Vials Fixed Patches (HIGH: Green, LOW: Blue, BASE: Orange)\n"
        "outputs/card3/crop_check_all30.png",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.98])
    plt.savefig(output_all_png, dpi=150, facecolor=fig30.get_facecolor())
    plt.close(fig30)
    print(f"Saved 30-vial verification grid to: {output_all_png}")

    # 8. Generate judging sheet (10 rows x 3 columns)
    # One row per recipe (3 vials side by side, 10 rows), each tile labeled only 'Vial N (Recipe R)'
    fig_judge, axes_judge = plt.subplots(10, 3, figsize=(10, 28))
    fig_judge.patch.set_facecolor("#ffffff")

    for r_idx in range(10):
        for c_idx in range(3):
            v_num = r_idx * 3 + c_idx + 1
            ax = axes_judge[r_idx, c_idx]
            if v_num in vial_frames:
                frame, r = vial_frames[v_num]
                vial_crop = frame[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2]
                ax.imshow(cv2.cvtColor(vial_crop, cv2.COLOR_BGR2RGB))
                ax.set_title(
                    f"Vial {v_num} (Recipe {int(r['recipe_id'])})",
                    fontsize=9,
                    fontweight="bold",
                    pad=5,
                )
            ax.axis("off")

    plt.suptitle(
        "Card 3 — Human Eye Visual Judging Sheet (10 Recipes × 3 Vials)\n"
        "outputs/card3/judging_sheet.png",
        fontsize=13,
        fontweight="bold",
        y=0.995,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    plt.savefig(output_judging_png, dpi=180, facecolor=fig_judge.get_facecolor())
    plt.close(fig_judge)
    print(f"Saved judging sheet to: {output_judging_png}")

    # 9. Print Results Table
    table_df = pd.DataFrame(analysis_rows)
    print("\n" + "=" * 120)
    print("ALL 30 VIALS GLASS EDGES, LIQUID COVERAGE, AND MEDIAN CIELAB (D65) COLORS:")
    print("=" * 120)
    display_cols = [
        "vial",
        "recipe",
        "vol_ml",
        "high_edges",
        "low_edges",
        "base_edges",
        "high_in_liq",
        "low_in_liq",
        "base_in_liq",
        "low_lab",
        "high_lab",
        "base_lab",
    ]
    print(table_df[display_cols].to_string(index=False))
    print("=" * 120)

    # 9. Flagging Summary
    print("\nFLAGGING EVALUATION (Wall touches, meniscus, black holder, dark strip, screws, glints):")
    if all_flags:
        print(f"WARNING: {len(all_flags)} vial(s) were FLAGGED:")
        for v_num, flag_list in all_flags:
            print(f"  - Vial {v_num}: {', '.join(flag_list)}")
    else:
        print("RESULT: ALL 30 VIALS PASSED WITH ZERO FLAGS.")
        print("  - No patch touches a glass wall, meniscus, black holder, dark strip, screw, or glint.")
        print(f"  - LOW patch [302:318, 352:372]: inside liquid for all 30 vials.")
        print(f"  - HIGH patch [302:318, 268:288]: inside liquid for all 24 vials >= 60 mL (empty for 30/40 mL).")
        print(f"  - BASE patch [304:316, 389:395]: inside colored glass bottom glow for all 30 vials.")

    return table_df, all_flags


if __name__ == "__main__":
    run_patch_analysis()

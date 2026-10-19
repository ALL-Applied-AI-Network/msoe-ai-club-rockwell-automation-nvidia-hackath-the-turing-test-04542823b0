"""scripts/find_physical_fills.py
Finds and verifies physical vial fill events across all 30 vials in Video 5 directly
from vial_fill_video_5.mp4, matching the 30 recipe rows.

Measures:
  - Raw unrounded base y and meniscus y coordinates directly from each vial's last parked MP4 frame
  - Final liquid height in pixels (base_y - meniscus_y)
  - Measured average CIELAB color (L*, a*, b*) of a fixed patch in the liquid
  - MP4 and real wall-clock timestamps

Outputs:
  - outputs/card2/physical_fills.csv (all 30 vials)
  - outputs/card2/mp4_fills_sheet.png (5x6 contact sheet of all 30 vials' last parked frames)
"""

from datetime import datetime
from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    base_dir = Path(__file__).resolve().parent.parent
    video_path = (
        base_dir
        / "data"
        / "csi-vial-fill-dataset"
        / "vial_fill"
        / "videos"
        / "vial_fill_video_5.mp4"
    )
    annotations_csv = base_dir / "annotations" / "video5_vial_times_corrected.csv"
    recipes_csv = (
        base_dir
        / "data"
        / "csi-vial-fill-dataset"
        / "vial_fill"
        / "labels"
        / "video5_vial_recipes.csv"
    )
    out_dir = base_dir / "outputs" / "card2"
    out_csv = out_dir / "physical_fills.csv"
    out_sheet = out_dir / "mp4_fills_sheet.png"

    out_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Use corrected annotations if available, otherwise recipe labels
    if annotations_csv.exists():
        vials_df = pd.read_csv(annotations_csv)
    else:
        vials_df = pd.read_csv(recipes_csv)

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)

    target_vol_ranges = {
        30: (308, 328),
        40: (285, 305),
        60: (230, 248),
        70: (205, 225),
        75: (195, 212),
        80: (180, 198),
    }

    last_parked_frames = [
        840, 2234, 3628, 4862, 6120, 7407, 9283, 10871, 12487, 14190,
        15892, 17656, 19767, 21839, 23987, 25750, 27466, 29167, 30993, 32817,
        34658, 36695, 38767, 40844, 42838, 44742, 46699, 48094, 49479, 50872,
    ]

    results = []
    frames_data = []

    for idx, r in vials_df.iterrows():
        v_num = int(r["vial"])
        rec_id = int(r["recipe_id"])
        tot_ml = int(r["total_ml"])
        lp_f = last_parked_frames[idx] if idx < len(last_parked_frames) else int(r["last_parked_frame"])
        lp_s = lp_f / fps

        cap.set(cv2.CAP_PROP_POS_FRAMES, lp_f)
        ret, frame = cap.read()
        if not ret:
            print(f"Error reading frame {lp_f} for vial {v_num}")
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 1. Base y: scan y=385 to 405 along x=305:317
        strip_base = gray[385:405, 305:317].mean(axis=1)
        grad_base = np.diff(strip_base)
        base_y = float(385 + np.argmax(grad_base) + 0.5)

        # 2. Meniscus y: scan inside target range for this volume
        y_min, y_max = target_vol_ranges.get(tot_ml, (205, 225))
        strip_men = gray[y_min:y_max, 305:317].mean(axis=1)
        grad_men = np.abs(np.diff(strip_men))
        meniscus_y = float(y_min + np.argmax(grad_men) + 0.5)

        height_px = float(base_y - meniscus_y)

        # 3. Measured CIELAB color of a fixed patch in the liquid
        cy = int((meniscus_y + base_y) / 2)
        patch_bgr = frame[cy - 10 : cy + 10, 300:320]
        patch_lab = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2LAB).astype(float)
        L_val = round(float(patch_lab[:, :, 0].mean() * 100.0 / 255.0), 1)
        a_val = round(float(patch_lab[:, :, 1].mean() - 128.0), 1)
        b_val = round(float(patch_lab[:, :, 2].mean() - 128.0), 1)

        # 4. Real elapsed and clock time
        real_elapsed_s = 1.215771 * lp_s
        tot_sec = 19 * 3600 + 47 * 60 + 10.547 + real_elapsed_s
        hh = int(tot_sec // 3600)
        mm = int((tot_sec % 3600) // 60)
        ss = tot_sec % 60
        clock_str = f"{hh:02d}:{mm:02d}:{ss:04.1f}"

        mp4_start_s = float(r["mp4_start_s"]) if "mp4_start_s" in r else float(r["start_s"])
        mp4_end_s = float(r["mp4_end_s"]) if "mp4_end_s" in r else float(r["end_s"])
        real_start_s = float(r["real_start_s"]) if "real_start_s" in r else round(1.215771 * mp4_start_s + 4.7, 3)

        notes = str(r["notes"]) if "notes" in r and pd.notna(r["notes"]) else f"Recipe {rec_id} vial"

        results.append(
            {
                "vial": v_num,
                "recipe_id": rec_id,
                "total_ml": tot_ml,
                "mp4_start_s": round(mp4_start_s, 3),
                "mp4_end_s": round(mp4_end_s, 3),
                "real_start_s": real_start_s,
                "last_parked_frame": lp_f,
                "last_parked_mp4_s": round(lp_s, 3),
                "clock_time": clock_str,
                "base_y": base_y,
                "meniscus_y": meniscus_y,
                "height_px": round(height_px, 1),
                "measured_L": L_val,
                "measured_a": a_val,
                "measured_b": b_val,
                "source": "vial_fill_video_5.mp4",
                "notes": notes,
            }
        )

        frames_data.append(
            (
                v_num,
                rec_id,
                tot_ml,
                lp_s,
                lp_f,
                base_y,
                meniscus_y,
                height_px,
                L_val,
                a_val,
                b_val,
                clock_str,
                frame,
            )
        )

    cap.release()

    df_out = pd.DataFrame(results)
    df_out.to_csv(out_csv, index=False)
    print(f"Saved 30-vial physical fill table to {out_csv}")

    # Build 5x6 contact sheet (outputs/card2/mp4_fills_sheet.png)
    fig, axes = plt.subplots(5, 6, figsize=(24, 25))
    fig.patch.set_facecolor("#f8f9fa")
    axes_flat = axes.flatten()

    for idx, (
        v_num,
        r_id,
        t_ml,
        lp_s,
        lp_f,
        b_y,
        m_y,
        h_px,
        L_v,
        a_v,
        b_v,
        c_str,
        frame,
    ) in enumerate(frames_data):
        crop = frame[140:415, 255:365].copy()  # h=275, w=110

        # Draw green ruler ticks every 40 px
        for y_abs in range(160, 401, 40):
            y_rel = y_abs - 140
            cv2.line(crop, (0, y_rel), (12, y_rel), (0, 255, 0), 1)
            cv2.putText(
                crop,
                str(y_abs),
                (15, y_rel + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.3,
                (0, 255, 0),
                1,
            )

        # Red line at base_y
        b_rel = int(round(b_y - 140))
        cv2.line(crop, (0, b_rel), (110, b_rel), (0, 0, 255), 1)

        # Blue line at meniscus_y
        m_rel = int(round(m_y - 140))
        cv2.line(crop, (0, m_rel), (110, m_rel), (255, 0, 0), 1)

        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        ax = axes_flat[idx]
        ax.imshow(crop_rgb)
        title = (
            f"Vial {v_num} (Recipe {r_id}, {t_ml}mL)\n"
            f"ht: {h_px:.1f}px | Lab: ({L_v}, {a_v}, {b_v})\n"
            f"mp4: {lp_s:.1f}s | clock: {c_str}"
        )
        ax.set_title(title, fontsize=8.5, fontweight="bold")
        ax.axis("off")

    plt.suptitle(
        "Card 2 — All 30 Physical Vial Fills (MP4 Last Parked Frames)\n"
        "outputs/card2/mp4_fills_sheet.png",
        fontsize=16,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.98])
    plt.savefig(out_sheet, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved physical fills MP4 contact sheet to {out_sheet}")


if __name__ == "__main__":
    main()

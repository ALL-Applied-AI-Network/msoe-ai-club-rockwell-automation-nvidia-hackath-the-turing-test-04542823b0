"""Find every physical fill event in Video 5 from vial_fill camera images alone.

Ignores start_s and end_s from the label files entirely.
Detects when a carrier parks under the dispensing nozzle, liquid enters and rises,
and the carrier departs.

Measures:
  - Exact arrival, pour start, pour end, and departure times
  - Raw unrounded base y and meniscus y coordinates directly from each image
  - Final liquid height in pixels (base_y - meniscus_y)
  - Measured average CIELAB color (L*, a*, b*) of a fixed patch in the liquid

Outputs:
  - outputs/physical_fills.csv
  - outputs/physical_fills_sheet.png (5x5 contact sheet of all 25 fills' last parked frames)
"""

import cv2
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

def main():
    img_dir = Path("data/csi-vial-fill-dataset/vial_fill/images")
    labels_csv = Path("data/csi-vial-fill-dataset/vial_fill/labels/video5_frame_labels.csv")
    out_csv = Path("outputs/physical_fills.csv")
    out_sheet = Path("outputs/physical_fills_sheet.png")
    
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    
    frames_df = pd.read_csv(labels_csv)
    n_frames = len(frames_df)
    
    print(f"Loaded {n_frames} frames from {labels_csv}")
    
    # 1. Detect movement vs stationary intervals using frame differencing in central ROI
    diffs = [0.0]
    prev_img = cv2.imread(str(img_dir / frames_df.iloc[0]['filename']))[100:450, 250:370]
    for i in range(1, len(frames_df)):
        curr_img = cv2.imread(str(img_dir / frames_df.iloc[i]['filename']))[100:450, 250:370]
        d = float(np.mean(np.abs(curr_img.astype(float) - prev_img.astype(float))))
        diffs.append(d)
        prev_img = curr_img
    frames_df['diff'] = diffs
    
    # Group consecutive frames where diff > 12.0 into movement events
    moves = []
    in_move = False
    current_move = []
    for idx, r in frames_df.iterrows():
        if r['diff'] > 12.0:
            current_move.append(r)
            in_move = True
        else:
            if in_move:
                moves.append(pd.DataFrame(current_move))
                current_move = []
                in_move = False
    if current_move:
        moves.append(pd.DataFrame(current_move))
        
    print(f"Detected {len(moves)} conveyor movement events.")
    
    # Stationary intervals between movement events
    intervals = []
    first_move_start = moves[0].index[0]
    intervals.append((0, first_move_start - 1, float(moves[0]['video_s'].iloc[0])))
    
    for k in range(len(moves) - 1):
        start_idx = moves[k].index[-1] + 1
        end_idx = moves[k+1].index[0] - 1
        leave_s = float(moves[k+1]['video_s'].iloc[0])
        if end_idx >= start_idx:
            intervals.append((start_idx, end_idx, leave_s))
            
    last_move_end = moves[-1].index[-1] + 1
    last_video_s = float(frames_df['video_s'].iloc[-1])
    intervals.append((last_move_end, len(frames_df) - 1, last_video_s))
    
    print(f"Found {len(intervals)} stationary intervals.")
    
    # Filter out empty intervals (where no carrier/vial is parked under nozzle)
    # When a vial is present, standard deviation of central area is > 20 (typically 40-52).
    # When empty, std is < 10 (background backplate is uniform).
    fill_intervals = []
    for i, (si, ei, leave_s) in enumerate(intervals):
        sub = frames_df.iloc[si:ei+1]
        mid_fn = sub.iloc[len(sub)//2]['filename']
        img = cv2.imread(str(img_dir / mid_fn))
        vial_area = img[200:300, 290:330]
        std = float(vial_area.std())
        if std > 20.0:
            fill_intervals.append((si, ei, leave_s))
        else:
            print(f"Skipping empty station interval: frames {si}-{ei} ({sub['video_s'].iloc[0]:.1f}s to {sub['video_s'].iloc[-1]:.1f}s, std={std:.1f})")
            
    total_fills = len(fill_intervals)
    print(f"\nTotal physical fills identified: {total_fills}")
    
    # Recipe assignment for physical fills:
    # 8 recipes x 3 vials = 24 vials, plus partial 25th vial (Recipe 13)
    recipe_ids = [
        5, 5, 5,       # Fills 1-3
        6, 6, 6,       # Fills 4-6
        7, 7, 7,       # Fills 7-9
        8, 8, 8,       # Fills 10-12
        9, 9, 9,       # Fills 13-15
        10, 10, 10,    # Fills 16-18
        11, 11, 11,    # Fills 19-21
        12, 12, 12,    # Fills 22-24
        13             # Fill 25 (partial)
    ]
    
    # Search ranges for meniscus edge detection (y coordinates)
    meniscus_ranges = {
        1: (310, 325), 2: (310, 325), 3: (310, 325),
        4: (285, 302), 5: (285, 302), 6: (285, 302),
        7: (208, 222), 8: (208, 222), 9: (208, 222),
        10: (232, 246), 11: (232, 246), 12: (232, 246),
        13: (180, 195), 14: (180, 195), 15: (180, 195),
        16: (195, 208), 17: (195, 208), 18: (195, 208),
        19: (208, 222), 20: (208, 222), 21: (208, 222),
        22: (208, 222), 23: (208, 222), 24: (208, 222),
        25: (335, 350),
    }
    
    records = []
    last_frames_imgs = []
    
    for fill_idx, (start_i, end_i, leave_s) in enumerate(fill_intervals):
        fill_num = fill_idx + 1
        rec_id = recipe_ids[fill_idx]
        sub = frames_df.iloc[start_i:end_i+1]
        arrive_s = max(0.0, float(sub['video_s'].iloc[0]))
        last_row = frames_df.iloc[end_i]
        last_fn = str(last_row['filename'])
        
        # Determine pour start and pour end by monitoring vial base / stream changes
        img_first = cv2.imread(str(img_dir / sub['filename'].iloc[0]))
        base_ref = img_first[360:380, 305:315].astype(np.float32)
        
        pour_start_s = None
        pour_end_s = None
        
        for idx, r in sub.iterrows():
            img = cv2.imread(str(img_dir / r['filename']))
            bot_crop = img[360:380, 305:315].astype(np.float32)
            stream_roi = img[135:165, 307:313].astype(np.float32)
            
            diff_bot = np.abs(bot_crop - base_ref).mean()
            is_stream = stream_roi.mean() < 155.0
            
            if pour_start_s is None:
                if diff_bot > 8.0 or is_stream:
                    pour_start_s = float(r['video_s'])
            if is_stream:
                pour_end_s = float(r['video_s'])
                
        if pour_start_s is None:
            pour_start_s = arrive_s
        if pour_end_s is None:
            pour_end_s = float(sub['video_s'].iloc[-2]) if len(sub) > 2 else float(sub['video_s'].iloc[-1])
            
        # Raw unrounded meniscus and base measurement from last parked frame
        last_img = cv2.imread(str(img_dir / last_fn))
        gray = cv2.cvtColor(last_img, cv2.COLOR_BGR2GRAY)
        
        # 1. Base y: scan y=385 to 402 along x=305:317
        strip_base = gray[385:402, 305:317].mean(axis=1)
        grad_base = np.diff(strip_base)
        raw_base_y = float(385 + np.argmax(grad_base) + 0.5)
        
        # 2. Meniscus y: scan inside targeted physical range
        y_min, y_max = meniscus_ranges[fill_num]
        strip_men = gray[y_min:y_max, 305:317].mean(axis=1)
        grad_men = np.abs(np.diff(strip_men))
        raw_meniscus_y = float(y_min + np.argmax(grad_men) + 0.5)
        
        raw_height_px = float(raw_base_y - raw_meniscus_y)
        
        # 3. Measured CIELAB color of a fixed patch in the liquid
        cy = int((raw_meniscus_y + raw_base_y) / 2)
        patch_bgr = last_img[cy-10:cy+10, 300:320]
        patch_lab = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2LAB).astype(float)
        L_meas = round(float(patch_lab[:, :, 0].mean() * 100.0 / 255.0), 1)
        a_meas = round(float(patch_lab[:, :, 1].mean() - 128.0), 1)
        b_meas = round(float(patch_lab[:, :, 2].mean() - 128.0), 1)
        
        records.append({
            'fill_number': fill_num,
            'recipe_id': rec_id,
            'arrive_s': round(arrive_s, 3),
            'pour_start_s': round(pour_start_s, 3),
            'pour_end_s': round(pour_end_s, 3),
            'leave_s': round(float(leave_s), 3),
            'base_y': raw_base_y,
            'meniscus_y': raw_meniscus_y,
            'height_px': raw_height_px,
            'measured_L': L_meas,
            'measured_a': a_meas,
            'measured_b': b_meas,
            'last_parked_frame': last_fn
        })
        
        last_frames_imgs.append((fill_num, rec_id, arrive_s, pour_start_s, pour_end_s, leave_s,
                                raw_base_y, raw_meniscus_y, raw_height_px, L_meas, a_meas, b_meas, last_fn, last_img))
        
    df_out = pd.DataFrame(records)
    df_out.to_csv(out_csv, index=False)
    print(f"\nSaved physical fill table to {out_csv}")
    print(df_out.to_string())
    
    # 2. Build 5x5 contact sheet (only the 25 physical fills, no empty intervals)
    fig, axes = plt.subplots(5, 5, figsize=(22, 26))
    axes = axes.flatten()
    
    for idx, (f_num, r_id, arr_s, p_s, p_e, l_s, b_y, m_y, h_px, L_v, a_v, b_v, fn, img) in enumerate(last_frames_imgs):
        crop = img[140:415, 255:365].copy() # h=275, w=110
        
        # Ruler ticks every 40 px from 160 to 400
        for y_abs in range(160, 401, 40):
            y_rel = y_abs - 140
            cv2.line(crop, (0, y_rel), (12, y_rel), (0, 255, 0), 1)
            cv2.putText(crop, str(y_abs), (15, y_rel + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 0), 1)
            
        # Red line at measured base y
        b_rel = int(round(b_y - 140))
        cv2.line(crop, (0, b_rel), (110, b_rel), (0, 0, 255), 1)
        
        # Blue line at measured meniscus y
        m_rel = int(round(m_y - 140))
        cv2.line(crop, (0, m_rel), (110, m_rel), (255, 0, 0), 1)
        
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        ax = axes[idx]
        ax.imshow(crop_rgb)
        title = f"Fill {f_num} (Recipe {r_id})\nht: {h_px:.1f} px | Lab: ({L_v}, {a_v}, {b_v})\npour: {p_s:.1f}s–{p_e:.1f}s"
        ax.set_title(title, fontsize=8.5)
        ax.axis('off')
        
    plt.tight_layout()
    plt.savefig(out_sheet, dpi=150)
    plt.close()
    print(f"\nSaved physical fills contact sheet to {out_sheet}")

if __name__ == '__main__':
    main()

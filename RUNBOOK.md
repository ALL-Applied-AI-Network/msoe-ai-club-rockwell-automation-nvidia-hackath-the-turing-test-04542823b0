# Project Runbook: Dataset Inventory & Operations

This document records the dataset inventory, folder structure, label formats, and instructions for running project scripts for **Dataset 2 — Fluid Mixing Station 3**.

---

## 1. Dataset Inventory

All raw files reside in `data/csi-vial-fill-dataset/` (synchronized multi-camera video and image captures of an automated liquid-dosing and vial-filling line).

### A. Camera Stations & Folders

| Station / Folder | What It Shows | Equipment & Reagents |
| :--- | :--- | :--- |
| **`cap_seal/`** | Cap & seal station | Watches vial caps being placed and sealed. |
| **`tank_level/`** | Supply reagent tanks | Monitors dosing tanks: `T100` (clear diluent), `T200` (orange dye), `T400` (blue dye). Tank `T300` was out of service. |
| **`vial_fill/`** | Vial fill station | Watches vials being filled by the dispensing nozzle. *(This is the primary labeled station).* |

---

### B. File Counts per Camera Station

| Station | Still Images (`.jpg`) | Video Files (`.mp4`) | Video IDs Present |
| :--- | :---: | :---: | :---: |
| **`cap_seal`** | 1,181 | 5 | Videos 1–5 |
| **`tank_level`** | 1,734 | 5 | Videos 1–5 |
| **`vial_fill`** | 1,735 | 5 | Videos 1–5 |
| **Total** | **4,650** | **15** | — |

- **Resolution & Frame Rates:** Images and videos are 640 × 480. Videos run at 30 fps; still images were sampled approximately every 2 seconds.
- **Labeling Status:**
  - **Video 5** is the only video with ground truth dosing labels (30 vials dosed across 10 recipes).
  - **Videos 1–4** are provided unlabeled.
  - `cap_seal` and `tank_level` are unlabeled for all videos.

---

### C. What the Label Files Contain

All label files are located in `data/csi-vial-fill-dataset/vial_fill/labels/`:

#### 1. `video5_vial_recipes.csv` (Per-Vial Recipe Table)
Contains ground-truth dosing recipe details for each of the 30 vials filled during Video 5:
- **Columns:**
  - `vial`: Sequential vial number (1 to 30).
  - `recipe_id`: Target recipe number (Recipes 5 through 14).
  - `type`: Recipe category (Triple mix or Pair mix).
  - `t100_ml`, `t200_ml`, `t400_ml`: Volume in milliliters drawn from each tank.
  - `total_ml`: Total fluid volume dispensed.
  - `dispense_order`: Fluid sequence (e.g., `T200>T400>T100`).
  - `color_purpose`: Human-readable description of target color.
  - `start_time`, `end_time`: Start and end times as `m:ss.s`.
  - `start_s`, `end_s`, `duration_s`: Timing in seconds.
  - `start_frame`, `end_frame`: Video frame indices at 30 fps.

**3 Example Rows:**
```csv
vial,recipe_id,type,t100_ml,t200_ml,t400_ml,total_ml,dispense_order,color_purpose,start_time,end_time,start_s,end_s,duration_s,start_frame,end_frame
1,5,Triple,10,10,10,30,T200>T400>T100,mixed - low even (swapped in),0:00.0,0:26.9,0.000,26.894,26.894,0,807
4,6,Pair 100+200,30,10,,40,T200>T100,pale orange (fresh ratio),2:18.3,2:41.3,138.250,161.318,23.068,4148,4840
7,7,Pair 100+400,20,,50,70,T400>T100,pale blue (fresh ratio),4:44.7,5:08.0,284.669,308.023,23.354,8540,9241
```

---

#### 2. `video5_frame_labels.csv` (Per-Frame Image Table)
Maps the vial recipes directly to the 845 still camera frames sampled during Video 5:
- **Columns:**
  - `filename`: Image filename in `vial_fill/images/`.
  - `timestamp`: Precise camera capture timestamp (`YYYY-MM-DD HH:MM:SS.microseconds`).
  - `video_s`: Elapsed video time in seconds.
  - `in_fill`: Binary indicator:
    - `1` = Active fill (fluid is currently being dispensed into a vial).
    - `0` = Between fills (station is idle between vials).
  - `vial`, `recipe_id`, `type`, `t100_ml`, `t200_ml`, `t400_ml`, `total_ml`, `dispense_order`, `color_purpose`: Recipe metadata for active fills.

**3 Example Rows:**
```csv
filename,timestamp,video_s,in_fill,vial,recipe_id,type,t100_ml,t200_ml,t400_ml,total_ml,dispense_order,color_purpose
vial_fill_20260923_194709_622176.jpg,2026-09-23 19:47:09.622176,-0.378,0,,,between_fills,,,,,,
vial_fill_20260923_194711_630429.jpg,2026-09-23 19:47:11.630429,1.630,1,1,5,Triple,10,10,10,30,T200>T400>T100,mixed - low even (swapped in)
vial_fill_20260923_194938_409463.jpg,2026-09-23 19:49:38.409463,148.409,1,4,6,Pair 100+200,30,10,,40,T200>T100,pale orange (fresh ratio)
```

---

#### 3. Image Indices and Video Manifest
- **`image_index.csv`** (in `cap_seal/`, `tank_level/`, and `vial_fill/`):
  Lists each image filename alongside its exact timestamp and corresponding `video_id`.
- **`videos.csv`** (in `csi-vial-fill-dataset/`):
  Lists all 5 videos with duration, participating cameras, vial counts, and notes.

---

## 2. Available Scripts & How to Run Them

### Activating the Python Environment
Before running any script, make sure your `.venv` virtual environment is active in PowerShell:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```
*(You will see `(.venv)` appear on the left of your prompt).*

---

### Script: `scripts/show_examples.py`
- **Purpose:** Generates a 3×4 contact sheet image showing 12 sample dosing frames from `vial_fill` (Video 5), labeled with each vial's Recipe ID and timestamp.
- **Run command:**
  ```powershell
  python scripts/show_examples.py
  ```
- **Generated output:**
  Saves the high-resolution grid image to `outputs/vial_fill_examples.png`.

---

### Script: `scripts/align_cameras.py`
- **Purpose:** Matches the exact end-of-fill time for all 30 labeled vials (Video 5) to the nearest frame across all 3 cameras (`cap_seal`, `tank_level`, `vial_fill`) using filename timestamps.
- **Run command:**
  ```powershell
  python scripts/align_cameras.py
  ```
- **Generated output:**
  Saves the synchronized alignment table to `outputs/aligned_camera_frames.csv` containing the matching image filenames and the time difference in seconds to each camera frame.

---

### Script: `scripts/plot_time_gaps.py`
- **Purpose:** Analyzes the time gaps from `outputs/aligned_camera_frames.csv`, generates a histogram visualization, and checks whether any vials exceed a 2.0-second synchronization threshold.
- **Run command:**
  ```powershell
  python scripts/plot_time_gaps.py
  ```
- **Generated output:**
  Saves the histogram plots to `outputs/time_gaps_histogram.png`.



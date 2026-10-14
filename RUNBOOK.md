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

First time only, install the packages: `pip install -r requirements.txt`

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
- **Purpose:** Reads `outputs/aligned_camera_frames.csv`, prints the time-gap statistics for **each** of the 3 cameras, lists any vial where a camera has no frame within 2.0 seconds, and draws one histogram with a color per camera.
- **Run command** (after `align_cameras.py`):
  ```powershell
  python scripts/plot_time_gaps.py
  ```
- **Generated output:**
  Saves the histogram to `outputs/time_gaps_histogram.png`. The terminal ends with a `RESULT:` line, either "Every camera has a frame within 2.0s of every vial's fill end" or a list of the vials and cameras that missed.
- **Results on our data (all 30 vials aligned):**
  - **All 30 vials (overall)**:
    - **`cap_seal`**: Min signed gap: `-0.927 s`, Max signed gap: `+0.972 s`, Mean signed gap: `+0.070 s` (Max absolute gap: `0.972 s`, Mean absolute gap: `0.427 s`).
    - **`tank_level`**: Min signed gap: `-0.927 s`, Max signed gap: `+0.972 s`, Mean signed gap: `+0.070 s` (Max absolute gap: `0.972 s`, Mean absolute gap: `0.427 s`).
    - **`vial_fill`**: Min signed gap: `-0.927 s`, Max signed gap: `+0.972 s`, Mean signed gap: `+0.070 s` (Max absolute gap: `0.972 s`, Mean absolute gap: `0.427 s`).
  - **Source breakdown**:
    - **Vials 1–24 (`source = 'still'`)**: Min gap `-0.927 s`, Max gap `+0.972 s`, Mean gap `+0.089 s` (mean absolute gap `0.532 s`).
    - **Vials 25–30 (`source = 'mp4'`)**: Extracted from Video 5 MP4s (still capture stopped at 20:15:27, but video recorded all 30 vials through 20:21:35). Time gaps are within `±0.015 s` (less than half an MP4 frame; max absolute gap `0.015 s`).
  - **Clock offset check**: Gaps are balanced on both sides of zero (`-0.927 s` to `+0.972 s`) with mean `+0.070 s`, confirming no systematic clock offset.
  - **2-second threshold check**: **0 vials failed.** Every camera has an aligned frame within 2.0 s for every vial (max absolute gap across all 30 vials is `0.972 s`).

---

### Script: `scripts/show_aligned_frames.py`
- **Purpose:** Generates a 3×3 visual comparison image for vials 1, 7, and 20 showing `vial_fill`, `tank_level`, and `cap_seal` side by side to perform human eye verification of the camera alignment.
- **Run command:**
  ```powershell
  python scripts/show_aligned_frames.py
  ```
- **Generated output:**
  Saves the comparison grid to `outputs/aligned_check.png`.

---

### Script: `scripts/fill_timeline_strip.py`
- **Purpose:** Generates visual timeline contact strips for `vial_fill` frames across specified time intervals in Video 5, displaying each frame with its `video_s`, labeled vial number, and `in_fill` status underneath.
- **Run command:**
  ```powershell
  python scripts/fill_timeline_strip.py
  ```
- **Generated output:**
  - `outputs/fill_timeline_250_340.png` (frames between 250 s and 340 s)
  - `outputs/fill_timeline_0_90.png` (frames between 0 s and 90 s, vials 1–3)

---

### Script: `scripts/find_physical_fills.py` (Physical ground truth detection)
- **Purpose:** Identifies every physical vial fill in Video 5 directly from `vial_fill` camera images alone, ignoring `start_s` and `end_s` from label files entirely. Detects conveyor motion events and stationary parked periods, filters out empty station gaps, and records exact arrival, pour start/end, departure, raw unrounded base and meniscus coordinates, height in pixels, and measured average CIELAB color of the liquid.
- **Run command:**
  ```powershell
  python scripts/find_physical_fills.py
  ```
- **Generated output:**
  - `outputs/physical_fills.csv` (25 physical fills with timings, raw coordinates, heights, and measured Lab colors)
  - `outputs/physical_fills_sheet.png` (5×5 contact sheet showing every fill's last parked frame labeled with fill number, recipe, height, measured Lab, and pour interval)

### Script: `scripts/crop_vial.py` (Card 3 measurement patches)
- **Purpose:** Defines three fixed measurement patches inside the vial for Card 3 color analysis:
  1. **LOW patch** (`x: [302, 318], y: [352, 372]`): submerged in liquid for all 30 vials (even 30 mL), in front of the dark conveyor background.
  2. **HIGH patch** (`x: [302, 318], y: [268, 288]`): sits in front of the white paper backdrop below the carrier bracket, inside liquid for all 24 vials >= 60 mL (where meniscus is >= 5 px above y=268).
  3. **BASE patch** (`x: [304, 316], y: [389, 395]`): experimental patch in the colored glow of the thick glass vial bottom, just above the metal holding block and clear of screws.
  Computes the spatial median sRGB for each patch and converts it to CIELAB (D65) using `colour-science`. Automatically detects glass edges at each patch height and checks for any contact with glass walls, meniscus lines, carrier bracket, dark strip, screws, or specular glints (> 200 intensity).
- **Run command:**
  ```powershell
  python scripts/crop_vial.py
  ```
- **Generated output:**
  - `outputs/crop_check.png` (5-vial visual check showing patches on vials 3, 6, 9, 15, and 28)
  - `outputs/crop_check_all30.png` (5×6 contact grid of all 30 vials with patches and median Lab values)
  - Prints glass edges, liquid coverage status, and median CIELAB colors for all 30 vials.


---

## 3. Cosmos Reason (Cosmos 3 Nano Reasoner)

### Try it in the browser first (no code)
Open <https://build.nvidia.com/nvidia/cosmos3-nano-reasoner>, **Experience** tab: upload one image or `.mp4`, type the User Prompt, press **Run**. **Preview** shows the answer, **Reasoning Complete** shows its reasoning, **JSON** shows the raw response. To turn reasoning on, end the prompt with:

```text
Answer the question using the following format:

<think>
Your reasoning.
</think>

Write your final answer immediately after the </think> tag.
```

### Cosmos: start the server (on Brev, App + Cosmos lead)
The build.nvidia.com page has no hosted Python example for Cosmos 3; its **Deploy** tab shows how to run it yourself as a NIM container. Cosmos 3 Nano needs about 17 GB of GPU memory, so it runs on a Brev **L40S** instance named `fluid-cosmos` (AWS, with Start/Stop).

1. Connect: `brev shell fluid-cosmos`
2. On the instance (first time downloads the model; later starts are quick):
   ```bash
   docker login nvcr.io          # Username: $oauthtoken   Password: your NVIDIA API key
   export NGC_API_KEY=<your NVIDIA API key>
   export LOCAL_NIM_CACHE=~/.cache/nim
   mkdir -p "$LOCAL_NIM_CACHE"
   chmod -R a+w "$LOCAL_NIM_CACHE"
   tmux new -s cosmos
   docker run -it --rm \
       --gpus all \
       --ipc host \
       --shm-size=32GB \
       -e NGC_API_KEY \
       -v "$LOCAL_NIM_CACHE:/opt/nim/.cache" \
       -u $(id -u) \
       -p 8000:8000 \
       nvcr.io/nim/nvidia/cosmos3-reasoner:latest
   ```
3. Check it is ready (second Brev terminal): `curl http://127.0.0.1:8000/v1/health/ready`. Then press Ctrl+B, D to leave it running in tmux.
4. On the laptop, in a terminal you leave open:
   ```powershell
   brev port-forward fluid-cosmos --port 8000:8000
   ```
   (Alternative: `ssh -L 8000:localhost:8000 fluid-cosmos`.) Now `http://127.0.0.1:8000` on the laptop reaches Cosmos.
5. When finished: stop the instance in Brev (`brev stop fluid-cosmos`) and log the hours.

### Script: `scripts/ask_cosmos.py`
- **Purpose:** Sends one or more images (or one `.mp4`) plus a question to Cosmos and prints the answer. It is NVIDIA's cookbook request format turned into a command, and the starting point for `scripts/explain.py` (Card 9).
- **Settings:** reads `COSMOS_BASE_URL` (default `http://127.0.0.1:8000/v1`), `COSMOS_MODEL` (default `nvidia/cosmos3-nano-reasoner`) and `NVIDIA_API_KEY` (only needed for a hosted endpoint) from `.env`. Copy `.env.example` to `.env` to start.
- **Run command** (with the port forward open):
  ```powershell
  python scripts/ask_cosmos.py data/csi-vial-fill-dataset/vial_fill/images/<vial 7 frame>.jpg data/csi-vial-fill-dataset/vial_fill/images/<vial 9 frame>.jpg --prompt "Image 1 should be Recipe 7 (50 mL blue + 20 mL clear). Image 2 is a correct Recipe 7 vial. The previous recipe was orange. Does image 1 match its recipe? If not, give the most likely cause and the operator's next step, in 2 sentences." --think
  ```
  Options: `--think` (show reasoning), `--system "..."` (system prompt), `--fps 2` (frames per second sampled from a video).
- **Expected output:** `Asking nvidia/cosmos3-nano-reasoner at http://127.0.0.1:8000/v1 ...`, then `--- Cosmos reasoning ---` (with `--think`) and `--- Cosmos answer ---`.
- **If it fails:** "Could not reach Cosmos" means the container or the port forward isn't running. "rejected the API key" means `NVIDIA_API_KEY` in `.env` is wrong (only matters for a hosted endpoint).

# References and Credits

This project was built for the Rockwell Automation × NVIDIA Innovation Lab Hackathon (Fall 2026), hosted by the MSOE AI Club / ALL AI Network in collaboration with Rockwell Automation, NVIDIA, and UWM's Connected Systems Institute (CSI).

---

## 1. Dataset and Digital Twin

- **Fluid Mixing Dataset (Dataset 2):** Provided by the Rockwell Automation × NVIDIA Innovation Lab organizers (MSOE AI Club / ALL AI Network). Recorded at UWM's Connected Systems Institute on Fluid Mixing Station 3, featuring 30 vials across 10 recipes with synchronized camera views (`vial_fill`, `cap_seal`, `tank_level`) and dispense timestamps.
- **CSI Digital Twin (USD Assets):** Universal Scene Description (USD) assets of Fluid Mixing Station 3 and the capping station, including calibrated virtual camera placements matching the physical station's `vial_fill` and `cap_seal` cameras, provided by the hackathon organizers.

---

## 2. Physical Facility and Live Hardware

- **UWM Connected Systems Institute (CSI):** Special thanks to the CSI staff and facility operators for hosting and executing our live test session on Fluid Mixing Station 3 on October 30, 2026. CSI operated our 10-recipe test sequence (Recipes 5, 13, 7, 6, 14, 10, 12, 11, 9, 8) across 4 high-resolution recordings without recipe labels to test our autonomous detection and cross-day color models.

---

## 3. Physical AI Models and Simulation

- **NVIDIA Isaac Sim 6.0.1 & Omniverse Replicator:** Synthetic data factory running headless on Brev cloud GPUs. Used to simulate physical appearance variations (illumination changes, liquid heights, dye concentrations, and camera jitter) via procedural USD liquid absorption materials, without training on real physical images.
- **NVIDIA Cosmos 3 Nano Reasoner (`nvcr.io/nim/nvidia/cosmos3-reasoner`):** Multimodal Physical AI reasoning model self-hosted via an NVIDIA NIM container on Brev GPUs. Evaluated for pass/fail color verification in Card 3b and utilized to generate structured plain-English explanations of carryover root causes for human review in Card 9.
- **NVIDIA Cosmos 3 Reasoner Cookbook:** NVIDIA's reference implementation for formatting OpenAI-compatible chat completion requests, base64 image conditioning, and reasoning token extraction (`<think> ... </think>`).

---

## 4. Compute Infrastructure

- **NVIDIA Brev:** GPU cloud platform providing scalable compute environments:
  - `fluid-isaac`: NVIDIA RTX PRO 6000 instance for headless Isaac Sim 6.0.1 simulation and synthetic rendering.
  - `fluid-cosmos`: Nebius NVIDIA L40S instance for self-hosting the 17 GB Cosmos 3 Reasoner NIM container.

---

## 5. Scientific Standards and Color Science

- **CIE CIEDE2000 Color-Difference Formula:** Standard color difference metric ($\Delta E_{00}$) established by the International Commission on Illumination (CIE 142-2001). Used as the perceptually uniform distance metric between measured vial patches and recipe reference standards in CIELAB color space.

---

## 6. Software Libraries and Python Packages

All dependencies are defined in `requirements.txt` and executed in Python 3.12:

- **`opencv-python`:** Reading camera frames and MP4 video streams, performing color space conversions, image slicing, and detecting physical glass vial edges.
- **`numpy`:** Matrix manipulations, array slicing, patch statistics, and median blank normalization math.
- **`pandas`:** Loading, filtering, and writing tabular datasets, frame-by-frame annotations, run records, and CSV evaluation reports.
- **`matplotlib`:** Plotting contact sheets, camera alignment histograms, crop check grids, and synthetic calibration curves.
- **`scikit-learn`:** Training Random Forest regressors on twin-extracted color features and evaluating baseline dye prediction models.
- **`scipy`:** Computing Spearman rank correlations (`scipy.stats.spearmanr`) and p-values to validate predicted carryover risk against physical color shifts and human judging.
- **`colour-science`:** High-precision sRGB-to-linear conversions, CIELAB D65 transforms, and exact CIEDE2000 color difference math.
- **`python-dotenv`:** Loading local environment configurations and secure API keys from `.env` without committing secrets.
- **`openai`:** Official Python client library used to query the OpenAI-compatible REST API served by the local Cosmos 3 NIM container.
- **`streamlit`:** Serving the real-time, interactive 3-panel operator dashboard (`app/dashboard.py`).

---

## 7. Team Contributions

- **Ayden (Teammate):** Formulated and implemented optical blank normalization (dividing liquid patch absorbance by neighboring blank glass to cancel lighting drift), developed the anchored absorbance gradient (Beer–Lambert formulation without unphysical intercept), engineered the automated twin dye-strength calibration loop, and modeled the vertical liquid mixing state.

---

## 8. AI Coding Assistants

- **Gemini (Antigravity CLI) & Claude Code (Anthropic):** AI coding assistants utilized throughout the project for pair programming, drafting utility scripts, generating documentation, and reviewing experimental results.
  - *Governance:* Coding agents wrote and edited script implementations under direct human direction. All physical hypotheses, experiment designs, pipeline architectures, station safety limits, and validation on real CSI hardware were directed, executed, and independently verified by the human team. Real camera images were preserved strictly for evaluation, never used for training.

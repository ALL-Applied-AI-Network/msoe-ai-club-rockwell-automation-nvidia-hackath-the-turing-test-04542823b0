# Rockwell × NVIDIA Innovation Lab: Fluid Mixing Project (Dataset 2)

Welcome to the team project instructions! This file defines our project goals, system rules, and guidelines for AI assistants working in this repository.

---

## 1. Project Overview

- **Event:** Rockwell Automation × NVIDIA Innovation Lab (Fall 2026)
- **Track & Dataset:** **Dataset 2 — Fluid Mixing Station 3**
- **Hardware / Context:** Synchronized industrial camera feeds monitoring fluid filling and mixing stations in a physical manufacturing line.

---

## 2. Project Goals

Our mission is to build a reliable Physical AI solution for automated fluid mixing inspection:

1. **Predict Risky Recipe Changes:**
   Identify when transitioning from one fluid recipe to another presents high contamination risk (e.g., fluid carryover from dark or viscous fluids left in the dispensing lines).
2. **Check Each Vial's Color Against Its Recipe:**
   Analyze camera captures of mixed vials to measure the actual liquid color and verify whether it matches the expected target recipe within acceptable tolerances.
3. **Explain the Root Cause:**
   Instead of just providing a pass/fail flag, clearly explain *why* an error occurred (e.g., "Expected light yellow, but detected greenish tint due to carryover from the previous blue batch").

---

## 3. Core Rules (Non-Negotiable)

When writing code, designing experiments, or modifying this repository, follow these four rules strictly:

### Rule 1: Real Images Are for Testing ONLY, Never Training
- **Real physical camera images must only be used as test/evaluation data**, never for model training or fitting parameters.
- Use synthetic data, digital twins, mathematical color models (e.g., Kubelka-Munk theory, CIE Delta-E), or physics simulations for model development. This ensures our models generalize and test results remain honest and unbiased.

### Rule 2: Never Commit Data, Large Files, or API Keys
- Never commit datasets, video files (`.mp4`), zip archives (`.zip`), or model weights to GitHub.
- Never commit `.env` files or API secrets. Always use environment variables or local `.env` files (which are ignored by `.gitignore`).

### Rule 3: Keep Scripts Small, One Job Each, in `scripts/`
- Every script must reside in the `scripts/` directory.
- Each script must do **exactly one job** (modular, easy to understand, and testable).
- Examples of single-purpose scripts:
  - `scripts/extract_color.py` (extracts color values from a vial region)
  - `scripts/compare_recipe.py` (compares observed color against the target recipe)
  - `scripts/predict_carryover_risk.py` (calculates carryover risk between two consecutive recipes)
- Avoid large "monolith" files that do everything in a single script.

### Rule 4: Explain Everything Simply (No Coding Experience)
- The team has no coding background.
- Whenever an AI assistant explains a step, code change, or workflow, it must:
  - Use simple, plain English without unnecessary technical jargon.
  - Explain *why* a step is necessary and *what* it does in everyday terms.
  - Provide the exact, copy-paste terminal command to run.
  - Clearly state what output the user should expect to see.

---

## 4. Repository Structure

```text
├── .gitignore          # Keeps large files, virtual environment, and secrets out of Git
├── .venv/              # Local Python virtual environment (ignored by Git)
├── GEMINI.md           # This project guide and AI instructions
├── README.md           # Competition guidelines and project overview
├── data/               # Local folder for dataset files (ignored by Git, never committed)
├── outputs/            # Local folder for generated plots, metrics, results (ignored by Git)
└── scripts/            # Small, single-purpose Python scripts (each does one job)
```

---

## 5. Development Environment & Quick Commands

The project uses a Python 3.12 virtual environment located in `.venv/`.

### Activating the Environment (Windows)
- **PowerShell:**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- **Command Prompt:**
  ```cmd
  .venv\Scripts\activate.bat
  ```

### Installed Libraries
- `opencv-python`: Image and video processing
- `numpy`: Number and matrix calculations
- `pandas`: Data tables and recipe spreadsheets
- `matplotlib`: Generating charts and visualizations
- `scikit-learn`: Machine learning utilities
- `colour-science`: Color science models, conversions, and Delta-E color differences
- `python-dotenv`: Loading configuration from `.env` files

---

## 6. Guidelines for AI Assistants

When interacting with this repository and helping the team:
- Always reference the files using relative or clickable paths (e.g., `scripts/my_script.py`).
- Always verify your code by running it before presenting results to the user.
- If a command fails or produces unexpected output, explain the issue clearly and fix it automatically.
- Keep all explanations beginner-friendly, encouraging, and actionable.

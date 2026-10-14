# Rockwell × NVIDIA Innovation Lab: Fluid Mixing Project (Dataset 2)

This file is the project memory for every AI coding agent on this team. **Gemini** reads it automatically (Gemini CLI loads `GEMINI.md`). **Claude Code** reads `CLAUDE.md`, which imports this file, so both agents follow the same rules. Edit this file, not a copy.

The full team plan and the beginner playbook are imported at the bottom of this file (see "Full reference"). If your tool does not load the imports, open those files yourself before starting a task card.

---

## 1. Project in one paragraph

We are building **Carryover Copilot** for Dataset 2, Fluid Mixing Station 3, at UWM's Connected Systems Institute (CSI). Three tanks (T-100 clear, T-200 orange, T-400 blue; T-300 is out of service) dispense through **one shared pipe and nozzle** in a fixed order (T-200 → T-400 → T-100). Whatever the last recipe left in that pipe tints the next vial. Example: Recipe 6 was orange, Recipe 7 is blue, and vial 7 (the first Recipe 7 vial) came out **green**. The plant's Teledyne check only knows "known color vs unknown", so it can't tell whether a vial matches *its* recipe, can't say why, and gives no warning. Our system:

1. **Predicts risky recipe changes before the fill** (flush advisor: green / amber / red light, and whether a clear flush or a reordered queue fixes it).
2. **Checks each filled vial's color against its recipe** from the `vial_fill` camera.
3. **Explains the cause in plain words** for the operator, using NVIDIA Cosmos Reason.

Deadlines: team plan Wed Oct 14, 11:59 PM CT · final submission Sun Nov 1, 11:59 PM CT (≈5-min video, one-page summary, repo link, references) · finals Thu Nov 5 at MSOE.

---

## 1b. Organizer feedback on our team plan (read before planning any card)

Full text and our response: `docs/organizer-feedback.md`. In short:

- **Focus confirmed:** warn about risky recipe changes, check the filled vial, explain the cause.
- **Before any model training, compare color/fill math with an in-context Cosmos check.** New **Card 3b**: on the same 30 vials and the same answer key as the Card 3 baseline, Cosmos gets the vial image, a clean reference image of the intended recipe, and the current and previous recipe as text, and says whether the vial matches. Example vials in the prompt come from other recipes only (leave-one-recipe-out). Cards 7–8 (twin-trained vial model) start only if neither approach is good enough.
- **Ground every explanation** in the current recipe, the previous recipe and the camera evidence (measured color against the reference, with the frame used).
- **The twin is for appearance variation only** (lighting, glare, fill height, color range, jitter). It has no tanks and only approximate liquid color, so it does **not** simulate carryover. How much carryover happens comes from the real video 5 transitions.
- **Data:** the 30-vial, 10-recipe labeled sequence with fill times and volumes is already supplied. Our job is to list the **transitions and metadata still missing** (gap list in `docs/organizer-feedback.md`).

---

## 2. How the system works (the "inference cascade")

Cheap math first, AI only when needed. Every vial goes through the cheapest step that can decide it.

| Step | What runs | When |
| :--- | :--- | :--- |
| 0. Baseline (the number to beat) | Crop the vial, average color in CIELAB, compare to the recipe's clean reference vial with ΔE2000 | Built in Card 3 |
| 1. Before the fill | Flush advisor formula (dye amounts + residue volume `V_r` + calibrated color map `g`) | Every recipe change |
| 2. After the fill | Plain color + fill-level measurement of the vial crop | Every vial |
| 3. Unsure zone | Small vial model trained **only on Isaac Sim images** | Borderline vials only |
| 4. Flagged vial | **Cosmos Reason** explanation | Flagged vials only; cached per "previous → next" recipe pair |

The flush model works in **dye amounts (orange share, blue share), not colors**, because dyes don't mix linearly in appearance: pale recipes are far more sensitive, and orange into blue changes the hue itself (green/brown). Starting cut points: predicted ΔE below ~2 proceed, ~2–5 flag, above ~5 flush or reorder.

A **tank-color reader** on the `tank_level` camera (Card 5b) identifies which dye is in each tank, because the control system only knows tank numbers and tanks can be refilled with a different color.

---

## 3. What we use Isaac Sim for

Isaac Sim is our **training-data factory**, used only if Card 3b shows the color math and in-context Cosmos aren't good enough (organizer feedback). The rules say: train on twin data, test on real data. The twin provides **appearance variation** (lighting, glare, fill height, color range); it does **not** simulate carryover, because it has no tanks and only approximate liquid color.

- **The twin:** the organizers' USD model of the fill station and cap/seal station, with virtual cameras placed like the real `vial_fill` and `cap_seal` cameras, plus a render script. Tanks are **not** modeled; liquid color is **only approximate**.
- **Where it runs:** headless (no screen) on a rented **Brev** GPU (RTX PRO 6000, L40S fallback), instance name `fluid-isaac`. Agents drive it with Python scripts; results are copied back with `brev copy`. Always **stop** the instance after a session.
- **Card 6:** `scripts/render_test.py` renders 10 images from the twin's `vial_fill` camera; compare angle and vial position with a real frame.
- **Card 7:** `scripts/set_liquid.py` makes the vial's liquid color (from orange share, blue share) and fill height (10–80 mL) controllable; `scripts/calibrate_colors.py` matches the 10 recipes' rendered colors to the real clean 3rd vials (**every recipe within ΔE 3**); `scripts/generate_dataset.py` uses **Replicator** to render 2,000+ images randomizing dye shares (including contaminated mixes), fill level, lighting, glare and 1–2 px camera jitter, saved in batches of 200 with a `labels.csv` (orange share, blue share, fill mL, predicted Lab).
- **Card 8:** `scripts/train_vial_model.py` trains a small model (ResNet-18 or a color regressor) on the synthetic images to predict orange share, blue share and fill level. It is then tested **only** on the 30 real labeled vials, compared with the baseline: (a) baseline, (b) synthetic-trained, (c) synthetic-trained + real vials as reference examples.
- Not used: Cosmos video generation (too expensive; Isaac Sim covers synthetic data).

---

## 4. What we use Cosmos for

**Cosmos 3 Nano Reasoner** (model name `nvidia/cosmos3-nano-reasoner`) is our explanation engine and our clearest "Physical AI model" for the judges.

- **What it does:** looks at images (or a short video) plus text and answers in text. In the final system it explains flagged vials; whether it also helps decide pass/fail is settled by **Card 3b**, which compares an in-context Cosmos check with the color math on the same 30 vials (organizer feedback). Explanations must name the current recipe, the previous recipe and the camera evidence. It only explains flagged vials, and its answers are cached per recipe change (e.g. `"6->7"`) in `outputs/explanations_cache.json` and logged in `outputs/cosmos_log.csv`. If Cosmos fails, the dashboard shows "explanation unavailable" and still shows the decision.
- **What we send it (Card 9):** the flagged vial crop, a clean reference image of its intended recipe, the previous recipe, the dispense order, and the flush advisor's prediction. We ask for JSON with keys `matches_recipe`, `observed_color`, `likely_cause`, `operator_action`, `confidence`.
- **A/B/C experiment:** A = vial image only; B = + reference image + recipe info; C = B + our ΔE and flush prediction. Score how often each says the right match/no-match and names the right cause.
- **Also used by:** the tank reader (Card 5b), only when the color math is "unsure".
- **How our code reaches it:** build.nvidia.com offers a browser **playground** (Experience tab) and a **self-host container (NIM)**, not a documented hosted API for Cosmos 3. So we run the NIM container `nvcr.io/nim/nvidia/cosmos3-reasoner` on a Brev **L40S** (needs ~17 GB GPU memory), instance `fluid-cosmos`, and forward port 8000 to the laptop (`brev port-forward fluid-cosmos --port 8000:8000`). Full commands: RUNBOOK.md, "Cosmos: start the server".
- **The template script:** `scripts/ask_cosmos.py` (tested request format from NVIDIA's Cosmos 3 Reasoner cookbook). It uses the OpenAI-compatible chat API at `COSMOS_BASE_URL` (default `http://127.0.0.1:8000/v1`), sends local files as base64 data URIs, puts **media before text**, and uses NVIDIA's recommended sampling settings. `--think` appends NVIDIA's reasoning format (`<think> ... </think>` then the answer) and the script splits the two. Build `scripts/explain.py` on top of it; don't invent a different request format or endpoint.

---

## 5. Core rules (non-negotiable)

### Rule 1: Real images are for testing only, never training
- Real camera images are test/evaluation data only. They may also be used for color calibration targets and few-shot examples in Cosmos prompts, with evaluation kept **leave-one-recipe-out**.
- Train on synthetic data (Isaac Sim twin), color math (CIELAB, ΔE2000, mixing models) or physics simulation.
- Never use random train/test splits: neighboring frames are near-duplicates. Split by recipe or by run.

### Rule 2: Never commit data, large files, or API keys
- Never commit datasets, videos (`.mp4`), archives (`.zip`), synthetic images, or model weights.
- Never commit `.env` files or keys. Keys live in a local `.env` (copy `.env.example`), which Git ignores.

### Rule 3: Keep scripts small, one job each, in `scripts/`
- Every script lives in `scripts/` and does **exactly one job** (e.g. `crop_vial.py`, `flush_advisor.py`, `ask_cosmos.py`).
- Each script starts with a docstring saying what it does, what it reads and what it writes.
- Inputs come from `data/` (or `outputs/`); results go to `outputs/`.

### Rule 4: Explain everything simply (the team has no coding experience)
- Plain English, no unexplained jargon. Say *why* a step is needed and *what* it does.
- Always give the exact copy-paste command, and say what output the user should expect.

### Rule 5: Respect the real station
- Observe only. Never change recipes, move or re-aim cameras, or touch tanks; act only with the plant manager's approval.
- Station limits: ≤ 80 mL per vial, ≥ 10 mL of any component used, ≤ 50 mL from T-200, never T-300.
- Never invent business numbers (scrap cost, flush cost); use only numbers CSI or mentors give us.

---

## 6. Coding agents: Gemini and Claude only

We use **two** agents. We do **not** use Codex, GPT-6 Astra, or any other agent.

- **Gemini** (default, free): everyday building, data exploration, baseline, flush model, dashboard, docs.
- **Claude Code** (Claude Pro/Max plan): hard problems (headless Isaac Sim, debugging loops), plans for cards 7, 8 and 10 (`PLAN.md`), and reviews of anything that produces a number for judges (`REVIEW.md`).
- Handoffs go through files (`HANDOFF.md`, `PLAN.md`, `REVIEW.md`), never through memory of a chat. Commit before every switch. Only one agent works on a task at a time.
- If the same error survives three attempts, stop: commit, write `HANDOFF.md`, and switch agents or start a fresh session.

---

## 7. Where things stand (update after every card)

- **Done:** Card 1 (data inventory in RUNBOOK.md; `scripts/show_examples.py` contact sheet), Card 2 (`scripts/align_cameras.py` aligned using `scripts/time_base.py` and MP4 video fallback for vials 25–30; `scripts/plot_time_gaps.py` histogram with 0 vials failing threshold; `scripts/show_aligned_frames.py`; `scripts/find_physical_fills.py`; `scripts/fill_timeline_strip.py`; corrected annotations in `annotations/video5_vial_times_corrected.csv` and `annotations/video5_frame_labels_corrected.csv`), and Card 3 Step 1 (`scripts/crop_vial.py` with verified LOW, HIGH, and BASE patches and glass edge detection across all 30 vials in `outputs/crop_check_all30.png`; `annotations/video5_visual_verdicts.csv`). Cosmos template `scripts/ask_cosmos.py` added.
- **Time base rule:** Label `start_s` and `end_s` in `video5_vial_recipes.csv` are in MP4 playback seconds (30.0 fps container rate). Still-image file timestamps are in real wall-clock time (camera recorded at ~24.676 fps). Always convert between them using `scripts/time_base.py` (`mp4_to_real()`, `real_to_mp4()`). Never use `data/.../video5_frame_labels.csv` for vial numbers; use `annotations/video5_vial_times_corrected.csv` or `annotations/video5_frame_labels_corrected.csv`.
- **Next:** Card 3, step 2 (baseline score: ΔE2000 of each vial to its recipe's clean 3rd vial, graded against the human answer key in `annotations/video5_visual_verdicts.csv`, thresholds fixed in advance or chosen leave-one-recipe-out). Then **Card 3b** (in-context Cosmos check on the same vials) and the **transitions/metadata gap list** for the organizers (`docs/organizer-feedback.md`). Cards 7–8 only if needed after Card 3b.
- **The story so far, in plain English with the reasons:** `docs/PROGRESS.md`. After finishing any card, add a section there (what we did, what we found, why we did it that way) and update this list.

---

## 8. Repository layout

```text
├── GEMINI.md            # This file: project memory for Gemini (and Claude, via CLAUDE.md)
├── CLAUDE.md            # Claude Code's memory file; imports GEMINI.md
├── README.md            # Organizers' event info + our project summary
├── RUNBOOK.md           # Dataset inventory and every command that works
├── requirements.txt     # Python packages for the laptop environment
├── .env.example         # Template for .env (copy it; never commit .env)
├── docs/
│   ├── organizer-feedback.md # Organizers' feedback on our team plan + what it changes
│   ├── team-plan.md         # Copy of the team plan (Team plan tab of our doc)
│   ├── beginner-playbook.md # Copy of the beginner playbook (task cards + prompts)
│   └── PROGRESS.md          # Plain-English progress log with the reasoning
├── scripts/             # Small, single-purpose Python scripts
├── data/                # Dataset (local only, ignored by Git)
└── outputs/             # Generated charts, tables, logs (local only, ignored by Git)
```

---

## 9. Environment and commands

Python 3.12 virtual environment in `.venv/`, packages from `requirements.txt`.

- **Create it (once):** `python -m venv .venv` then, after activating, `pip install -r requirements.txt`
- **Activate (Windows PowerShell):**
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
  .\.venv\Scripts\Activate.ps1
  ```
- **Activate (Command Prompt):** `.venv\Scripts\activate.bat`
- **Activate (Mac):** `source .venv/bin/activate`

Main packages: `opencv-python` (images/video), `numpy`, `pandas` (tables), `matplotlib` (charts), `scikit-learn`, `colour-science` (CIELAB, ΔE2000), `python-dotenv` (.env), `openai` (the client library Cosmos's API speaks).

---

## 10. Guidelines for AI assistants

- Before starting, check which task card the user is on (docs/beginner-playbook.md) and what is done (section 7 and docs/PROGRESS.md).
- Reference files by relative path (e.g. `scripts/align_cameras.py`).
- Run your code before presenting results. If something fails, explain it simply and fix it.
- Never accept or present a number you can't explain; say what could make it wrong.
- After a step works: add its command to RUNBOOK.md, add a plain-English entry to docs/PROGRESS.md, then commit with a clear message.
- Keep explanations beginner-friendly, encouraging and actionable.

---

## Full reference (imported)

@./docs/organizer-feedback.md
@./docs/team-plan.md
@./docs/beginner-playbook.md
@./docs/PROGRESS.md

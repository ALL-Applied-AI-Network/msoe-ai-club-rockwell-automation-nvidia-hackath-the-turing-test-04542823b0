# Progress so far, in plain English

This is our team's lab notebook: what we did, what we found, and **why we did it that way**. It is written for teammates with no coding background and for judges who ask "why?". Add a section every time a task card is finished (newest work at the bottom of "What we did").

*Last updated: Oct 13, 2026 (Cards 1 and 2 done; Cosmos groundwork in place).*

---

## The big picture in one minute

A mixing station fills small vials with colored liquid. Three tanks (clear, orange, blue) all pour through **one shared pipe and one nozzle**. After each fill, a little liquid stays in that pipe. When the recipe changes, that leftover mixes into the first vial of the new recipe. Our clearest example: an orange recipe (Recipe 6) was followed by a blue one (Recipe 7), and the first blue vial came out **green**.

The plant's current camera check only asks "is this a color I know?" A green vial might pass. It never asks "is this the color **this recipe** should be?", never says why, and never warns before it happens. Our project, **Carryover Copilot**, does all three: warns before risky recipe changes, checks each vial against its own recipe, and explains the cause in plain words.

---

## What we did

### Step 0 · Set up a safe workspace

**What:** a private Python environment (`.venv`), a `.gitignore` that keeps data, videos, model files and keys out of GitHub, and a project memory file (`GEMINI.md`) that every AI agent reads before it starts.

**Why:**
- **Reproducibility.** Science only counts if someone else can repeat it. A fixed list of packages (`requirements.txt`) means a teammate's laptop gives the same numbers as yours.
- **Keeping the test honest.** The dataset stays out of GitHub because it is large, it isn't ours to republish, and because real images are our *exam*, not our *study material* (see "Decisions" below).
- **Agents forget.** Each new AI session starts blank. Writing the goal and rules in one file keeps every session, Gemini or Claude, pointed the same way.

### Card 1 · Explore the data (done)

**What:** a full inventory of the dataset (written in `RUNBOOK.md`) and a contact sheet: a grid of 12 sample frames from the `vial_fill` camera, each labeled with its recipe and time (`scripts/show_examples.py` → `outputs/vial_fill_examples.png`).

**What we found:**
- **Three cameras** watch the line: `tank_level` (the supply tanks), `vial_fill` (the vial being filled) and `cap_seal` (the finished vial being capped).
- **4,650 still images and 15 videos** in total. Images are 640 × 480 pixels. Videos run at 30 frames per second; still images were saved about **every 2 seconds**.
- **Only video 5 has answers (labels):** 30 vials, 10 recipes, 3 vials per recipe, with the exact start and end time of every fill and the milliliters drawn from each tank. Videos 1–4 have no labels.
- The cameras don't all have the same number of images (`cap_seal` has 1,181, the other two about 1,734), so they did **not** all save a picture at the same moments.

**Why we did it this way:**
- **Look before you measure.** Every later number depends on knowing what the files really contain. A contact sheet lets a human catch problems a script would miss: glare, a blocked view, a mislabeled frame.
- **The labels shaped our whole test plan.** With only 30 labeled vials, we can't afford to waste any on training, and we must test carefully (leave-one-recipe-out, below).
- **The recipe layout is a natural experiment.** Each recipe was run 3 times in a row. The **1st vial** after a change is the one at risk of carryover; the **3rd vial** has had two fills to flush the pipe, so it is our best "clean" example of that recipe's true color. Comparing 1st vs 3rd is like comparing a treated group with a control group, built into the data for free.

### Card 2 · Line up the three cameras (scripts done; results to record)

**What:** for each of the 30 labeled vials, we found the moment its fill **ended** and picked the closest picture from each camera (`scripts/align_cameras.py` → `outputs/aligned_camera_frames.csv`). Then we checked how far apart in time those pictures are (`scripts/plot_time_gaps.py` → `outputs/time_gaps_histogram.png`).

**How it works, in plain words:**
1. Every image's file name contains the exact time it was taken, down to the microsecond (e.g. `vial_fill_20260923_194711_630429.jpg` = 19:47:11.630429).
2. The label file says how many seconds into video 5 each frame was taken. Subtracting gives the clock time when video 5 started.
3. Video start + a vial's "fill end" seconds = the clock time that vial finished filling.
4. For each camera, pick the picture whose time is closest to that moment, and record the gap in seconds (negative = picture taken before the fill ended, positive = after).

**Why we did it this way:**
- **Three views of one event.** The tank camera can confirm how much liquid left each tank, the fill camera shows the color as it is poured, and the cap/seal camera shows the finished vial. Lining them up in time lets us follow one vial across all three.
- **Why the end of the fill?** The color only means something once all the liquids are in and mixed. A picture taken mid-pour shows a half-made recipe (for example, only the orange that pours first), which would look like an error when it isn't.
- **Why a 2-second limit?** Pictures were saved about every 2 seconds, so the closest picture should never be more than about 1 second away (half the spacing). A gap larger than 2 seconds means a picture is missing or a camera clock is off, and that vial's measurement can't be trusted.
- **Why look at the sign of the gap, not just its size?** Random gaps scattered around zero are normal. If one camera's gaps are *all* positive or *all* negative, its clock is shifted, a systematic error that would quietly bias every measurement from it.

**Fix made on Oct 13:** the histogram now checks all three cameras instead of assuming they match. On video 5 they did match exactly: all three cameras were triggered at the same moments, so their gaps are identical. The check stays as a safeguard in case a camera drops frames on another run.

**Results recorded on our data (30 vials inspected):**
- **Gap statistics for each camera:**
  - `cap_seal`: min `-0.961 s`, max `+0.984 s`, mean `-0.000 s` (max absolute gap `0.984 s`, mean absolute gap `0.551 s`).
  - `tank_level`: min `-0.961 s`, max `+0.984 s`, mean `-0.000 s` (max absolute gap `0.984 s`, mean absolute gap `0.551 s`).
  - `vial_fill`: min `-0.961 s`, max `+0.984 s`, mean `-0.000 s` (max absolute gap `0.984 s`, mean absolute gap `0.551 s`).
- **Clock offset check:** None of the cameras has gaps of all one sign. Gaps are evenly distributed on both sides of zero (`-0.961 s` to `+0.984 s`) with mean `-0.000 s`, so there is no systematic clock offset.
- **Eye check:** the three file names for each vial carry the same timestamp. Opening vials 1, 7 and 20 in `outputs/aligned_check.png` confirmed the three cameras captured the exact same moment, but `cap_seal` shows earlier vials (or an empty rack for vial 1) because finished vials travel downstream to that station.
- **Lesson for Card 3:** about half the nearest frames were taken up to ~1 s before the fill ended, when liquid may still be pouring. Card 3 uses the first frame after each fill’s end time, not the nearest one.

**An open question this raised:** at the moment a fill ends, the `cap_seal` camera is most likely looking at a *different* vial (the finished vial travels to the cap/seal station afterwards). So "same moment" is not the same as "same vial" for that camera. To follow one vial, we will need the travel delay between stations. Card 3 doesn't need it (it only uses `vial_fill`), but the dashboard and live demo will.

### Label check · Physical inspection of video 5 frames

**What:** we inspected the actual still frames from the `vial_fill` camera for all 30 labeled vials across video 5 to verify whether the fill timings and liquid volumes in `video5_vial_recipes.csv` and `video5_frame_labels.csv` match what appears on camera (`scripts/last_frame_per_vial.py` → `outputs/last_frame_per_vial.png` and `outputs/last_frame_per_vial.csv`).

**What we found (facts visible directly in the images):**
- **Fill timing discrepancy:** The physical dispenses do not begin or end at the times recorded in `video5_vial_recipes.csv`. For example, for labeled vial 7, liquid starts pouring out of the nozzle into the vial around 271.0 s, whereas the recipe table lists `start_s = 284.7 s`. Furthermore, labeled vial 7 departs the station under conveyor motion around 301.2 s, whereas the recipe table lists `end_s = 308.0 s` (the station is completely empty from 303.2 s to 307.2 s, even though `video5_frame_labels.csv` labels those frames as `vial = 7, in_fill = 1`).
- **Liquid height comparison for vials 4–9 (measured in pixels from the bottom inside curve of the vial at y ≈ 392 to the liquid meniscus):**
  - **Vial 4 (190.6 s):** ~27 px (stream actively dispensing).
  - **Vial 5 (240.9 s):** ~27 px (stream actively dispensing).
  - **Vial 6 (246.9 s, Recipe 6, 40 mL):** ~102 px (meniscus at y ≈ 290).
  - **Labeled Vial 7 (299.2 s, Recipe 7 labeled, 70 mL expected):** ~102 px (meniscus at y ≈ 290). The liquid height in labeled vial 7 matches Vial 6 (40 mL), not the 70 mL fill height.
  - **Labeled Vial 8 (375.7 s, Recipe 7 labeled):** ~178 px (meniscus at y ≈ 214).
  - **Labeled Vial 9 (423.9 s, Recipe 7 labeled):** ~178 px (meniscus at y ≈ 214).
- **Color observation across vials 6–9:**
  - **Vial 6 (246.9 s):** orange/amber liquid.
  - **Labeled Vial 7 (299.2 s):** orange/amber liquid. No blue liquid or blue stream is visible in any frame while this vial is parked.
  - **Labeled Vial 8 (375.7 s):** the first labeled vial where blue appears. A blue stream is visible pouring from the nozzle into the vial from ~355.5 s to ~371.6 s, mixing with orange liquid sitting in the base to produce dark green/muddy liquid.
  - **Labeled Vial 9 (423.9 s):** contains clean blue liquid throughout.

### Cosmos groundwork (Oct 13)

**What:** `scripts/ask_cosmos.py`, a small tested script that sends pictures (or a short video) and a question to NVIDIA's **Cosmos 3 Nano Reasoner** and prints its answer, plus step-by-step instructions in `RUNBOOK.md` for running Cosmos on a rented Brev GPU.

**Why:**
- The Cosmos page on build.nvidia.com now offers a browser playground and a "run it yourself" container, but no ready-made Python example. We took the request format straight from NVIDIA's official Cosmos 3 cookbook, so we aren't guessing.
- Running our own copy (about 17 GB of GPU memory) on a Brev L40S means no rate limits during experiments and a demo we control.
- Pictures go **before** the question in each request, and we use NVIDIA's recommended settings, because that is how the model was trained to read requests.
- We tested the script against a stand-in server to confirm it sends exactly the format NVIDIA documents. It still needs one real run against Cosmos.

---

## Decisions and the science behind them

| Decision | Why |
| :--- | :--- |
| **Real images are for testing only; we train on Isaac Sim's synthetic images** | If a model studies the exam questions, its score means nothing. Keeping real vials as a never-seen test is the only way our accuracy number is honest. It also mirrors real life: a plant has to set up the check *before* a new recipe ever runs. The gap between simulated and real pictures ("sim-to-real gap") is a known problem, which is why we calibrate the twin's colors against real clean vials first. |
| **Test with "leave-one-recipe-out", never a random split** | Neighboring frames of the same vial are near-copies. A random split puts copies in both training and testing, so the model looks great by memorizing. Hiding a whole recipe at a time proves it works on a recipe it has never seen. |
| **Measure color in CIELAB and compare with ΔE2000, not raw RGB** | RGB is how screens store color, not how eyes see it: equal RGB steps can look very different. CIELAB is designed so equal distances look equally different, and ΔE2000 is the industry formula for "how different do two colors look". A ΔE of about 2 is the smallest difference most people notice, which gives our thresholds real meaning. |
| **Model dye amounts first, then convert to color** | Dyes absorb light; they don't add up like paint on a screen. By the Beer–Lambert law, absorbance grows in proportion to dye concentration, while the light that gets through falls off exponentially. That is why a drop of orange changes a pale vial a lot and a dark one barely, and why orange plus blue turns green instead of "orange-blue". So we add up dye amounts (orange share, blue share), which *do* add, and only then convert to the color the camera sees with one calibrated map. |
| **Use each recipe's 3rd vial as its clean reference** | By the 3rd fill, two fills have pushed the old mixture out of the pipe, so it is the best real example of that recipe's true color. |
| **Cheap math first, AI only to explain** | Color math is instant, free and gives the same answer every time. Vision-language models like Cosmos are slower and can be confidently wrong, so Cosmos never decides pass/fail; it only explains vials that were already flagged, and we score how often its explanations are right. |
| **Two coding agents: Gemini for everyday work, Claude Code for hard problems and reviews** | None of us codes, so agents write the code and we check it. Gemini is free for routine work; Claude Code handles the hardest parts (headless Isaac Sim, stubborn bugs) and double-checks anything that produces a number for judges. A second model catches mistakes a beginner can't see. We dropped Codex/GPT-6 Astra to keep one simple setup. |

---

## What's next

1. **Card 3, baseline color check:** pick one fixed box around the vial, measure average CIELAB color just after each fill ends, compare each vial with its recipe's 3rd vial using ΔE2000, and report caught first vials and false alarms. This is the number everything later must beat.
2. **Cosmos playground test:** try vial 7 (green) in the browser with and without recipe info, and paste the answers into `RUNBOOK.md`.


## Words used here

- **Carryover:** leftover liquid from the previous recipe ending up in the next vial.
- **CIELAB / ΔE:** a way to describe color the way eyes see it, and the distance between two such colors.
- **Contact sheet:** one image made of many small pictures, for checking by eye.
- **Leave-one-recipe-out:** hide one recipe, build with the other nine, test on the hidden one, repeat for all ten.
- **Synthetic images:** pictures rendered from the 3D digital twin in Isaac Sim, with labels that come for free.
- **NIM:** a ready-made container from NVIDIA that runs a model (here, Cosmos) on our own GPU.

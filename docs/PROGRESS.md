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
- **Lesson for Card 3:** Card 3 measures each vial in the last parked frame from annotations/video5_vial_times_corrected.csv, not from the label times.

**An open question this raised:** at the moment a fill ends, the `cap_seal` camera is most likely looking at a *different* vial (the finished vial travels to the cap/seal station afterwards). So "same moment" is not the same as "same vial" for that camera. To follow one vial, we will need the travel delay between stations. Card 3 doesn't need it (it only uses `vial_fill`), but the dashboard and live demo will.

### Label check · Physical inspection of video 5 frames

**What:** we inspected the actual still frames from the `vial_fill` camera for all labeled vials across video 5 to verify whether the fill timings and liquid volumes in `video5_vial_recipes.csv` and `video5_frame_labels.csv` match what appears on camera (`scripts/find_physical_fills.py` → `outputs/physical_fills.csv`, `outputs/physical_fills_sheet.png`, and `annotations/video5_vial_times_corrected.csv`).

**Usable test set:** fills 1–24 (Recipes 5–12, 8 recipes × 3 vials), with 7 carryover first vials (fills 4, 7, 10, 13, 16, 19, 22); fill 25 is partial; vials 26–30 are not in video 5. Fill 4 (dark) and fill 7 (green) are visible carryover examples.

**What we saw in the images (visual facts):**
- **Total physical fill count:** exactly **25 physical fills** occur in video 5 (not 30). Video 5 ends at 1697.1 s while Fill 25 is actively pouring. Fills for rows 26–30 never occur in this video (video duration in `videos.csv` is 1698 s; last frame in `video5_frame_labels.csv` is at 1697.142 s with `in_fill = 0`).
- **Stationary intervals:** out of 27 stationary periods between conveyor movements, exactly 2 are empty conveyor periods without a vial parked under the nozzle (305.2 s–321.3 s and 1658.9 s–1667.0 s; background std < 7.0), and 25 contain a parked vial (std > 40.0).
- **Physical fill heights and measured CIELAB colors (raw unrounded values from each image):**
  - Fills 1–3 (Recipe 5, 30 mL target): base y in [399.5, 400.5], meniscus y in [310.5, 320.5], heights 80.0–90.0 px (~2.67–3.00 px/mL). Measured Lab: Fill 1 (9.8, -9.4, 3.0), Fill 2 (5.1, -2.8, 0.0), Fill 3 (7.3, -1.4, 0.9).
  - Fills 4–6 (Recipe 6, 40 mL target): base y = 400.5, meniscus y in [291.5, 294.5], heights 106.0–109.0 px (~2.65–2.72 px/mL). Measured Lab: Fill 4 (4.5, -1.0, 0.8 — very dark carryover from Recipe 5), Fill 5 (8.4, 6.6, 7.9), Fill 6 (12.4, 13.7, 14.4).
  - Fills 7–9 (Recipe 7, 70 mL target): base y in [399.5, 400.5], meniscus y in [215.5, 219.5], heights 181.0–184.0 px (~2.59–2.63 px/mL). Measured Lab: Fill 7 (11.9, -10.8, 3.0 — dark green carryover), Fill 8 (26.4, -5.3, -24.0 — negative b* blue), Fill 9 (24.4, -4.7, -23.4 — clean blue reference).
  - Fills 10–12 (Recipe 8, 60 mL target): base y in [399.5, 400.5], meniscus y in [238.5, 239.5], heights 161.0–162.0 px (~2.68–2.70 px/mL). Measured Lab: (6.0–8.4, -7.0 to -3.1, -1.5 to 3.5).
  - Fills 13–15 (Recipe 9, 80 mL target): base y in [399.5, 400.5], meniscus y in [180.5, 191.5], heights 209.0–220.0 px (~2.61–2.75 px/mL). Measured Lab: (11.6–14.9, -4.8 to -4.3, 8.9–14.0).
  - Fills 16–18 (Recipe 10, 75 mL target): base y in [395.5, 400.5], meniscus y in [195.5, 197.5], heights 200.0–204.0 px (~2.67–2.72 px/mL). Measured Lab: (10.5–21.6, -8.7 to -6.5, 5.3–20.1).
  - Fills 19–21 (Recipe 11, 70 mL target): base y in [399.5, 400.5], meniscus y in [209.5, 220.5], heights 179.0–190.0 px (~2.56–2.71 px/mL). Measured Lab: (13.6–15.5, -13.2 to -9.4, -7.4 to 0.6).
  - Fills 22–24 (Recipe 12, 70 mL target): base y = 400.5, meniscus y in [209.5, 212.5], heights 188.0–191.0 px (~2.69–2.73 px/mL). Measured Lab: Fill 22 (8.9, -3.9, 6.0), Fill 23 (18.3, 21.5, 24.6), Fill 24 (20.3, 25.3, 28.5).
  - Fill 25 (Recipe 13, 70 mL target): base y = 400.5, meniscus y = 337.5, height = 63.0 px (partial fill interrupted mid-pour when video cut off at 1697.1 s). Measured Lab: (13.0, 11.6, 13.3).
- **Cumulative timing drift (not a static 1-vial shift):**
  - The gap between recorded `start_s` and physical pour start is **cumulative**: it grows by ~10–18 seconds on nearly every vial cycle.
  - At Row 1, drift is `-1.6 s`. At Row 2, `-11.7 s`. At Row 3, `-22.5 s`.
  - At Row 4, the label generator recorded a window at 138.2 s–161.3 s where no dispense occurred (carrier was moving and settling), while the physical pour started at 172.5 s (drift = `-34.3 s`).
  - As the run progresses, physical cycle times (~60–85 s including conveyor moves and settling) exceed the scheduled label cycle times (~45–65 s).
  - The drift grows steadily: `-64.8 s` at Row 7 (about 1 cycle early), `-150.8 s` at Row 14 (about 2 cycles early), `-242.4 s` at Row 21 (about 3 cycles early), reaching `-300.6 s` by Row 25 (about 4 cycles early).
  - Because of this ~300 s cumulative drift, the scheduled table reached Row 30 (`start_s = 1671.3 s`) while the physical line had only reached Fill 25 when the camera stopped at 1697.1 s.

**What it means (interpretation):**
- The dataset labels reflect an idealized open-loop schedule rather than real-time camera trigger timestamps. The schedule accumulated ~10–18 s of lag per vial cycle against the real physical conveyor.
- Using label `start_s` / `end_s` causes algorithms to inspect empty conveyor gaps or previous vials.
- Corrected ground truth is codified in `annotations/video5_vial_times_corrected.csv` (vial, recipe, volume, physical fill number, pour start/end, raw coordinates, measured Lab, drift, and notes) for honest benchmarking in Card 3.

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

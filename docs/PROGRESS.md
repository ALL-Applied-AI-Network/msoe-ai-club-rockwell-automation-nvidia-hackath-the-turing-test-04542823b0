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

**Results recorded on our data (all 30 vials aligned):**
- **Gap statistics for each camera across all 30 vials:**
  - `cap_seal`, `tank_level`, `vial_fill`: min `-0.927 s`, max `+0.972 s`, mean `+0.070 s` (max absolute gap `0.972 s`, mean absolute gap `0.427 s`).
- **Breakdown by source:**
  - **Vials 1–24 (`source = still`):** min `-0.927 s`, max `+0.972 s`, mean `+0.089 s` (mean absolute gap `0.532 s`).
  - **Vials 25–30 (`source = mp4`):** extracted from Video 5 MP4s (still capture stopped at 20:15:27, but video recorded through 20:21:35). Time gaps are within `±0.015 s` (mean absolute gap `0.007 s`).
- **Clock offset check:** Gaps are evenly distributed on both sides of zero (`-0.927 s` to `+0.972 s`) with mean `+0.070 s`, confirming no systematic clock offset between camera hardware clocks.
- **2-second check:** **0 vials failed.** Every camera has an aligned frame within 2.0 s across all 30 vials (max absolute gap is `0.972 s`).
- **Eye check:** the three file names for each vial carry the same timestamp. Opening vials 1, 7 and 20 in `outputs/aligned_check.png` confirmed the three cameras captured the exact same moment, but `cap_seal` shows earlier vials (or an empty rack for vial 1) because finished vials travel downstream to that station.
- **Lesson for Card 3:** Card 3 measures each vial in the last parked frame directly from `vial_fill_video_5.mp4` using `annotations/video5_vial_times_corrected.csv`, giving us access to all 30 vials with consistent lighting and encoding.

**An open question this raised:** at the moment a fill ends, the `cap_seal` camera is most likely looking at a *different* vial (the finished vial travels to the cap/seal station afterwards). So "same moment" is not the same as "same vial" for that camera. To follow one vial, we will need the travel delay between stations. Card 3 doesn't need it (it only uses `vial_fill`), but the dashboard and live demo will.

### Label check · Physical inspection of video 5 and the time-base mismatch

**What:** we inspected the frames of `vial_fill_video_5.mp4` and the still images to resolve discrepancies between recorded fill times in `video5_vial_recipes.csv` and what appears on camera (`outputs/mp4_label_check.png`, `outputs/mp4_fills_sheet.png`, and `annotations/video5_vial_times_corrected.csv`).

**Usable test set:** **all 30 vials** (10 recipes × 3 vials each, Recipes 5–14), with 9 carryover first vials (vials 4, 7, 10, 13, 16, 19, 22, 25, 28) and 10 clean 3rd vials. Vial 4 (dark) and Vial 7 (green) are classic carryover examples.

**The time-base mismatch (why still-image times diverge from video seconds):**
- When comparing still images (`vial_fill/images/`) to the label times in `video5_vial_recipes.csv`, the timestamps appeared to diverge by ~10–18 seconds per vial cycle, and the still-image directory stopped during Vial 25.
- The machine operated normally and on time. Instead, there was an underlying **time-base mismatch between MP4 playback time and real wall-clock time**:
  1. `vial_fill_video_5.mp4` has 50,942 frames and is packaged with a container header declaring **30.0 fps** (total duration 1698.067 s, or 28 min 18 s).
  2. The burned-in camera clock on the video reveals that real elapsed time covers 19:47:10.547 to 20:21:35.201 (2064.654 real clock seconds).
  3. The camera captured frames at **~24.676 fps** in real time, but the file plays at **30.0 fps**. Therefore, the MP4 video plays **~1.2158× faster than real time**:
     $$\text{real\_elapsed\_s} = 1.215771 \times \text{mp4\_s} + 0.000027 \quad (\text{max error } 6.6\text{ ms})$$
  4. The label file `video5_vial_recipes.csv` was created in **MP4 playback seconds** ($\text{start\_s} = \text{start\_frame} / 30.0$).
  5. The still images in `vial_fill/images/` were saved according to the **real system clock**.
  6. Comparing real-clock still frames against MP4 playback seconds produced an artificial difference of $(1.215771 - 1.0) \approx 0.2158$ s per MP4 second (about 13 s across each 60 s vial cycle).
  7. The still image capture stopped after 1697.1 real seconds (20:15:27 clock time), which corresponds to only 1395 s of MP4 playback (Vial 25). The MP4 video kept running through 20:21:35 clock time (1698 s of MP4 playback), successfully capturing all 30 vials.

**What we saw in the MP4 video (visual facts):**
- **Label row 7 is indeed the green vial:** In `outputs/mp4_label_check.png`, sampling the middle of the label windows directly in MP4 time shows:
  - Row 6 (233.7 s, Recipe 6): pale orange liquid filling the vial.
  - Row 7 (296.3 s, Recipe 7): dark olive green liquid actively filling the vial (blue dye pouring from the nozzle into orange residue in the vial).
  - Row 8 (348.9 s, Recipe 7): clean pale blue liquid filling the vial.
- **All 30 vials are fully present:** All 30 vials complete their fill and pause parked under the nozzle before advancing downstream.
- **Consistent liquid heights and CIELAB colors across all 30 vials:** In `outputs/mp4_fills_sheet.png`, every vial's last parked frame was extracted and measured using a consistent 20×20 patch centered in the liquid:
  - Vials 1–3 (Recipe 5, 30 mL): heights 79.0–83.0 px; base y ~399.5–402.5, meniscus y ~319.5–321.5. Measured Lab: (4.5–9.1, -9.8 to -1.9, 0.5–3.7).
  - Vials 4–6 (Recipe 6, 40 mL): heights 103.0–107.0 px; meniscus y ~292.5–296.5. Measured Lab: Vial 4 is dark carryover (4.1, -1.2, 1.7); Vials 5–6 are pale orange (7.8–13.0, 5.6–15.1, 8.2–16.2).
  - Vials 7–9 (Recipe 7, 70 mL): heights 181.0–194.0 px; meniscus y ~205.5–222.5. Measured Lab: Vial 7 is green carryover (14.1, -13.4, 4.6); Vials 8–9 are clean blue (21.1–28.7, -6.3 to -3.0, -24.6 to -22.9).
  - Vials 10–12 (Recipe 8, 60 mL): heights 161.0–163.0 px; meniscus y ~238.5–239.5. Measured Lab: (5.4–7.1, -7.4 to -3.1, -0.2 to 3.8).
  - Vials 13–15 (Recipe 9, 80 mL): heights 210.0–214.0 px; meniscus y ~187.5–191.5. Measured Lab: (10.7–13.8, -6.1 to -4.6, 8.7–14.3).
  - Vials 16–18 (Recipe 10, 75 mL): heights 200.0–204.0 px; meniscus y ~195.5–197.5. Measured Lab: (9.6–21.0, -9.3 to -7.4, 5.6–20.5).
  - Vials 19–21 (Recipe 11, 70 mL): heights 180.0–194.0 px; meniscus y ~209.5–220.5. Measured Lab: (12.6–14.9, -13.9 to -9.6, -6.6 to 0.9).
  - Vials 22–24 (Recipe 12, 70 mL): heights 175.0–191.0 px; meniscus y ~209.5–223.5. Measured Lab: Vial 22 carryover (8.0, -3.7, 5.5); Vials 23–24 orange (15.2–17.6, 19.5–21.2, 20.6–24.7).
  - Vials 25–27 (Recipe 13, 70 mL): heights 184.0–193.0 px; meniscus y ~205.5–216.5. Measured Lab: (11.5–21.5, 12.0–28.2, 15.4–30.9).
  - Vials 28–30 (Recipe 14, 70 mL): heights 184.0–195.0 px; meniscus y ~207.5–215.5. Measured Lab: (11.5–39.1, -16.7 to 0.6, 1.5–13.9).

**What it means (interpretation):**
- The original labels in `video5_vial_recipes.csv` are correct when applied directly to `vial_fill_video_5.mp4`.
- For Card 3, we should evaluate color and fill height directly from `vial_fill_video_5.mp4` rather than still images, ensuring identical lighting, encoding, and access to the complete 30-vial test set.
- All corrected metadata, MP4 timestamps, real clock times, liquid coordinates, and measured CIELAB colors are codified in `annotations/video5_vial_times_corrected.csv`.

### Card 3, step 1 · Fixed measurement patches and edge safety check

**What:** We selected and verified three fixed measurement patches on the vial using the last parked MP4 frame of all 30 vials (`scripts/crop_vial.py` → `outputs/crop_check.png` and `outputs/crop_check_all30.png`).
- **LOW patch (`x: [302, 318], y: [352, 372]`):** In front of the dark conveyor backdrop. Submerged in liquid across all 30 vials (including 30 mL vials, whose meniscus is at $y \approx 320.5$).
- **HIGH patch (`x: [302, 318], y: [268, 288]`):** In front of the white paper backdrop. Sits below the black carrier bracket ($y \le 264$) and above the dark border ($y \ge 294$). Counted inside liquid only when the meniscus is at least 5 px above $y=268$; this is true for all 24 vials $\ge 60$ mL (meniscus $\le 239.5$). Empty for 30 mL and 40 mL vials.
- **BASE patch (`x: [304, 316], y: [389, 395]`):** Inside the colored glow of the thick glass vial bottom, clearing the carrier metal block ($y \approx 396$–$403$) and hex screws ($x \le 275, x \ge 345$).
- **Edge detection & safety check:** Detects the inner glass walls across all 30 vials ($x \in [271, 293]$ on left, $[325, 341]$ on right). Every patch is well within the liquid with **0 flagged vials** (no contact with glass walls, meniscus lines, carrier bracket, backdrop dark strip, screws, or glint reflections).
- **Color conversion:** Patch color is extracted as the spatial median sRGB, then converted to CIELAB (D65) using `colour-science`.

### Card 3, step 2 · Baseline score

**What:** We ran `scripts/baseline_check.py` to calculate CIELAB color distances ($\Delta$E2000 via `colour-science`) for all 30 vials against each recipe's 3rd vial as its clean reference, across the LOW, HIGH, and BASE patches from `scripts/crop_vial.py`.

- **Answer key locking:** The answer key was locked in commit `a4eb011` before any score existed. One human judge (`judge_1`) labeled vials by eye from the judging sheet; `judge_1`'s entries for the 3rd vials are ignored because those vials serve as the references themselves. An AI judge was recorded separately in the `ai_judge` column and was not used for scoring. `judge_2` is currently empty.
- **Scoring results on the HIGH patch ($\Delta$E > 5):**

| Answer Key | Vials Scored | Positive / Negative | Caught Off-Vials | False Alarms | Balanced Accuracy | Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Human `judge_1` (unsure = off)** | 16 | 8 Pos / 8 Neg | **8 of 8** (100%) | **0** | **100.0%** | Catches all 8 carryover vials with 0 false alarms. |
| **Human `judge_1` (unsure = fine)** | 16 | 4 Pos / 12 Neg | **4 of 4** (100%) | **4** | **83.3%** | All 4 false alarms are on vials the judge labeled 'unsure' (V7, V10, V16, V29). |
| **Advance Rule (1st = at risk, 2nd = fine)** | 16 | 8 Pos / 8 Neg | **7 of 8** (87.5%) | **1** | **87.5%** | Misses vial 13 ($\Delta$E = 1.98, where judge also said matches); 1 false alarm on vial 29 ($\Delta$E = 6.49, judged 'unsure'). |

- **Threshold selection:** Leave-one-recipe-out (LORO) thresholds gave the same picture. Clean 2nd vials measure $\Delta$E 0.5–2.6 and carryover vials measure 6.5–32.7 on the HIGH patch, which is why the pre-decided threshold $\Delta$E > 5 cleanly separates them and $\Delta$E > 2 does not.
- **Patch comparison & small vial weak spot:** The HIGH patch separates off from fine best, likely because the white backdrop gives clear light transmission and high dynamic range. In contrast, LOW and BASE reach only ~60–70% balanced accuracy, with causes (dark backdrop, glass bottom) likely, not tested. Because 30 mL and 40 mL vials (Recipes 5 and 6) do not reach the HIGH patch, LOW and BASE are the only option for 30/40 mL vials: our main weak spot.
- **Lingering carryover in pale recipes:** The pale-recipe 2nd vials (vials 5 and 29) stay off ($\Delta$E = 10.0 on LOW for vial 5; $\Delta$E = 6.5 on HIGH for vial 29), consistent with leftover color lingering longer in pale recipes (not yet tested).
- **Limitations:** Only one human judge is available so far; only 16 HIGH-scored vials exist in the dataset (8 of 8 caught is consistent with a true catch rate as low as ~63% at standard confidence intervals); each recipe's 3rd vial is assumed clean.

### Organizer feedback on our team plan (Oct 14)

**What they said:** our three goals (warn before risky recipe changes, check each filled vial, explain the cause) are the right focus. They asked us to (1) compare plain color/fill measurements with an in-context Cosmos approach **before** training any model, (2) ground explanations in the current and previous recipes and the camera evidence, (3) keep "the twin makes realistic-looking variations" separate from "the twin simulates carryover", since it has no tanks and only approximate liquid color, and (4) instead of requesting data that's already supplied, list which transitions and metadata are still missing. Full text: `docs/organizer-feedback.md`.

**What we changed and why:**
- **Added Card 3b, a Cosmos check, before any training.** If simple color math plus Cosmos, shown a reference vial and the recipes, already catches the off vials, training a model on synthetic images adds cost and risk for no gain. Testing the cheaper options first is how engineers avoid over-building.
- **Explanations must cite evidence:** the intended recipe, the previous recipe and what the camera measured. An explanation that only says "probably carryover" can't be checked; one that names the previous recipe and the measured color shift can.
- **The twin is for appearance, not carryover.** Renders can vary lighting, glare, fill height and color, which helps a model cope with real-world variety. But carryover happens in pipes and tanks the twin doesn't model, so its strength comes only from the real recipe changes in video 5.
- **Data gap list instead of a data request.** Video 5 has exactly 9 recipe changes, each seen once. We'll list which risky changes never occur (e.g. blue → orange) and which metadata is missing (the recipe before vial 1, recipe sequences for videos 1–4, tank contents, Teledyne results), and send that list to the organizers.

### Transitions gap list (Oct 19)

**What we built:** `scripts/list_transitions.py` and `annotations/video5_transitions.csv`, analyzing all 9 recipe transitions in Video 5 by volume, dye shares, dye category (`orange`, `blue`, `mixed`, `clear`), strength (`pale` vs `dark`), and hue (`orange-side`, `blue-side`, `balanced`, `clear`), paired with baseline first-vial $\Delta$E and `judge_1` verdicts.

- **Main gap in one sentence:** Video 5 runs in a single direction and never tests carryover into a pale recipe from a blue-side recipe (the expected worst case for color distortion), never tests pure blue into pure orange, and includes no transitions into or out of a clear-only recipe to verify flush effectiveness.
- **The open question (12→13 vs 8→9):** Transition 12→13 kept the same hue family and was still clearly off ($\Delta$E = 10.4, judged off), while 8→9 (balanced to balanced, darker) was the only first vial that looked clean ($\Delta$E = 2.0, judged matches). With only a single example of each same-hue change, we cannot tell whether 8→9 escaped carryover because of recipient volume, saturation, or station variance; more same-hue changes would tell us.

### Card 4, step 1 · Color map g (Oct 19)

**What we did:** In `scripts/fit_color_map.py`, we fitted a light-absorption (Beer–Lambert) map $g$ from recipe dye shares (orange share, blue share) to camera CIELAB color on the 8 tall recipes (Recipes 7–14, HIGH patch), converting Lab to linear RGB and optical absorbance $A = -\log_{10}(\text{linear RGB})$ per channel.

- **Fitted model & performance:** Across all 8 recipes, the 9 parameters capture physical complementary absorption ($k_{\text{blue}, R} = +3.22$ and $k_{\text{orange}, B} = +2.67$). However, evaluated under strict leave-one-recipe-out (LORO) cross-validation, the median prediction error is **$\Delta$E 6.3** (mean 8.2), which is too large for the fine-grained $\Delta$E 2 / 5 risk thresholds.
- **Why it misses:** It fails worst when it must extrapolate—specifically Recipes 7 ($\Delta$E 11.1) and 14 ($\Delta$E 21.3), which are the only pure-blue recipes in the tall set, while there is no pure-orange tall recipe available. Furthermore, two fitted coefficients are negative (e.g. $k_{\text{orange}, R} = -0.63$ and $k_{\text{blue}, B} = -0.44$), which pure physical light absorption does not allow. This shows that the camera system is not behaving as a pure transmission sensor, likely influenced by its dark floor and automatic exposure.
- **Decision:** For known recipes where clean reference vials have been measured, use their actual measured patch colors directly rather than predicting them via $g$. Reserve $g$ only for predicting brand-new, unseen recipes in a queue, and explicitly display its expected uncertainty.

### Card 4, step 2 · Why a simple leftover model didn't fit (Oct 19)

**What we did:** In `scripts/fit_residue.py` and `scripts/check_measurements.py`, we attempted to fit a physical residue volume $V_r$ (leftover liquid in the shared pipe blending into the recipient vial) using measured clean 3rd-vial colors and absorbance mixing across the 7 tall transitions (7→8 through 13→14, HIGH patch), and sanity-checked our camera measurements.

- **Exposure is stable:** Measuring a white paper backdrop patch across all 30 frames confirmed $L^*$ is strictly between 61.0 and 62.7 (spread 1.71, 0 outliers $> 2$ from median 61.9), proving our color measurements are not artifacts of camera drift or auto-exposure swings.
- **The one-number leftover model failed:** The model assumes the first vial equals the new recipe plus a fixed volume $V_r$ of the previous recipe. Under optimization, the best $V_r$ hit the 40.0 mL search ceiling in 5 of 7 transitions (and 37.9 mL in a 6th), and 3 transitions still missed by $\Delta$E > 10. In transitions 9→10, 10→11, and 13→14, the first vial's lightness $L^*$ is within $\approx 1$ of the previous recipe's color, which cannot physically occur from a small pipe residue volume.
- **Subtractive dye absorption vs "darker than both":** In subtractive mixing, orange and blue dyes absorb complementary spectra, so a blend naturally darkens compared to single-dye components. Transitions 9→10, 12→13, and 13→14 show minor lightness dips ($\le 1.4\ L^*$), well within sensor and measurement noise. Transition 11→12 (5 $L^*$ darker) is a blue-side $\to$ orange-side shift where significant darkening is physically expected.
- **Unmixed / layered appearance on camera:** Crop strips (`outputs/card4/first_vial_strips.png`) show clear visual stratification and layering in several first vials (e.g. vials 4 and 28). If liquid inside the vial is not fully mixed at the moment of camera capture, a single central patch cannot represent the entire vial's composition.
- **Decision:** Do not report an artificial physical residue volume $V_r$. Instead, predict carryover risk directly from the measured recipe-to-recipe color gap.

### Card 4, step 3 · Measured risk model (Oct 19)

**What we built:** In `scripts/fit_risk_model.py`, we developed a direct measured risk model predicting carryover error from the recipe-to-recipe color distance:
$$\widehat{\Delta E}_{\text{first vial}} = \alpha \times \Delta E_{\text{recipe gap}} \quad (\text{without intercept})$$
where $\Delta E_{\text{recipe gap}}$ is the $\Delta E2000$ between the two recipes' clean 3rd vials, and $\alpha$ is fitted under leave-one-transition-out (LOTO) cross-validation (about 0.69 on the HIGH patch across 7 tall transitions, and 0.67 on the LOW patch across all 9 transitions).

- **Ranks changes in the right order:** The model strongly ranks recipe transitions by true carryover risk, with Spearman rank correlation $\rho = 0.786$ ($p = 0.036$) on the HIGH patch and $\rho = 0.817$ ($p = 0.007$) on the LOW patch. In both patches, 8→9 is correctly predicted as the safest transition with the lowest error, while the high-risk shifts 13→14, 11→12, and 6→7 are all correctly flagged RED.
- **Risk lights vs 'Always RED' baseline:**
  - On the LOW patch, LOTO risk lights match the measured light in **8 of 9 transitions (88.9%)**, compared to only **5 of 9 (55.6%)** for a naive "always RED" baseline.
  - On the HIGH patch, LOTO matches **6 of 7 (85.7%)**, but so does "always RED", because 6 of the 7 tall transitions in Video 5 were indeed RED. The only LOTO mismatch on HIGH is one false amber (8→9 predicted amber vs measured green), but 8→9 is still recognized as lowest error.
- **Why the advisor shows lights, not exact numbers:** Predicted $\Delta E$ values are rough estimates (individual LOTO errors deviate by up to $\sim 13\ \Delta E$ on HIGH, e.g. on 7→8 and 13→14). Therefore, the flush advisor outputs the traffic light (GREEN, AMBER, RED) and recommended operator action rather than pretending the numerical $\Delta E$ is exact.
- **Physical meaning of $\alpha$:** An $\alpha$ of $\approx 0.67\text{--}0.69$ means the first vial's color error is about two-thirds of the whole gap between the recipes, i.e. the first vial looks more like the old recipe than the new one. That is surprisingly large for a small pipe leftover (see step 2) and is an open question for the organizers. (Note: this describes the color position on the camera, not that "two-thirds of the liquid carries over").

### Card 4, step 4 · Flush advisor (Oct 20)

**What we built:** `scripts/flush_advisor.py`, an operator tool that evaluates any queued sequence of recipe IDs before dispensing begins, using clean 3rd-vial reference measurements and the fitted risk model slopes.

- **What it prints:** For every change in the queue, it prints the recipe change, the patch used (HIGH if both recipes are $\ge 60$ mL, else LOW), the recipe color gap $\Delta E$, the risk light (GREEN, AMBER, RED), and the plain-English operator action:
  - GREEN ($< 2\ \Delta E$): `"proceed"`
  - AMBER ($2\text{--}5\ \Delta E$): `"proceed and flag the first vial for inspection"`
  - RED ($> 5\ \Delta E$): `"flush or reorder; a flush needs the plant manager's approval, and its effect isn't measured yet (no flush in our data)"`
- **Playbook test checks:**
  - `6 -> 7`: RED (LOW patch, recipe gap $\Delta E = 30.1$, flags high risk of carryover discoloration).
  - `7 -> 7`: GREEN (HIGH patch, recipe gap $\Delta E = 0.0$, proceeds cleanly).
  - `8 -> 9`: AMBER (HIGH patch, recipe gap $\Delta E = 6.4$, flags for inspection).
- **Conservative reordering advice:** The advisor evaluates all queue permutations (holding the current station state fixed via `--after`). It suggests an alternative order **only** if that order strictly reduces the number of RED changes, or keeps REDs equal while reducing AMBERs. It never suggests a reorder based on tiny numerical score differences, as predicted $\Delta E$ can vary by $\sim 13\ \Delta E$. For example, with queue `7 12 8 --after 6`, it suggests `12 -> 8 -> 7` (reducing RED changes from 3 to 2). When no permutation eliminates a RED change (e.g. `11 12 13 --after 10`), it explicitly advises: `"No order removes a red change; consider a flush (needs the plant manager's approval)."`
- **Flush effects unmeasured:** The tool explicitly reminds the user that a flush requires plant manager approval and that its cleaning effect has not been measured yet, as Video 5 contains no flush sequences.

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
| **Test simple color math and an in-context Cosmos check before training any model** | The organizers asked for it, and it's good practice: the cheapest method that works wins. A trained model is only worth its cost if it clearly beats both simpler options on the same vials and the same answer key. |
| **The digital twin varies appearance; it does not simulate carryover** | The twin has no tanks and only approximate liquid colors, so it can't reproduce how leftover liquid moves through the pipe. We use it for lighting, glare, fill height and color variety, and take the size of carryover only from real recipe changes. |
| **Use each recipe's 3rd vial as its clean reference** | By the 3rd fill, two fills have pushed the old mixture out of the pipe, so it is the best real example of that recipe's true color. |
| **Cheap math first, AI where it earns its place** | Color math is instant, free and gives the same answer every time. Vision-language models like Cosmos are slower and can be confidently wrong, so Card 3b measures how well Cosmos judges vials (given a reference vial and the recipes) against the same answer key before we decide its role. Its explanations are scored too. |
| **Two coding agents: Gemini for everyday work, Claude Code for hard problems and reviews** | None of us codes, so agents write the code and we check it. Gemini is free for routine work; Claude Code handles the hardest parts (headless Isaac Sim, stubborn bugs) and double-checks anything that produces a number for judges. A second model catches mistakes a beginner can't see. We dropped Codex/GPT-6 Astra to keep one simple setup. |

---

## What's next

1. **Human answer key:** one judge so far (`judge_1`); add `judge_2` later and rerun `scripts/baseline_check.py`.
2. **Card 3, step 2, baseline score:** done (HIGH patch at $\Delta$E > 5 catches carryover vials with 0 false alarms when 'unsure' counts as off (4 when it counts as fine); small vials remain weak).
3. **Gap list for the organizers:** done (table in `annotations/video5_transitions.csv` and gap list in `docs/organizer-feedback.md`).
4. **Card 4, flush advisor:** done (`fit_color_map.py`, `fit_residue.py`, `check_measurements.py`, `fit_risk_model.py`, `flush_advisor.py`; risk lights from measured recipe gap; no physical leftover volume reported).
5. **Cosmos playground test:** try vial 7 (green) in the browser with and without recipe info, and paste the answers into `RUNBOOK.md` (no Brev needed).
6. **Card 3b, in-context Cosmos check:** test Cosmos on the same 30 vials against the baseline once Cosmos runs on Brev (organizer feedback).
7. **Decide on training:** start Cards 7-8 (twin-trained model) only if steps 2-6 aren't good enough.

## Words used here

- **Carryover:** leftover liquid from the previous recipe ending up in the next vial.
- **CIELAB / ΔE:** a way to describe color the way eyes see it, and the distance between two such colors.
- **Contact sheet:** one image made of many small pictures, for checking by eye.
- **Leave-one-recipe-out:** hide one recipe, build with the other nine, test on the hidden one, repeat for all ten.
- **Synthetic images:** pictures rendered from the 3D digital twin in Isaac Sim, with labels that come for free.
- **NIM:** a ready-made container from NVIDIA that runs a model (here, Cosmos) on our own GPU.

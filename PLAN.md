# PLAN: Card 7 · Calibrated twin renders for the small vials

Written by Claude Code for Gemini to carry out, **one step per prompt**. Each step says what to ask, how to check it worked, and what to commit. Do the steps in order; don't start a step until the one before it passes its check.

**How to use this file:** on the Brev instance, start `agy` inside `/workspace/project/repo` (after `git pull` or a fresh repo copy) and say *"Read GEMINI.md and PLAN.md. Do Card 7 step N only, then tell me how to check it."* Laptop steps are marked **(laptop)**.

Card 10's remaining step (Cosmos explanations in the dashboard) is at the bottom of this file.

---

## Why Card 7, in one paragraph

Card 3b showed the color check already works on tall vials (8 of 8 caught, 0 false alarms). The one real gap is the **30–40 mL vials** (Recipes 5 and 6), where the liquid never reaches the good HIGH patch and only the weaker LOW patch works. The twin can do exactly what video 5 can't: show the same vial at **any fill height, dye mix, lighting and glare**. Card 7 makes the twin's liquid controllable, calibrates its colors against the real clean vials, and renders a labeled image set for Card 8. The twin varies **appearance only**; it does not simulate carryover (organizer feedback).

## Ideas this plan builds on

- **Blank normalization** (teammate's idea, tested in `scripts/blank_check.py`): measure every liquid patch **relative to the empty vial in the next holder, at the same height**, like a lab blank. On video 5 it caught exactly the same vials as the raw check, and it cancels any even change in brightness. Both the twin and the real camera have that empty neighbour vial in view, so twin and real are compared in this blank-relative space. If the neighbour pocket is empty, use the median blank of the run (`blank_fallback`).
- **The anchored gradient** (same teammate): absorbance relative to the blank grows in a straight line with each dye's amount, starting from zero at the empty vial. Calibrating the twin means matching each dye's strength, a handful of numbers.
- **Automatic calibration loop** (same teammate's "reward and penalty" idea): render, measure the color error against the real vial, correct the dye strengths along the gradient, repeat a few times.
- **Mixing state** (same teammate's "flow" idea): some real first vials look layered (darker at the bottom; `outputs/card4/first_vial_strips.png`). The renders include a controllable "mixing state", from evenly mixed to layered, so a model learns layered vials too.

## Ground rules for every step

- **Real images are calibration targets only.** Only the clean **3rd vials** are used to calibrate. The 1st and 2nd vials are Card 8's test set and are never used here.
- **Where things live on Brev:** `/workspace/project/repo` (our repo copy), `/workspace/project/twin` (twin; never copy it into the repo), `/workspace/project/renders`, `/workspace/project/logs`. No `sudo`, no `docker`, no `tmux`. Isaac Sim's Python is `/isaac-sim/python.sh`; `ACCEPT_EULA=Y` must be set.
- **Long jobs** run with `nohup … > /workspace/project/logs/<job>.log 2>&1 &`, saving each image as soon as it's rendered, so a closed tab loses little.
- **Every render script** appends one line (GPU, job, minutes, images) to `outputs/run_log.csv`, so we can report GPU time per 1,000 images.
- **Never commit from Brev, never run `docker compose down`.** At the end of each session: zip, download, Stop. Commit scripts from the laptop; renders go to `outputs/card7/` on the laptop (ignored by Git) and the team Drive.
- **Stop rule:** if the same error survives 3 attempts, write `HANDOFF.md` and stop; headless Isaac Sim problems go to Claude.
- **Time box:** steps 1–5 in one Brev session (about 2 hours); step 6 in a second session.

---

## Step 1 · Find out where the stripes come from (Brev, about 20 min)

> "Read GEMINI.md, PLAN.md and docs/twin-map.md. Card 7 step 1 only. In stations/fill_station/fill_station.usda, find the liquid inside the filling vial: how it's built (one shape or many layers, animated how), and its material. Then render frame 686 from FillCam twice, once with the settings scripts/render_test.py uses and once with 4× more path-tracing samples, to /workspace/project/renders/card7_step1_default.png and card7_step1_more_samples.png. Tell me in plain English what causes the horizontal stripes. Do NOT commit."

**Check:** look at the two images side by side. If the stripes fade with more samples, they are render noise. If they stay, they come from how the liquid is built. Either way, step 3 replaces this liquid.
**Commit:** nothing yet (the explanation goes into `docs/twin-map.md` in step 8).

## Step 2 · Put our measurement patches on the twin's image (Brev, about 20 min)

> "Card 7 step 2 only. Write scripts/measure_patches.py (one job: measure the vial patches in one image; it must run both with /isaac-sim/python.sh on Brev and with the laptop's Python). It measures the median color of the HIGH (x 302–318, y 268–288), LOW (x 302–318, y 352–372), BLANK_HIGH (x 410–426, y 268–288) and BLANK_LOW (x 410–426, y 352–372) patches, and returns the raw Lab color and the blank-normalized color (linear RGB of the patch ÷ linear RGB of the blank at the same height, then × the run's median blank, converted to Lab), exactly as scripts/blank_check.py does. Install colour-science with '/isaac-sim/python.sh -m pip install --user colour-science' if needed (tell me first). Draw the four boxes on card7_step1_more_samples.png and save it as /workspace/project/renders/card7_step2_patches.png. If a box doesn't land on the liquid or on the empty neighbour vial in the twin, find the twin's equivalent position, and report both sets of coordinates. Do NOT commit."

**Check:** in the picture, HIGH and LOW sit inside the filled vial's liquid, and BLANK_HIGH and BLANK_LOW inside the empty neighbour vial, clear of the glass walls. Note any changed coordinates; they go into `docs/twin-map.md` in step 8.
**Commit (laptop, after the session):** `Card 7 step 2: patch measurement shared by twin and real images`

## Step 3 · Our own liquid: controllable color, fill height and mixing (Brev, about 30 min)

> "Card 7 step 3 only. Write scripts/set_liquid.py (one job: set the vial's liquid in the twin and render one image). Hide the twin's animated liquid and put in one smooth liquid column inside the filling vial, with the vial's real inner radius taken from the geometry, so that fill height = volume ÷ (π × inner radius²) for a given mL (10–80 mL). Give it a transparent material whose color comes from light absorption: absorption per color channel = k_orange × orange share + k_blue × blue share, with the 6 k numbers read from outputs/card7/twin_dye_strengths.json (start from the real anchored gradient in outputs/card7/anchored_gradient.csv, copied from the laptop). Add a 'mixing' setting from 0 (evenly mixed) to 1 (layered: darker at the bottom, lighter at the top, changing smoothly with no visible bands). Inputs: --orange, --blue, --ml, --mixing, --out. Render three tests: Recipe 7 (orange 0, blue 0.714, 70 mL), Recipe 6 (orange 0.25, blue 0, 40 mL) and Recipe 7 with mixing 0.7. Do NOT commit."

**Check:** no stripes in any of the three. The 70 mL and 40 mL levels look like the real vials 9 and 6 (compare with `python scripts/replay_feed.py --vial 9 --save ...` on the laptop). Changing the shares visibly changes the color, and the mixing image is darker at the bottom without hard lines.
**Commit (laptop):** `Card 7 step 3: controllable liquid in the twin`

## Step 4 · Automatic calibration against the real clean vials (Brev, about 45 min of GPU)

> "Card 7 step 4 only. Write scripts/calibrate_colors.py (one job: match the twin's dye strengths to the real camera). Targets: the blank-normalized colors of the 10 real 3rd vials (outputs/card7/vials_30_transmittance.csv, copied from the laptop), HIGH patch for tall recipes and LOW for Recipes 5 and 6. Hold out Recipes 5 and 11: never use them to adjust anything. Loop, at most 4 rounds: render the 8 calibration recipes' clean vials with set_liquid.py at their real volumes, measure them with measure_patches.py relative to the twin's own empty neighbour vial, compute ΔE2000 to the real targets, and update the 6 dye strengths along the anchored gradient (Beer–Lambert: absorbance is linear in the strengths). Stop early when the median ΔE stops improving. Save outputs/card7/twin_dye_strengths.json and outputs/card7/calibration.csv (recipe, round, ΔE). Then render the 2 held-out recipes once with the final strengths and report their ΔE separately. Run it with nohup and a log. Do NOT commit."

**Check:** the table shows ΔE per recipe per round. Our target is every calibration recipe within about ΔE 3. The **held-out** Recipes 5 and 11 tell us whether it really generalizes. Report the numbers honestly even if they miss; don't add rounds or change the hold-out after seeing them.
**Commit (laptop):** `Card 7 step 4: twin color calibration (held-out recipes 5 and 11)`

## Step 5 · Side-by-side check (laptop, about 10 min)

> "(laptop) Card 7 step 5 only. Make outputs/card7/calibration_check.png: for each of the 10 recipes, the real 3rd-vial crop next to the calibrated twin render at the same volume, labeled with recipe, ΔE, and 'held out' for Recipes 5 and 11. Do NOT commit."

**Check:** by eye, would a stranger believe each pair shows the same liquid? Note any recipe that still looks off.
**Commit:** nothing (the picture is in `outputs/`).

## Step 6 · The image set (Brev, second session, about 1.5–2.5 hours of GPU)

> "Card 7 step 6 only. Write scripts/generate_dataset.py (one job: render the labeled training images) using set_liquid.py's liquid and Replicator. Randomize for every image: orange and blue shares (clean recipes, and contaminated mixes between two recipes); fill 10–80 mL, with at least 40% of images between 25 and 45 mL; mixing 0–1; light brightness ±30% and color temperature; one extra glare light in a random position in half the images; camera jitter of 1–2 pixels; the neighbour vial missing in 10% of images. Save PNGs in batches of 200 under /workspace/project/renders/card7_dataset/batch_000 … with a labels.csv per batch: file, orange share, blue share, fill mL, mixing, light settings, glare yes/no, neighbour present yes/no, and the HIGH/LOW raw and blank-normalized Lab from measure_patches.py. First render a 30-image smoke test and a grid of those 30 images next to 30 real vial crops (scratch, not the real test vials' verdicts), then stop and wait for my OK. Only after my OK, render 1,000 images with nohup; it must resume from the last finished batch if stopped."

**Check:** in the smoke-test grid, would a stranger believe the twin images come from the same camera? Look especially at the small fills. After the full run: the labels match a few random images by eye, and `outputs/run_log.csv` gives minutes per 1,000 images. Decide on more images (up to 2,000) only if Card 8 needs them.
**Commit (laptop):** `Card 7 step 6: twin dataset generator` (scripts only; the images go to the team Drive, never GitHub)

## Step 7 · Fair lighting test: raw vs blank-normalized (Brev renders + laptop)

> "Card 7 step 7 only. Render Recipes 7, 9, 12 and 14 clean, and each one tinted with 15% of the previous recipe's mix, at their real volumes, each under 5 lighting setups: normal, 30% dimmer, 30% brighter, light from one side only, and normal plus a glare spot. Measure each with measure_patches.py. On the laptop, make outputs/card7/lighting_test.csv and a table: for each image, ΔE to the clean render under normal light, and the PASS/UNSURE/FAIL verdict (ΔE < 2 / 2–5 / > 5), with raw and with blank-normalized colors. Count how often the verdict changes compared with normal light. Do NOT commit."

**Check:** the scenes the video 5 test couldn't cover (uneven light, glare) show whether blank normalization really protects the color check. Report it either way. This decides whether the dashboard should switch to normalized colors for the CSI live test.
**Commit (laptop):** `Card 7 step 7: lighting robustness test`

## Step 8 · Write it down (laptop)

> "(laptop) Card 7 step 8. Update docs/twin-map.md (what the stripes were, twin patch coordinates, the liquid replacement), RUNBOOK.md (the Card 7 commands and outputs/card7 in the Current outputs table), docs/PROGRESS.md (a 'Card 7' section: what we did, calibration ΔE including the held-out recipes, the lighting test result, GPU minutes per 1,000 images, and credit the teammate for blank normalization, the anchored gradient, the calibration loop and the mixing state), and GEMINI.md section 7. Show me the PROGRESS.md section before committing."

**Commit:** `Card 7: calibrated twin renders and lighting test`

---

## After Card 7: Card 8 in one line

Train a small model on the twin images only to estimate the dye shares (and fill level) from the vial crop, with special attention to 25–45 mL fills. Test it only on the real vials, against the color check, small vials reported separately. A separate plan will follow once step 6's images exist.

---

## Card 10 · remaining step (needs Cosmos on Brev, after Card 9)

Steps 1–9 of Card 10 are done (`app/dashboard.py`; see `docs/PROGRESS.md`, "Card 10").

### Step 10 · Plug in the real explanations

Only after Card 9 has produced `scripts/explain.py` (built on `scripts/ask_cosmos.py`, version C prompts: vial crop, clean reference image, intended and previous recipe, dispense order, measured ΔE and the advisor's light).

> "With Cosmos reachable, run explain.py once for each of the 9 recipe changes in video 5, using each change's first vial, and save every answer with explanation_cache.put(). Then replay the dashboard. Do NOT commit; show me the cached explanation for 6->7 and a screenshot of panel 3 on vial 7."

**Check:** vial 7's panel names Recipe 6 (orange) as the previous recipe and the measured color shift as evidence. Stop the Brev instance and replay again: the page still shows the cached explanation. Read all 9 explanations yourself; would an operator know what to do?
**Commit:** none for the cache (it lives in `outputs/`). Copy `outputs/explanations_cache.json` to the demo laptop before the video recording and the live test.

## Not in these plans (decide later)

- **Live mode at CSI** (reading the real `vial_fill` camera and detecting fills without labels). It depends on the organizers' answer about camera access; `scripts/find_physical_fills.py` is the starting point.

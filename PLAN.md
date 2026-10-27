# PLAN: Card 7 · Calibrated twin renders for the small vials

(Card 8, the twin-trained model, follows Card 7 further down this file; then Card 10's last step and the **new-recording mode for the CSI session**, at the bottom.)

Written by Claude Code for Gemini to carry out, **one step per prompt**. Each step says what to ask, how to check it worked, and what to commit. Do the steps in order; don't start a step until the one before it passes its check.

**How to use this file:** on the Brev instance, start `agy` inside `/workspace/project/repo` (after `git pull` or a fresh repo copy) and say *"Read GEMINI.md and PLAN.md. Do Card 7 step N only, then tell me how to check it."* Laptop steps are marked **(laptop)**.

Card 10's remaining step (Cosmos explanations in the dashboard) is at the bottom of this file.

---

## Why Card 7, in one paragraph

Card 3b showed the color check already works on tall vials (8 of 8 caught, 0 false alarms). The one real gap is the **30–40 mL vials** (Recipes 5 and 6), where the liquid never reaches the good HIGH patch and only the weaker LOW patch works. The twin can do exactly what video 5 can't: show the same vial at **any fill height, dye mix, lighting and glare**. Card 7 makes the twin's liquid controllable, calibrates its colors against the real clean vials, and renders a labeled image set for Card 8. The twin varies **appearance only**; it does not simulate carryover (organizer feedback).

## Ideas this plan builds on

- **Blank normalization** (Ayden's idea, tested in `scripts/blank_check.py`): measure every liquid patch **relative to the empty vial in the next holder, at the same height**, like a lab blank. On video 5 it caught exactly the same vials as the raw check, and it cancels any even change in brightness. Both the twin and the real camera have that empty neighbour vial in view, so twin and real are compared in this blank-relative space. If the neighbour pocket is empty, use the median blank of the run (`blank_fallback`).
- **The anchored gradient** (Ayden): absorbance relative to the blank grows in a straight line with each dye's amount, starting from zero at the empty vial. Calibrating the twin means matching each dye's strength, a handful of numbers.
- **Automatic calibration loop** (Ayden's "reward and penalty" idea): render, measure the color error against the real vial, correct the dye strengths along the gradient, repeat a few times.
- **Mixing state** (Ayden's "flow" idea): some real first vials look layered (darker at the bottom; `outputs/card4/first_vial_strips.png`). The renders include a controllable "mixing state", from evenly mixed to layered, so a model learns layered vials too.

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

> "(laptop) Card 7 step 8. Update docs/twin-map.md (what the stripes were, twin patch coordinates, the liquid replacement), RUNBOOK.md (the Card 7 commands and outputs/card7 in the Current outputs table), docs/PROGRESS.md (a 'Card 7' section: what we did, calibration ΔE including the held-out recipes, the lighting test result, GPU minutes per 1,000 images, and credit Ayden for blank normalization, the anchored gradient, the calibration loop and the mixing state), and GEMINI.md section 7. Show me the PROGRESS.md section before committing."

**Commit:** `Card 7: calibrated twin renders and lighting test`

---

# PLAN: Card 8 · Twin-trained vial model, tested on real vials (laptop)

**Goal:** a small model trained **only on the Card 7 twin images** that estimates a vial's orange and blue share from its patch colors, then judges real vials by comparing that estimate with the recipe. It is tested on the real vials with the **same vials and answer keys as Card 3**, with the small vials reported separately. Everything runs on the laptop (scikit-learn, already in `requirements.txt`); no Brev.

**Honest limits, written down before any result:**
- Only 4 scored real vials are small (vials 1, 2, 4, 5). Whatever the model does there can't be proven statistically; it is reported as a count, not a percentage claim.
- The model's yes/no threshold is chosen on twin images only, never on real vials. The camera-response curve (`outputs/card7/camera_response.json`) was fitted on the real 3rd vials only, which are references, not test vials.
- If the model doesn't beat the color check, that is the result we report.

## Step 1 · Twin features and labels (laptop)

> "Read GEMINI.md and PLAN.md. Card 8 step 1 only. Copy the 1,000-image dataset's labels.csv files (all batches) into outputs/card7/dataset_labels/ (the images themselves stay on the team Drive). Write scripts/build_twin_features.py (one job) that makes outputs/card8/twin_features.csv with one row per twin image: the blank-normalized linear RGB of the LOW patch, of the HIGH patch (empty if the fill is below the HIGH patch), fill mL, and the labels orange share, blue share, and whether the image is a clean recipe or a contaminated mix. Apply the camera-response curve from outputs/card7/camera_response.json (the simpler gain-only version) to the twin colors. Print the row count, the share ranges, and how many rows have no HIGH patch. Do NOT commit."

**Check:** about 1,000 rows; roughly half have no HIGH patch (small fills); shares range 0–0.72.
**Commit:** `Card 8 step 1: twin features for the vial model`

## Step 2 · Train the model on twin images only (laptop)

> "Card 8 step 2 only. Write scripts/train_vial_model.py (one job) that trains two small scikit-learn regressors to predict orange share and blue share from the features in outputs/card8/twin_features.csv: one using LOW + fill mL (for every vial), one using HIGH + LOW + fill mL (tall vials only). Hold out 20% of the twin images, split by whole clean recipe or contamination pair (not random rows), and report the error in share units on that twin hold-out. Then choose the flag threshold on the twin hold-out only: the share distance (between predicted shares and the recipe's shares) that best separates clean images from contaminated ones; save both models and the threshold in outputs/card8/ (model files are git-ignored). Do NOT commit."

**Check:** the share error on twin hold-out is small (well under 0.1); the threshold is a single number recorded before any real vial is touched.
**Commit:** `Card 8 step 2: twin-trained vial model and twin-chosen threshold`

## Step 3 · Test on the real vials (laptop)

> "Card 8 step 3 only. Write scripts/test_vial_model.py (one job) that computes the same features for the real vials (blank-normalized LOW and HIGH from scripts/blank_check.py's measurements, recipe mL), predicts their shares with the saved models (HIGH model for tall vials, LOW model for short ones), and flags a vial when the share distance to its recipe exceeds the saved threshold. Score it exactly like baseline_check.py (same 18 vials, same three answer keys, the 16 tall vials separately) and also on the small vials 1, 2, 4 and 5 against judge_1. Make one table with three rows per key: (a) the Card 3 color check, (b) the twin-trained model vs the recipe's shares, (c) the twin-trained model vs its own prediction for the recipe's real 3rd vial (instead of the recipe's shares). Save outputs/card8/real_test.csv. Do NOT commit."

**Check:** every number comes from the same vials and keys as Card 3. Row (c) usually helps when the model is biased; if (b) and (c) disagree a lot, the model's absolute shares are off but its comparisons may still work.
**Commit:** `Card 8 step 3: real-vial test of the twin-trained model`

## Step 4 · Write it down (laptop)

> "Card 8 step 4. Add a 'Card 8' section to docs/PROGRESS.md (what we trained on, the twin hold-out error, the threshold chosen on twin data, the real-vial table with all three rows, the small-vial counts, and the honest limits listed at the top of this plan), the commands to RUNBOOK.md, and update GEMINI.md section 7. Show me the PROGRESS.md section before committing."

**Commit:** `Card 8: twin-trained model results`

---

## Card 10 · remaining step (needs Cosmos on Brev, after Card 9)

Steps 1–9 of Card 10 are done (`app/dashboard.py`; see `docs/PROGRESS.md`, "Card 10").

### Step 10 · Plug in the real explanations

Only after Card 9 has produced `scripts/explain.py` (built on `scripts/ask_cosmos.py`, version C prompts: vial crop, clean reference image, intended and previous recipe, dispense order, measured ΔE and the advisor's light).

> "With Cosmos reachable, run explain.py once for each of the 9 recipe changes in video 5, using each change's first vial, and save every answer with explanation_cache.put(). Then replay the dashboard. Do NOT commit; show me the cached explanation for 6->7 and a screenshot of panel 3 on vial 7."

**Check:** vial 7's panel names Recipe 6 (orange) as the previous recipe and the measured color shift as evidence. Stop the Brev instance and replay again: the page still shows the cached explanation. Read all 9 explanations yourself; would an operator know what to do?
**Commit:** none for the cache (it lives in `outputs/`). Copy `outputs/explanations_cache.json` to the demo laptop before the video recording and the live test.

---

# PLAN: New-recording mode for the CSI session (laptop, no Brev)

**Goal:** CSI runs a planned recipe sequence on Station 3 while we watch. We take that `vial_fill` recording and, **on site, the same day**, process it with Carryover Copilot: find each filled vial without hand-made labels, take fresh reference vials from that recording, check every vial with blank-normalized colors, warn when the lighting changed, and write a trial log. This is the judges' "solution operating on the CSI hardware" (`docs/submission-and-judging.md`). Live camera reading is **not** part of this plan.

**Why it's needed:** today everything depends on `annotations/video5_vial_times_corrected.csv`, where the "last parked frame" of each vial was found by hand (the 30 frame numbers are typed into `scripts/find_physical_fills.py`). A new recording has no such table, and its recipes, lighting and reference vials are new.

**Ground rules:**
- **Video 5 is the practice run.** Every step is checked by treating video 5 as if it were a new recording and getting the same answers as the existing dashboard. CSI's recording is the real test: nothing is tuned on it.
- **Thresholds are fixed now, before any CSI data:** verdicts stay ΔE < 2 pass, 2–5 unsure, > 5 fail; the lighting warning fires when a vial's blank differs from its reference vial's blank by ΔE2000 > 3.0 (the blank varies by about 1.1–1.3 L on video 5, so 3 is well outside normal); an empty neighbour pocket is a blank whose L* is more than 5 away from the run's median blank.
- **The recipe list and recordings are data:** they live in `data/runs/<run name>/` (ignored by Git). Results go to `outputs/runs/<run name>/`. Only scripts and an empty template are committed.
- **The answer key comes first.** At CSI, a teammate writes their by-eye verdict for every vial (matches / unsure / off) on paper **before** anyone looks at the system's verdicts, exactly like `judge_1` on video 5.
- Cosmos is not needed on the day: new recipe changes show "explanation unavailable" unless an explanation is already cached (Card 9). The decision never depends on Cosmos.

## Step 0 · What to ask CSI for (captain, no code)

Ask, in the same thread as the session request:
1. The **`vial_fill` recording** of the session as an `.mp4` (same camera, same position as the dataset; we never move or re-aim it), handed to us on a USB stick or shared drive before we leave.
2. The **recipe list** in fill order: for every vial, the recipe ID and the mL from T-200, T-400 and T-100.
3. **At least 3 vials per recipe**, as in video 5, so the last vial of each recipe can be its clean reference. Ideally include a change into a pale recipe from a blue one and a change into or out of a clear-only recipe (the gaps in `docs/organizer-feedback.md`).
4. What is in each tank that day.
5. Permission to film the station and our laptop screen together.

## Step 1 · Find the filled vials without labels (laptop, about 1 hour)

> "Read GEMINI.md and PLAN.md. New-recording mode step 1 only. Write scripts/detect_parked_vials.py (one job): given any vial_fill .mp4, find the **last parked frame** of every vial that was filled under the nozzle, with no label file. Hint: the starwheel only moves when it indexes to the next vial, so frame-to-frame change in a region that includes the neighbour vial (around x 400–440) is near zero while a vial is parked and large when it moves; the fill itself only changes the vial region. Take the frame a few frames before each index move starts, and keep only parked vials whose LOW patch shows liquid. Write outputs/runs/<name>/parked_vials.csv (vial order, frame, mp4 seconds) and a contact sheet of every found frame with the LOW and HIGH patches drawn. Test it on video 5 and compare with the 30 last_parked_frame values in annotations/video5_vial_times_corrected.csv: print how many vials it found, any extras or misses, and the frame difference for each vial. Then run scripts/vial_check.py's color check at the found frames and at the known frames and say whether any verdict differs. Also run it on videos 1–4 and just report how many vials it finds in each. Do NOT commit."

**Check:** on video 5, exactly 30 vials, no extras, each within 15 frames of the known frame, and **every verdict the same** as at the known frames. (Done Oct 27: the fill test is the LOW patch's change during the parked interval, cut 4.6, midway between the largest empty-pocket change 2.63 and the palest fill seen, 6.54 in video 3. A clear-only fill has never been seen, so the margin for it is unknown.) Open the contact sheet: every patch sits inside liquid. Videos 1–4 have no labels, so their counts are only a sanity check (look at their contact sheets by eye). If video 5 needs tuning, tune on video 5 only.
**Commit:** `New-recording mode step 1: find parked vials without labels`

## Step 2 · Turn a recording + recipe list into a run table (laptop, about 45 min)

> "New-recording mode step 2 only. Create annotations/run_recipes_template.csv with the columns vial, recipe_id, t200_ml, t400_ml, t100_ml, is_reference (header and one example row only). Write scripts/new_run.py (one job): given --video, --recipes (a filled-in copy of the template) and --name, run detect_parked_vials.py, match the n-th parked vial to the n-th recipe row, and **stop with a clear message** if the counts differ (say both counts, list every rejected parked interval with its frame and LOW change so a missed pale or clear fill is easy to spot, mention the --min-fill-de option, and point to the contact sheet). If is_reference is empty, use the last vial of each run of the same recipe. Refuse a recipe with fewer than 2 vials or more than 80 mL, and warn about T-300 or over 50 mL from T-200. Check the camera hasn't moved: run crop_vial.py's glass-edge check on every found frame and stop with a message if any patch touches the glass. Write outputs/runs/<name>/vials.csv with the same columns the dashboard already reads from annotations/video5_vial_times_corrected.csv (vial, recipe_id, total_ml, last_parked_frame, last_parked_mp4_s, plus is_reference), so existing code can read it. Test it on video 5 using a recipe list made from the label file's recipe and tank mL per vial, saved as data/runs/video5_practice/recipes.csv. Do NOT commit."

**Check:** `outputs/runs/video5_practice/vials.csv` has 30 rows with the same recipes as the annotations, the 10 references are vials 3, 6, …, 30, and frames match step 1. Delete one row from the practice recipe list and run again: it must stop with the "counts differ" message, not crash.
**Commit:** `New-recording mode step 2: run table from a recording and a recipe list`

## Step 3 · Blank-normalized check and the "lighting changed" warning (laptop, about 1 hour)

> "New-recording mode step 3 only. In scripts/vial_check.py add a normalized check next to the existing raw one (keep the raw one unchanged): measure the vial's patch and the neighbour vial's blank at the same height (BLANK_HIGH x 410–426, y 268–288; BLANK_LOW x 410–426, y 352–372), T = linear patch ÷ linear blank, normalized color = T × the run's median blank, then Lab and ΔE2000 against the reference vial's normalized color, same verdict cut points. Detect an empty neighbour pocket automatically: blank L* more than 5 away from the run's median blank → use the run's median blank and mark blank_fallback. Add the lighting warning: if the vial's raw blank color differs from its reference vial's raw blank by ΔE2000 > 3.0, return the warning 'lighting changed since this recipe's reference vial: re-take the reference vial'. Test on the video 5 practice run: list which vials get blank_fallback, how many lighting warnings fire, and every vial whose normalized verdict differs from the raw verdict. Then a made-up lighting change: darken only the frames of vials 19 and 20 by 25% (linear) and run again. Do NOT commit."

**Check:** blank_fallback on exactly vials 6, 24 and 30 (matching `scripts/blank_check.py`); **0** lighting warnings on video 5 (if any fire, show me before touching the 3.0); normalized verdicts catch the same vials as Card 3 (HIGH 8 of 8, 0 false alarms). With vials 19 and 20 darkened: warnings on exactly vials 19 and 20, and their normalized verdicts don't change. Say plainly that the warning catches overall brightness changes; light from one side fooled both methods in the Card 7 twin test, so the warning is a prompt to re-take references, not a guarantee.
(Done Oct 27, accepted: blank_fallback on 6, 24, 30; 0 warnings on video 5, but the largest natural blank change was 2.75 (vial 29), close to the 3.0 cut, so an occasional false 'lighting changed' warning at CSI is possible; the warning never changes a verdict. Raw and normalized verdicts identical on all 30; darkening vials 19 and 20 fired warnings on exactly those two, normalized verdicts unchanged, while raw vial 20 went PASS → UNSURE.)
**Commit:** `New-recording mode step 3: blank-normalized check and lighting warning`

## Step 4 · Risk lights from the run's own references (laptop, about 30 min)

> "New-recording mode step 4 only. Let scripts/flush_advisor.py take its clean references from a run (outputs/runs/<name>/vials.csv, the is_reference vials, normalized colors) instead of only outputs/card3/baseline_results.csv, keeping the same alphas from the Card 4 risk model and the same light cut points. A recipe change whose recipes have no reference yet shows the existing 'unknown recipe, no clean reference yet' message (gray), never a guessed light. Add a --run option to the command line. Test on the video 5 practice run and compare the 9 lights with the current advisor's. Do NOT commit."

**Check:** the 9 lights on video 5 match today's dashboard, or any difference is listed with both recipe-gap numbers (normalized colors can shift a gap a little). 6 → 7 stays RED.
**Commit:** `New-recording mode step 4: risk lights from a run's references`

## Step 5 · The dashboard's "new recording" source and the trial log (laptop, about 1.5 hours)

> "New-recording mode step 5 only. In app/dashboard.py add a sidebar choice 'Source': 'Video 5 (demo)' (today's behavior, unchanged) or 'Recorded run' with a dropdown of folders in outputs/runs/. For a recorded run: read its vials.csv and video, use the normalized check from step 3 and the run's risk lights from step 4, show the lighting warning in panel 2 when it fires, and change the honesty banner to: 'Recorded run <name>: reference vials are the last vial of each recipe in this recording, so they are not checked.' Hide the judge_1 end-of-run table unless outputs/runs/<name>/judge_verdicts.csv exists (columns vial, verdict), in which case compare against it the same way. Write outputs/runs/<name>/trial_log.csv as vials are shown, one row per vial: time shown, vial, recipe, previous recipe, risk light, verdict, ΔE, patch, blank_fallback, lighting warning, ms per vial, notes. Test with the video 5 practice run. Do NOT commit; show me a screenshot of vial 7 in 'Recorded run' mode and the first 10 rows of the trial log."

**Check:** in 'Recorded run' mode on video 5, the verdicts match step 3 and vial 7 is FAIL with 6 → 7 RED; switching back to 'Video 5 (demo)' looks exactly as before. The trial log has one row per vial shown, including passes.
**Commit:** `New-recording mode step 5: dashboard source for recorded runs and the trial log`

## Step 6 · Dry run, one command, and failure rehearsal (laptop, about 45 min)

> "New-recording mode step 6. Add to RUNBOOK.md a 'CSI session day' section: where to put the recording and the recipe list (data/runs/<name>/), the one command that builds the run (python scripts/new_run.py --video ... --recipes ... --name ...), then streamlit run app/dashboard.py and 'Recorded run'. Then rehearse failures and fix anything that crashes instead of showing a message: a wrong video path, a recipe list with one row missing, a recipe list with a typo in a column name, and a recording with the camera shifted (shift video 5's frames 20 px right in a scratch copy). Do NOT commit; show me what each failure prints."

**Check:** every failure prints a plain-English message saying what to fix. Then a teammate who didn't build it runs the video 5 practice run from RUNBOOK.md alone (this also counts as Card 10's cold-start test).
**Commit:** `New-recording mode step 6: CSI session-day runbook and failure messages`

## Step 6b · Write it down (laptop, about 20 min)

> "New-recording mode step 6b. Add a 'New-recording mode' section to docs/PROGRESS.md: what it does and why (the judges want the system on CSI hardware; video 5's vial frames were found by hand); the fill test (LOW patch change during the parked interval, cut 4.6, between the largest empty-pocket change 2.63 and the palest fill 6.54; no clear-only fill seen yet); the video 5 practice result (30 of 30 found, all verdicts identical); blank normalization and the lighting warning (0 warnings on video 5, largest natural blank change 2.75 against the 3.0 cut; the darkening test); and the limits (light from one side fools both checks; references come from the same recording). Update GEMINI.md section 7 and RUNBOOK.md's Current outputs table. Show me the PROGRESS.md section before committing."

**Check:** every number above appears exactly as written; no 'proves', 'guarantees' or 'eliminates'.
**Commit:** `New-recording mode: docs`

## Step 7 · At CSI (whole team, no code changes on the day)

1. Before the run: tag the commit (`git tag csi-session-v1`), copy `outputs/explanations_cache.json` to the laptop, confirm the camera is untouched. Observe only; nobody touches the station.
2. During the run: one teammate fills the paper judge sheet by eye for every vial; one films the station and the screen.
3. After the run: copy the recording and recipe list into `data/runs/csi_<date>/`, type the judge sheet into `outputs/runs/csi_<date>/judge_verdicts.csv` **before** running the system, then run `new_run.py` and the dashboard. Keep every attempt in the trial log, including failures and reruns.
4. Report the result honestly, whatever it is, with the same counts as Card 3 (caught, false alarms, misses), plus the lighting warnings and any vials the detector missed.
5. **If no visit is possible:** ask CSI to record the sequence and send the `vial_fill` .mp4 and recipe list; process it the same way and say plainly in the video that CSI ran the station and we processed their recording. Never present video 5 as the CSI session.
6. Afterwards: add a 'CSI session' section to docs/PROGRESS.md with the trial log counts, and commit the judge sheet as `annotations/csi_<date>_judge_verdicts.csv` (a hand-typed answer key, not camera data).

---

# PLAN: Card 9 · Cosmos explanations for flagged vials (laptop + Brev Cosmos)

**Goal:** a short, checkable explanation for each flagged vial, written by Cosmos 3 Nano Reasoner from the camera evidence and the recipes (organizer feedback: ground every explanation in the current recipe, the previous recipe and the camera evidence). Cosmos explains; the color check still decides (Card 3b).

**Scope (time is short):** version C only (vial crop + reference crop + recipe text + our measured ΔE and the advisor's light). The A/B comparison is not run; say so in the docs. Test set: the 8 flagged first vials of video 5 with a known previous recipe: vials 4, 7, 10, 16, 19, 22, 25, 28 (vial 13, 8 → 9, passed the color check, so it never reaches Cosmos).

**Honest-scoring rules, written before any result:** the prompt and the scoring rubric are committed **before** the Brev run, and nothing in them changes after seeing answers. A teammate scores every answer against the rubric. The cache stores the **first** repeat for each recipe change, not the best-looking one.

## Step 1 · explain.py and the rubric (laptop, about 45 min)

> "Read GEMINI.md and PLAN.md. Card 9 step 1 only. Write scripts/explain.py (one job: ask Cosmos to explain one flagged vial) on top of scripts/ask_cosmos.py, using the same request format. Inputs for a vial: its liquid crop and the clean reference crop of its recipe from outputs/card3b/crops/, and as text: the intended recipe (number and mL from T-200 orange, T-400 blue, T-100 clear), the previous recipe (same), the dispense order T-200 → T-400 → T-100 through one shared pipe and nozzle, the patch used, the measured ΔE2000 against the reference, the verdict, and the flush advisor's light for that change. System prompt: 'You inspect vials on a color-mixing line. Image 1 is the vial being checked, image 2 is a clean vial of the same recipe. Use only the facts given; do not invent numbers or say a flush has been tested. Answer only in JSON with keys matches_recipe (true/false), observed_color, likely_cause, operator_action, confidence (low/medium/high).' Add --vials, --repeats (default 3), --dry-run (prints the full prompt for each vial without calling Cosmos), and save every answer to outputs/card9/explanations.csv (vial, change e.g. 6->7, repeat, raw answer, parsed fields, seconds). With --cache, put the first repeat of each change into outputs/explanations_cache.json via scripts/explanation_cache.py. Also write annotations/card9_rubric.md with this rubric: an explanation is CORRECT only if (1) matches_recipe is false; (2) it names the previous recipe or its color; (3) the cause is leftover of the previous recipe in the shared path or nozzle; (4) the action invents nothing (no made-up numbers, no claim that a flush is proven); (5) observed_color is a fair description of image 1 (the scorer looks at the crop). Run --dry-run for vial 7. Do NOT commit; show me the vial 7 prompt."

**Check:** the vial 7 prompt says Recipe 7 (50 mL blue + 20 mL clear), previous Recipe 6 (10 mL orange + 30 mL clear), ΔE about 25.6 on HIGH, FAIL, advisor RED, and the images go **before** the text. No numbers in it that aren't in our outputs.
**Commit (before any Cosmos run):** `Card 9 step 1: explain.py (version C) and the frozen scoring rubric`

## Step 2 · Run it on Brev (Cosmos instance, about 30 min of GPU)

Follow RUNBOOK.md, "Cosmos: start the server" (Nebius L40S, JupyterLab terminal, `nvidia-smi` shows CUDA 12.9 or higher, then `docker start cosmos`, then the ready check). Upload `scripts/explain.py`, `scripts/ask_cosmos.py`, `scripts/explanation_cache.py` and `outputs/card3b/crops/` as in the Card 3b run, then:

```bash
python3 explain.py --vials 4 7 10 16 19 22 25 28 --repeats 3 --cache
```

Download `outputs/card9/explanations.csv` and `outputs/explanations_cache.json` (right-click → Download) into the same folders on the laptop. **Stop** the instance (Stop, never Delete), log the hours, and never paste the NVIDIA key into a chat.

**Check:** 24 rows; every answer parsed as JSON (or the raw text is kept when it didn't); `python scripts/explanation_cache.py --show` on the laptop lists 8 changes.

## Step 3 · Score, plug in, write down (laptop, about 1 hour)

1. A teammate who didn't write the prompt scores the **first** repeat of each of the 8 vials with `annotations/card9_rubric.md`, looking at each crop, and types the result into `annotations/card9_scores.csv` (vial, change, correct yes/no, which rubric point failed). Also count how many vials got the same matches_recipe and cause in all 3 repeats.
2. Card 10 step 10 (above): replay the dashboard; vial 7's panel 3 shows the cached 6->7 explanation, and still does with the Brev instance stopped.
3. > "Card 9 step 3. Add a 'Card 9' section to docs/PROGRESS.md: version C only (A/B not run), the 8 vials, the frozen rubric, the score as 'N of 8 fully correct' with which points failed, the repeat consistency, seconds per call, and one example explanation quoted exactly (6->7). Update GEMINI.md section 7 and RUNBOOK.md. Show me the section before committing."

**Check:** the score is a count out of 8 straight from `annotations/card9_scores.csv`; any wrong explanations are listed, not hidden.
**Commit:** `Card 9: Cosmos explanations, scored` (scripts, rubric and scores only; the cache and CSVs in outputs/ stay local; copy the cache to the demo laptop).

## Not in these plans (decide later)

- **Live camera mode at CSI** (reading the real `vial_fill` camera as frames arrive). It depends on the organizers' answer about camera access. The new-recording mode above covers a recording processed the same day.

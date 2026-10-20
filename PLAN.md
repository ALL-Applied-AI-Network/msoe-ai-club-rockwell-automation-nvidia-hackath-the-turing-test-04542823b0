# PLAN: Card 10 · Cascade and operator dashboard

Written by Claude Code for Gemini to carry out, **one step per prompt**. Each step says what to ask, how to check it worked, and what to commit. Do the steps in order; don't start a step until the one before it passes its check.

**How to use this file:** tell Gemini *"Read GEMINI.md and PLAN.md. Do step N only, then tell me how to check it."* After the check passes, commit with the message given in that step.

---

## What we are building, in one paragraph

A Streamlit web page (`app/dashboard.py`) that replays video 5 as if it were live and shows the whole system working: (1) the recipe queue with a green/amber/red light for each recipe change, from `scripts/flush_advisor.py`; (2) each vial as it finishes filling, with its crop and verdict from the color check; (3) a plain-language explanation for flagged vials, from Cosmos once it runs on Brev (until then, "explanation unavailable"). This is the screen the judges watch in the video.

## Ground rules for every step

- **The app stays thin.** All logic lives in small scripts in `scripts/` (one job each, each runnable on its own); `app/dashboard.py` only imports them and draws the page. To import from `scripts/`, the app adds the `scripts/` folder to `sys.path`.
- **Reuse, don't rewrite.** Frame reading comes from the code in `scripts/baseline_check.py` (it seeks to `last_parked_frame` from `annotations/video5_vial_times_corrected.csv`); patch colors from `scripts/crop_vial.py`; lights and reorder advice from `evaluate_transition()` and `evaluate_order()` in `scripts/flush_advisor.py`.
- **Same cut points everywhere:** ΔE below 2 green/pass, 2–5 amber/unsure, above 5 red/fail. Never tune them on video 5.
- **Be honest on screen.** The replay uses the labeled fill times and the 3rd vials of this same run as references, so the replay is a **demo, not a score**. The score is Card 3's leave-one-recipe-out result. The page must say so (step 8).
- **Detection never depends on Cosmos.** If Cosmos is off or fails, the page still shows every light and verdict.
- **Debug images go in `scratch/`, results in `outputs/card10/`.** Nothing in `data/`, `outputs/` or `scratch/` is committed.

## The cascade on this page

| Step | What runs | Built in | Status for the demo |
| --- | --- | --- | --- |
| 1. Before the fill | Risk light for the coming recipe change | Card 4 (`flush_advisor.py`) | Ready |
| 2. After the fill | Vial color vs. its recipe's clean reference (ΔE2000; HIGH patch if the vial is ≥ 60 mL, else LOW, marked "low confidence") | Card 3 (`baseline_check.py`) | Ready, wrapped in step 1 below |
| 3. Unsure zone | Twin-trained vial model | Cards 7–8 | **Not built** (only if Card 3b says it's needed). Unsure vials show "check by eye". |
| 4. Flagged vial | Cosmos explanation, cached per recipe change (e.g. `"6->7"`) | Card 9 | Needs Brev. Step 10 below plugs it in. |

---

## Steps 1–9: no Brev needed

### Step 1 · One-vial color check as a reusable function

> "Read GEMINI.md and PLAN.md. Write scripts/vial_check.py with one job: check one vial against its recipe. It has a function check_vial(frame, recipe_id, total_ml, references) that returns a dict with: patch used (HIGH if total_ml ≥ 60, else LOW), measured Lab, reference Lab, ΔE2000, verdict (pass if ΔE < 2, unsure if 2–5, fail if > 5) and confidence ('normal' for HIGH, 'low' for LOW). Also a function load_references() that builds each recipe's clean reference from its 3rd vial, reusing the patch code from crop_vial.py and the frame reading from baseline_check.py. Add a command line: python scripts/vial_check.py --vial 7 prints the result for one vial, and python scripts/vial_check.py --all prints all 30 and compares each ΔE with outputs/card3/baseline_results.csv. Do NOT commit; show me both outputs."

**Check:** vial 7 says fail; vial 8 says pass or unsure; `--all` reports that every ΔE matches `baseline_results.csv` (differences below 0.01). The 3rd vials show ΔE 0, because each is its own reference; the output should label them "reference vial".
**Commit:** `Card 10 step 1: reusable one-vial color check`

### Step 2 · Replay feed

> "Write scripts/replay_feed.py with one job: hand out the recorded vials of video 5 in order, as if they were arriving live. A function iter_vials() yields, for each of the 30 vials: vial number, recipe ID, previous recipe ID (None for vial 1), total mL, mp4 time and the last parked frame (read from data/.../vial_fill_video_5.mp4 at last_parked_frame from annotations/video5_vial_times_corrected.csv). Command line: python scripts/replay_feed.py --vial 7 --save scratch/replay_v7.jpg saves that frame and prints its details; python scripts/replay_feed.py --list prints all 30 rows without reading frames. Do NOT commit; show me the output and the saved image."

**Check:** the saved vial 7 image shows the green vial parked under the nozzle; `--list` shows 30 rows, recipes 5–14, previous recipe 6 for vial 7.
**Commit:** `Card 10 step 2: replay feed for video 5`

### Step 3 · Explanation cache (no Cosmos yet)

> "Write scripts/explanation_cache.py with one job: store and look up Cosmos explanations per recipe change. Functions get(prev_recipe, next_recipe) and put(prev_recipe, next_recipe, explanation_dict), using outputs/explanations_cache.json with keys like "6->7", and append every put to outputs/cosmos_log.csv with a timestamp. A missing or broken file must never crash: get() then returns None. Command line: python scripts/explanation_cache.py --show prints what is cached. Do NOT commit; show me --show on an empty cache and after putting one test entry, then delete the test entry."

**Check:** an empty cache prints "no explanations cached yet"; the test entry appears under `"6->7"`; deleting the JSON file and running `--show` again doesn't crash.
**Commit:** `Card 10 step 3: explanation cache`

### Step 4 · Page skeleton

> "Add streamlit to requirements.txt and install it. Create app/dashboard.py: a Streamlit page titled 'Carryover Copilot · Fluid Mixing Station 3' with three panels side by side: (1) Recipe queue, (2) Latest vial, (3) Explanation. For now, fill them with fixed example text for vial 7 only. Give me the exact command to start it and tell me what I should see. Do NOT commit."

**Check:** `streamlit run app/dashboard.py` opens a browser tab with three panels and the title. Nothing crashes.
**Commit:** `Card 10 step 4: dashboard skeleton`

### Step 5 · Panel 1, the recipe queue with lights

> "Wire panel 1 to flush_advisor.py's evaluate_transition() and evaluate_order() (import them; don't copy them). Show video 5's recipe order (5 → 6 → … → 14) as a row of recipe boxes with a green/amber/red light on each change, the recipe gap, and the action text. Highlight the next change coming up. Below it, show the reorder advice for the next 3 recipes in the queue (the Batch Scheduler holds up to 3), with 'needs the planner's OK'. If outputs/card4/risk_model.json or outputs/card3/baseline_results.csv is missing, show the same plain message flush_advisor.py prints instead of crashing. Do NOT commit."

**Check:** the 6 → 7 change is red, 8 → 9 amber, and the lights match `python scripts/flush_advisor.py 5 6 7 8 9 10 11 12 13 14` exactly.
**Commit:** `Card 10 step 5: recipe queue panel with risk lights`

### Step 6 · Panel 2, replaying the vials

> "Wire panel 2 to replay_feed.py and vial_check.py. Add a 'Next vial' button and an 'Auto-play' switch (one vial every 3 seconds). For each vial, show the vial crop with the measured patch outlined, the recipe and previous recipe, ΔE, and a big PASS / UNSURE / FAIL label colored green / amber / red. Mark 'low confidence' for vials under 60 mL and 'reference vial' for 3rd vials. Keep the replay position when the page refreshes (st.session_state). Panel 1 should move its highlight to the change that the current vial belongs to. Do NOT commit."

**Check:** step through vials 6 → 7 → 8. Before vial 7, panel 1 shows the red 6 → 7 light; vial 7 shows FAIL; vial 8 shows PASS or UNSURE. Auto-play runs through all 30 without errors.
**Commit:** `Card 10 step 6: vial replay panel`

### Step 7 · Panel 3 and the cascade counter

> "Wire panel 3 to explanation_cache.py. When the current vial is FAIL, look up the cached explanation for 'previous->current' recipe and show likely_cause and operator_action in large text, plus the evidence line: intended recipe, previous recipe, measured color vs reference (ΔE and patch) and the frame number used. If nothing is cached, show 'Explanation unavailable (Cosmos not running)' and still show the evidence line. PASS vials show 'No explanation needed'. UNSURE vials show 'Check by eye (vial model not built)'. Under the panels, add a counter: how many vials reached each cascade step (1 checked before fill, 2 color-checked, 3 unsure, 4 sent to Cosmos) and the average time per vial for the color check. Do NOT commit."

**Check:** with an empty cache, vial 7 shows "Explanation unavailable" plus the evidence line; after a full auto-play, the counter shows 30 vials color-checked, and the number sent to Cosmos equals the number of FAIL vials.
**Commit:** `Card 10 step 7: explanation panel and cascade counter`

### Step 8 · Honesty banner and end-of-run summary

> "Add a banner at the top: 'Replay of recorded video 5. Clean references are the 3rd vials of this same run, so this replay is a demonstration, not a score. Our score is the Card 3 leave-one-recipe-out result.' When the replay reaches vial 30, show a summary table: every FAIL and UNSURE vial, its ΔE, and judge_1's verdict from annotations/video5_visual_verdicts.csv side by side. Do NOT commit."

**Check:** the banner is visible without scrolling; the summary lists vial 7 as FAIL with judge_1 'unsure', and every vial in the table can be traced to a row of `outputs/card3/baseline_results.csv`.
**Commit:** `Card 10 step 8: honesty banner and run summary`

### Step 9 · One command and a cold start by a teammate

> "Add a 'Dashboard' section to RUNBOOK.md: which scripts must have run first (baseline_check.py → fit_risk_model.py), the one command that starts the dashboard, what the page shows, and what to do if it says a file is missing. Add a plain-English 'Card 10 · Dashboard' entry to docs/PROGRESS.md and update GEMINI.md section 7. Then commit and push."

**Check:** a teammate who did not build it starts the dashboard from RUNBOOK.md alone, on their own laptop, and replays to vial 9. Anything they had to ask about goes back into RUNBOOK.md.
**Commit:** `Card 10 step 9: dashboard runbook and docs`

---

## Step 10: needs Cosmos running on Brev (after Card 9)

### Step 10 · Plug in the real explanations

Only after Card 9 has produced `scripts/explain.py` (built on `scripts/ask_cosmos.py`, version C prompts: vial crop, clean reference image, intended and previous recipe, dispense order, measured ΔE and the advisor's light).

> "With the Cosmos port forward open, run explain.py once for each of the 9 recipe changes in video 5, using each change's first vial, and save every answer with explanation_cache.put(). Then replay the dashboard. Do NOT commit; show me the cached explanation for 6->7 and a screenshot of panel 3 on vial 7."

**Check:** vial 7's panel names Recipe 6 (orange) as the previous recipe and the measured color shift as evidence. Stop the Brev instance and replay again: the page still shows the cached explanation. Read all 9 explanations yourself; would an operator know what to do?
**Commit:** none for the cache (it lives in `outputs/`). Copy `outputs/explanations_cache.json` to the demo laptop before the video recording and the live test.

---

## Not in this plan (decide later)

- **Live mode at CSI** (reading the real `vial_fill` camera and detecting fills without labels). It depends on the organizers' answer about camera access; `scripts/find_physical_fills.py` is the starting point.
- **Step 3 of the cascade** (twin-trained model): only if Card 3b says the color check plus Cosmos isn't good enough.

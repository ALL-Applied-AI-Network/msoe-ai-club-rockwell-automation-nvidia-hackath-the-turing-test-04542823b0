# Fluid Mixing Team Plan — Rockwell × NVIDIA Innovation Lab

> **Repo copy of the "Team plan" tab** of our team doc, *Fluid Mixing Team Plan — Rockwell × NVIDIA Innovation Lab* (exported Oct 13, 2026). The live doc is the source of truth: when the plan changes, update the doc and re-export this file. AI agents read this copy through GEMINI.md. Diagrams from the doc are described in one line here.

Oct 12, 2026 · M

## TL;DR

We build **Carryover Copilot** for Dataset 2 (Fluid Mixing Station): a system that warns the operator *before* a risky recipe change, checks every filled vial against its intended recipe, and explains in plain words why a vial is off ("residual orange from Recipe 6 turned this blue fill green"). It hits all four things the organizers said make a project competitive:

| Organizer criterion | How Carryover Copilot meets it |
| --- | --- |
| 1. Clear manufacturing challenge | First vial after a recipe change comes out the wrong color; today's Teledyne check only knows "known color vs unknown", not "matches the recipe" or "why" |
| 2. Demo on UWM CSI hardware | Supervised live test at CSI, running on the real `vial_fill` camera during a scheduled recipe sequence |
| 3. Uses Physical AI models | Cosmos Reason 3 (vision-language reasoning) for the explanation; Isaac Sim digital twin for synthetic training data |
| 4. Leverages NVIDIA compute | Isaac Sim on a Brev RTX PRO 6000 for synthetic data; DGX Spark / GB10 or Brev for training and inference |

**Why this dataset:** it is the only one where the organizers explicitly ask for root cause, not just detection, and the cause is learnable from data we already have (recipe order + dispense order T-200 → T-400 → T-100). That makes a strong business story and a clear baseline to beat.

**Deadlines:** team plan Wed Oct 14, 11:59 PM CT · final submission (≈5-min video, one-page summary, repo, references) Sun Nov 1, 11:59 PM CT · finals Thu Nov 5, 5–8 PM, MSOE Diercks Hall. Prize pool: $5,000 cash + RTX 5080 + RTX 5070 (split not announced yet).

> Assumption: you linked the Fluid Mixing page, so this plan picks Dataset 2. If the team wants Vial Inspection or Grasping instead, say so and I'll rework it.

## Team plan form answers (due Oct 14)

Paste these into the [team plan form](https://dashboard.all-ai-network.org/s/V28NHK?d=1ff0683a-39d7-4302-a363-0835ca390c98). Fill the bracketed parts. The organizers call it "a short resource request, not a contract", so specific beats long.

**Team name and members**

&#91;Team name\] — \[Name 1, school\], \[Name 2, school\], \[Name 3, school\], \[Name 4, school\]

**Dataset**

Dataset 2: Fluid Mixing Station 3 (with the Datasets 1–2 digital twin).

**Problem we plan to solve**

When the station changes recipes, residue in the shared mixing path discolors the first vial of the new batch (e.g. Recipe 7 blue after Recipe 6 orange comes out green). The Teledyne check compares color against a reference database, so it cannot tell whether a vial matches its intended recipe, and it gives no warning or cause. We will build a system that (1) flags risky recipe transitions before the fill, using recipe sequence and dispense order; (2) checks each filled vial from the `vial_fill` camera against the color expected for its recipe; and (3) explains the likely cause in operator language using Cosmos Reason. We will train on synthetic data rendered from the Isaac Sim digital twin, evaluate with leave-one-recipe-out on the 30 labeled real vials, and report false alarms and misses separately against a simple color-threshold baseline. Goal: a supervised live test on the CSI line.

**Data needed beyond what is provided, and why**

1. One recorded run (or access to the next scheduled run) with a planned recipe sequence that includes at least 4 color changes (e.g. orange → blue, blue → clear-heavy, clear → orange), 3 vials per recipe, all three cameras, with recipe ID and fill start time per vial. Why: a held-out real test set covering transitions not in the current 10 recipes.
2. Current tank contents/colors on the test day. Why: our expected-color model depends on what is loaded in T-100, T-200 and T-400.
3. A supervised live-test slot in week 4 (target Oct 27–30). Why: judges require a demo on CSI hardware.

**Compute**

| Resource | Workload | Hardware | Est. hours | Est. cost |
| --- | --- | --- | --- | --- |
| Brev | Learning the Isaac Sim workflow, then rendering synthetic vial images from the digital twin | RTX PRO 6000 (L40S fallback) | \~40 h | \~$240 |
| Brev | Train the vial color/fill model on synthetic images | L40S | \~15 h | \~$30 |
| Brev | Cosmos 3 Nano Reasoner on our own GPU (NIM container, \~17 GB GPU memory): every Cosmos call our code makes, since build.nvidia.com offers the browser playground and a self-host container for Cosmos 3, not a documented hosted API | L40S | \~20 h | \~$40 |
| Brev | Disk storage while instances are stopped | — | \~3 weeks | \~$10 |
| Brev | Buffer for beginner mistakes (failed runs, one forgotten instance) | — | — | \~$80 |
| build.nvidia.com | Cosmos 3 Nano Reasoner browser playground (testing prompts by hand) and the NVIDIA API key that downloads the Cosmos container | Free | — | $0 |
| UWM DGX Spark or MSOE GB10 | Training/inference once access opens; live-demo box | 1 system | as available | $0 |
| CSI workstation | Not needed unless mentors recommend the Emulate3D twin | — | — | — |

**Brev credits requested: $400** (expected range $300–500). Nobody on our team has written code before, so we budgeted extra GPU hours for learning and failed runs. We will stop instances after every session, log GPU, hours and credits per run, and post weekly usage so sponsors can rebalance.

**AI-agent tools/credits**

None of us has coding experience, so every line of code will be written by coding agents that we direct in plain English and check by running. We use two agents only: **Gemini** (Gemini 3.7 Flash, free; students also claim the free Google AI Pro year) for everyday building, and **Claude Code** for the hardest parts (headless Isaac Sim scripts on a remote Linux machine, debugging, and reviewing anything that produces a number for judges). We request one $100/month Claude Max plan for \[sim lead\] and three $20/month Claude Pro plans for \[names\] building the baseline, evaluation and dashboard. Free Gemini limits will not cover beginners leaning on an agent for every task in weeks 2–3. Both agents read the same project rules from our repo (GEMINI.md, which CLAUDE.md imports).

**Expected total cost (for us, not the form)**

| Item | Likely amount | Who pays |
| --- | --- | --- |
| Brev GPU credits | \~$400 (range $300–500) | Sponsor credits, if granted |
| Claude plans for one month: 1× $100 Claude Max + 3× $20 Claude Pro | $160 | Requested from organizers |
| Gemini + Google AI Pro student year | $0 | Free (card required; cancel before renewal at $19.99/month) |
| Cosmos playground on build.nvidia.com, DGX Spark / GB10 | $0 | Free |
| Worst case if organizers grant no agent plans | $0–80 | Us: stay on Gemini, or buy Claude Pro for 1–4 people for one month |

Do not run the coding agent on pay-per-token Claude API billing. One long agent session can use millions of tokens, so a flat-rate plan is far safer for beginners. Claude Code is included in Claude Pro and Max; both have rolling usage limits, so Pro users save Claude for hard problems and reviews and let Gemini do routine work.

**Mentor support wanted**

We are complete beginners at coding; a 30-minute walkthrough of Brev + the Isaac Sim launchable with a mentor in week 1 would save us the most time.

- Isaac Sim / Replicator: making the twin's liquid color and fill level controllable, and matching real camera lighting.
- Cosmos Reason prompting for multi-image cause explanations.
- A CSI contact to confirm recipe/tank state on test days and schedule the live test.

**Questions for organizers**

1. Can we read live frames from the `vial_fill` camera during a supervised test, or should we bring our own camera aimed at the same station?
2. Is the recipe queue / Batch Scheduler state available in real time (read-only), or should operators enter the upcoming recipe manually?
3. When will the DGX Spark / GB10 access instructions and the held-out real test set be released?
4. Can we use the 30 labeled vials for few-shot prompts (in-context examples), as long as evaluation stays leave-one-recipe-out?
5. Is there a hosted API endpoint for Cosmos 3 Nano Reasoner? Its build.nvidia.com page shows only the playground and a self-host container, so we plan to run the NIM on a Brev L40S (or a GB10 once access opens).

## The tools, in plain English

You need three of the listed tools: Brev, Isaac Sim and Cosmos Reason. Everything else on the resources page is optional or for other datasets.

| Tool | What it actually is | Do we need it? |
| --- | --- | --- |
| [Brev](https://brev.nvidia.com/) | Rent-a-GPU website. You click a "launchable" (a pre-installed Linux machine), it boots in \~10 min, and you SSH into it with `brev shell`. Credits drain every minute it runs. | **Yes** — it is where Isaac Sim runs. Each team is its own Brev org; the captain gets the sign-up link. |
| [Isaac Sim](https://brev.nvidia.com/launchable/deploy/now?launchableID=env-35JP2ywERLgqtD0b0MIeK1HnF46) | NVIDIA's 3D robot/factory simulator. The organizers' digital twin of the fill and cap/seal stations is a USD file it opens. Its **Replicator** module renders thousands of labeled images while randomizing color, fill level, lighting and camera. Runs headless on Brev: no GUI, you drive it with Python scripts and copy images back. | **Yes** — rules say train on twin data, not real data. This is our training-data factory. |
| Cosmos Reason 3 ([Nano Reasoner on build.nvidia.com](https://build.nvidia.com/nvidia/cosmos3-nano-reasoner)) | A vision-language model: send it images + text, it answers in text ("Vial 7 is green; recipe says blue; prior recipe was orange → carryover"). [Try it free in the browser playground; our code calls our own copy (a NIM container) on a Brev GPU, which the NVIDIA API key lets us download](https://build.nvidia.com/settings/api-keys). Edge = single image, Nano = multiple images/video. | **Yes** — this is our "Physical AI model" and the explanation engine. Playground for prompt tests, a Brev L40S for code. |
| Cosmos video generation (C2.5T launchable) | Generates synthetic videos. \~$17/hr. | **No.** Too expensive for what we need; Isaac Sim covers synthetic data. |
| DGX Spark (UWM) / Dell GB10 (MSOE, via Rosie) | Desk-sized NVIDIA AI computers, 10 per school, free to us. Access instructions not released yet. | **Nice to have** — use for training and as the live-demo box once open. |
| build.nvidia.com | NVIDIA's model catalog: free browser playgrounds, API keys, and the self-host (NIM) instructions. | **Yes** (for Cosmos Reason). |
| NeMoClaw, NuRec, TAO, Kumo-TS, Emulate3D | Agent framework, 3D reconstruction, NVIDIA training toolkit, time-series models, Rockwell's twin tool. | **No** for now. Revisit Kumo-TS only if tank-level time series becomes available. |
| Coding agent (Gemini first; Claude Code for hard problems) | AI that writes and runs code in your terminal. The organizers say Gemini 3.7 Flash solved every problem in their tests. | **Yes** — since none of us codes, the agent writes all code, including the Isaac Sim scripts on the Brev box. Bring in Claude Code when Gemini gets stuck and to review anything that produces a number for judges. We no longer plan to use Codex or GPT-6 Astra. |

One Brev rule to tattoo on everyone: **Stop the instance when you finish a session.** Stop keeps the disk; Delete wipes it. Only pick environments that offer Start/Stop, prefer AWS, and prefer an RTX PRO 6000 (about 2× an L40S per hour, but faster).

## Setup, step by step

New to all of this? The detailed, click-by-click version with prompts to copy is in Beginner playbook.

Everyone does part A today. One person (the "sim lead") does part B once the Brev link arrives.

**A. Everyone (by Oct 13)**

- [x] Create an [ALL AI Network account](https://dashboard.all-ai-network.org/j/L36HEH) with your university email; MSOE/UWM students are auto-placed on their team.
- [x] Connect GitHub from your profile and accept the team repo invite.
- [x] Join the [hackathon Slack](https://join.slack.com/t/rockwellnvidi-wq82211/shared_invite/zt-4bp05nsn9-UW3afFtM9wjzWtZiQoJBHg); follow #hackathon-announcements and #dataset-2-fluid-mixing.
- [x] Download the [Fluid Mixing dataset](https://drive.google.com/drive/folders/1qwV2BEz3ODX17kwNCr9M15DfkY8U_blQ?usp=sharing) and the [digital twin](https://drive.google.com/file/d/1nXRN_VZ_DKGS33jtELwn6z8WR8dbQfKe/view?usp=sharing); confirm you can open a video and the labels.
- [ ] Create an [NVIDIA API key](https://build.nvidia.com/settings/api-keys) and try the [Cosmos 3 Nano Reasoner](https://build.nvidia.com/nvidia/cosmos3-nano-reasoner) in the browser with the Recipe 7 vial images.
- [x] Install the Antigravity CLI (`curl -fsSL https://antigravity.google/cli/install.sh | bash`, or the PowerShell line on Windows), run `agy`, sign in. Students: claim the free year of [Google AI Pro](https://one.google.com/ai-student) (set a reminder to cancel). Claude plan holders also install Claude Code (Windows PowerShell: irm https://claude.ai/install.ps1 | iex; Mac: curl -fsSL https://claude.ai/install.sh | bash), then run claude in the repo folder and sign in.

**B. Sim lead: first Brev session (aim for under 2 hours, \~$12)**

1. Open the Brev org sign-up link the captain receives; sign in.
2. Open the [Isaac Sim + Isaac Lab launchable](https://brev.nvidia.com/launchable/deploy/now?launchableID=env-35JP2ywERLgqtD0b0MIeK1HnF46). Pick RTX PRO 6000 (else L40S), an AWS environment, and one that shows Start/Stop. Launch.
3. Wait \~10 minutes. If the page doesn't update, click **Compute**; your instance appears there. Click its card for connect instructions and install the Brev CLI it shows.
4. From your laptop: `brev copy /path/to/digital_twin.zip <instance-name>:/home/ubuntu`
5. Connect: `brev shell <instance-name>`, then `unzip` the twin.
6. Install a coding agent on the instance (Antigravity, or Claude Code: `curl -fsSL https://claude.ai/install.sh | bash`). Over SSH it prints a sign-in link; open it on your laptop.
7. Ask the agent: *"Load the fill-station digital twin in Isaac Sim headless, render 10 images from the vial\_fill camera, and tell me where they are saved."*
8. Copy results back: `brev copy <instance-name>:/home/ubuntu/<output-folder> ~/Downloads`. Compare against real `vial_fill` frames.
9. Push your scripts (not images, not keys) to the team repo.
10. **Stop the instance in the Brev console.** Log GPU, hours and credits in the team spreadsheet.

**C. Building with an agent when nobody codes**

Your job is not to write code. It is to describe what you want, run what the agent gives you, and check the result with your own eyes.

1. Make one project folder in the team repo. *The repo already has GEMINI.md (read by Gemini) and CLAUDE.md (read by Claude Code; it pulls in GEMINI.md), holding our goal, this plan, the playbook, the folder layout and the rules. Agents read them every session, so they stay on track. When the plan changes, ask the agent to update GEMINI.md and the copies in docs/*.
2. Ask for one small, checkable thing at a time: *"Write a script that opens video 5, saves one frame every 2 seconds to frames/, and prints how many it saved."* Not "build the whole system".
3. Always ask how to run it and what you should see: *"Explain in plain English what this does and give me the exact command to run it."*
4. Check the output yourself: open the images, read the numbers. If something is wrong, paste the full error back and say what you expected.
5. After anything works, ask the agent to commit it with a clear message. Small saves mean you can always go back.
6. When the agent loops on the same error three times, stop. Start a fresh session, paste the error and GEMINI.md, or hand that one problem to Claude Code.
7. Ask "why" often. Judges will ask how your system works, and "the AI wrote it" is not an answer. Each person should be able to explain their part.

Tip: let the agent write a `RUNBOOK.md` with every command that worked. It becomes your setup guide, your demo script and half your one-page summary.

Stuck? Post in #compute-questions and tag Dan Schneider (NVIDIA). Start the first line with "BLOCKING" if it stops the team, plus what you tried and the error.

## Technical approach

Three small modules beat one giant model: each one is measurable on its own, and the baseline is easy to beat in a visible way.

*(Diagram in the online doc: system architecture · 3 modules, 1 dashboard.)*

Real camera frames are only ever inputs and test data; the vial model learns from the twin's synthetic images.

**0. Baseline first (week 1, no GPU).** Crop the vial in `vial_fill` frames (fixed camera, so a fixed box works), average the color in HSV/Lab, and nearest-neighbor it to each recipe's "true" color (the last vial of each recipe is clean). Score with leave-one-recipe-out on the 30 labeled vials. This number is the bar every later step must beat, and judges explicitly want "results against a baseline".

**1. Transition risk + flush decision (before the fill).** Two things can tint a vial, and the model scores both:

- **Line carryover (the main, documented problem):** the previous recipe's mixture left in the shared mixing path tints the first vial after a change, then clears.
- **Nozzle buildup (our hypothesis, probably smaller):** dye film or drops on the nozzle that accumulate over fills and idle gaps. Most likely to matter for pale, clear-heavy recipes.

The model works in **dye amounts, not colors**, because dyes do not mix linearly in appearance. The same contamination shifts a pale, clear-heavy vial far more than a dark one, and opposite hues (orange into blue) change the hue itself, to green or brown, which is the most visible kind of error. Each dye is also tracked separately, because orange and blue have different tinting strength.

```latex
\mathbf{c}_{\text{vial}} = \frac{V_{\text{next}}\,\mathbf{c}_{\text{next}} + V_r\,\mathbf{c}_{\text{prev}} + \mathbf{n}}{V_{\text{next}} + V_r}, \qquad \Delta E_{\text{pred}} = \Delta E_{00}\big(g(\mathbf{c}_{\text{vial}}),\; g(\mathbf{c}_{\text{next}})\big)
```

- **c** = (orange share, blue share) of a vial, read straight from the recipe: 10 mL orange in 40 mL total = 0.25 orange, 0 blue.
- **V\_r** = residue volume in the line, fitted from the Recipe 6 → 7 case (orange before, blue intended, green out).
- **n** = nozzle load per dye (orange load, blue load). Each fill adds a little of the dyes it dispensed, the load fades over later fills, a flush resets it to 0. It starts at 0 and is switched on only if the data shows drift.
- **g** = a calibrated map from dye amounts to the color the camera sees (CIELAB), fitted on the 10 recipes' clean vials and on twin renders. This one map captures the pale-vs-dark sensitivity and the hue shifts; nobody hand-codes them.

| Predicted ΔE (CIEDE2000) | Action |
| --- | --- |
| below \~2 | Proceed |
| \~2 to \~5 | Proceed and flag the vial, or flush if a scrapped vial costs more than a flush |
| above \~5 | Flush, or reorder the queue |

The 2 and 5 cut points are starting values from common color-tolerance practice (ΔE ≈ 2 is about one just-noticeable difference). Calibrate them to the ΔE at which the Teledyne check rejects, and to CSI's real cost of a scrapped vial versus a flush.

**Dispense order** matters through carryover, not the final mix: fully mixed dyes give the same color in any order, but order sets what passes through the shared path last. The order here is fixed (T-200 → T-400 → T-100). Recipe 6 sent clear through last and vial 7 still turned green, so the residue is the previous mixture, not just the last fluid out. Measure color only after the labeled fill end time.

**Testing the nozzle hypothesis:** plot each vial's color error against fill count and idle time, pale recipes and dark recipes separately. Drift on pale recipes → fit **n** (a finding the organizers did not describe). No drift → report it as measured and negligible. Ask CSI in #dataset-2-fluid-mixing whether the tanks hold dissolved dyes or pigments: pigment particles cling and build up far more.

**What the operator sees:** a risk light per transition and the cheapest fix, either a clear flush (≥ 10 mL from T-100, never T-300, only with the plant manager's approval) or a reordered queue (orange → clear-heavy → blue splits one big jump into two small ones at zero cost). The system recommends; people act. Business-case number: fluid and cycle time saved versus flushing at every change, at the same or lower defect rate.

**Tank-color reader (feeds module 1).** The control system knows tank numbers, not colors, and tanks can be refilled with a different color. A reader on the existing `tank_level` camera identifies the dye in T-100, T-200 and T-400 at the start of each batch (T-300 ignored): fixed boxes over each tank, average color first, Cosmos Reason only when the color math is unsure. Its output replaces the assumed "T-200 = orange" list in the flush model and warns when a tank no longer matches what the recipes assume, so predictions stay correct through a changeover. The organizers list this exact idea as a starter question. Constraints: read-only footage, no camera or tank changes by us, no training (the twin has no tanks), and tank color only identifies the dye; the calibrated map g still predicts vial color, since liquid looks darker in a tank than in a vial.

**2. Vial check (after the fill).** A small classifier (e.g. ResNet-18 or a color-regression head) trained only on Isaac Sim renders of the twin's `vial_fill` camera, randomized over liquid color, fill level (10–80 mL), lighting, glare, and slight camera jitter. Tested on real vials. Report false alarms and misses separately. Compare real-only (few-shot), synthetic-only, and synthetic + few-shot, as the data-collection guide recommends.

**3. Explanation (Cosmos Reason).** Send Cosmos 3 Nano Reasoner the current vial crop, the reference image of the intended recipe, the previous recipe, the dispense order, and the module 1–2 outputs. It returns a one-paragraph cause and action for the operator. Evaluate explanations separately: does the stated cause match the known prior recipe?

**Inference cascade (cheap math first, AI only when needed).** Every vial goes through the cheapest step that can decide it; Cosmos is called only to explain a problem, never to detect one.

| Step | What runs | Cost per vial | Runs on |
| --- | --- | --- | --- |
| 1. Before the fill | Flush formula above | A few arithmetic operations | Every recipe change |
| 2. After the fill | Plain color + fill-level measurement of the vial crop | Milliseconds, any computer | Every vial |
| 3. Unsure zone | Twin-trained vial model | Milliseconds on a local GPU, no tokens | Borderline vials only |
| 4. Flagged vial | Cosmos Reason explanation | The expensive call | Flagged vials only, and only when formula and camera disagree or the transition pair is new |

Explanations are cached per previous → next recipe pair, so a repeat of "blue after orange came out green" reuses the text. Each cheap step has an "unsure" band that hands off to the next step, so a confident wrong formula cannot silently pass a bad vial. Report: share of vials reaching Cosmos, latency per vial, and accuracy of the cascade versus sending every vial to Cosmos. Frame it for judges as Physical AI where it adds value (the twin trains step 3; Cosmos reasons in step 4), not as "less AI".

**Operator dashboard.** A simple web page (Streamlit or plain HTML) showing the queue, a red/amber/green risk light per transition, each vial's check result, and the Cosmos explanation. This is what the judges watch in the video.

**Twin caveat to plan around:** the organizers say the twin's liquid color is only approximate and the tanks are not modeled. Week 2's first job is to calibrate rendered colors against real clean vials (the last vial of each recipe) so synthetic and real live in the same color space.

## Schedule and roles

The plan works backward from one fixed point: a live CSI test in the last week of October, so the video shows real hardware before the Nov 1 deadline.

*(Diagram in the online doc: team timeline · Oct 12 to Nov 5.)*

Work streams overlap on purpose: the baseline and data audit unblock everyone, then synthetic data and the risk/Cosmos work run in parallel.

**Done when (end of each week)**

1. Week 1 (Oct 12–18): team plan submitted; baseline accuracy on the 30 labeled vials, leave-one-recipe-out; frames from all 3 cameras aligned by timestamp; first twin render on Brev; every teammate has finished one small task with a coding agent from prompt to commit.
2. Week 2 (Oct 19–25): 2,000+ calibrated synthetic vial images; vial model beats baseline on real vials; Cosmos explains the Recipe 6 → 7 case correctly; CSI test requested.
3. Week 3 (Oct 26–Nov 1): risk score + dashboard end to end; live test run and logged; video and one-pager submitted Nov 1.
4. Finals week: rehearse the 5-minute talk twice; have a recorded backup of the live demo.

**Progress so far (Oct 13):** Card 1 (data inventory, contact sheet of 12 frames) and Card 2 (all three cameras matched to each vial's fill end by timestamp, plus a time-gap histogram for every camera) are done. The scripts are in `scripts/`; the commands are in RUNBOOK.md; the plain-English story of what we did and why is in `docs/PROGRESS.md`. Next up: Card 3, the baseline color check.

| Role | Owns (by directing a coding agent) | Pick the person who |
| --- | --- | --- |
| Captain / PM | Team plan, Slack requests, CSI test scheduling, business case, video script, weekly credit log | Communicates best and stays organized |
| Sim lead | Brev instance, Isaac Sim twin renders, color calibration; gets the $100 plan if granted | Is most patient with trial and error |
| Model + evaluation lead | Baseline color check, vial model, leave-one-recipe-out results table | Likes numbers and spreadsheets |
| App + Cosmos lead | Flush/risk rule, Cosmos prompts, operator dashboard, live-demo setup | Likes design and explaining things |

Fewer than four people: the captain also takes the risk model, and the ML lead takes the dashboard.

## How to win

The teams that win these are the ones with a live demo, a number that beats a baseline, and an honest failure slide. Polish matters less than proof.

**Judging checklist (from the event page plus the organizer's four criteria)**

- [ ] Live on real hardware: a recorded supervised test at CSI, with the trial log (every attempt, not just successes).
- [ ] Specific problem: "first vial after a color change is off-recipe and the current check can't tell".
- [ ] Business case: cost of a scrapped vial/batch × changeovers per shift; savings from a flush or reorder suggestion; adoption cost (one camera already exists, a GB10-class box, zero PLC changes). Ask CSI or mentors for realistic scrap/changeover numbers; never invent them.
- [ ] Measured results vs baseline: detection precision/recall, false alarms and misses separately, explanation accuracy, latency per vial.
- [ ] Where it still fails: e.g. near-identical colors, glare, recipes with no clean reference.
- [ ] Physical AI + NVIDIA compute visible: Isaac Sim twin renders, Cosmos Reason, GPU hours and credits logged.

**The ≈5-minute video**

1. 0:00–0:40 — The problem: real footage of green vial 7 in a blue batch; why the Teledyne check misses it.
2. 0:40–1:30 — The idea: twin → synthetic data → check + risk + explanation (show the architecture picture).
3. 1:30–3:00 — The live CSI demo: dashboard warns before the change, flags the bad vial, Cosmos explains it.
4. 3:00–4:00 — Results table vs baseline, plus real-vs-synthetic comparison.
5. 4:00–5:00 — Business case, adoption steps, failures, next steps.

**Pitfalls that sink teams**

- Training on the real images (explicitly against the rules' spirit). Use them for testing, calibration and few-shot prompts only.
- Leaving Brev running overnight. One forgotten RTX PRO 6000 night can burn a quarter of the budget.
- Requesting the CSI live test late. Ask in week 2, test in week 4.
- Changing recipes or touching equipment. Never: observe, and only act with the plant manager's approval. Respect the limits (≤ 80 mL per vial, ≤ 50 mL from T-200, never T-300).
- Random train/test splits. Neighboring frames are near-duplicates; split by recipe or run.
- Committing datasets, checkpoints or API keys to GitHub.

Use the Slack channels openly: mentors (Brett Storoe, Dr. Derek Riley, Tanner Cellio) see your questions in #dataset-2-fluid-mixing, and being visible to the judges' own companies before finals doesn't hurt.

## Sources

- [Innovation Lab overview](https://msoe-maic.com/library/?article=Rockwell-NVIDIA-Fall-2026)
- [Dataset 2: Fluid Mixing Station](https://msoe-maic.com/library?article=Rockwell-NVIDIA-Fall-2026-Fluid-Mixing)
- [Compute: Brev, DGX Spark, build.nvidia.com](https://msoe-maic.com/library?article=Rockwell-NVIDIA-Fall-2026-Compute)
- [Tools and resources](https://msoe-maic.com/library?article=Rockwell-NVIDIA-Fall-2026-Resources)
- [Collect and test your own data](https://msoe-maic.com/library?article=Rockwell-NVIDIA-Fall-2026-Data-Collection)
- [Coding agents](https://msoe-maic.com/library?article=Rockwell-NVIDIA-Fall-2026-Coding-Agents)

Claude plan prices (Pro $20/month, Max $100/month, Claude Code included) come from third-party pricing guides; check [Claude pricing](https://claude.com/pricing) before buying. The Cosmos 3 request format, model name and container come from NVIDIA's [Cosmos 3 Reasoner cookbook](https://github.com/NVIDIA/cosmos/tree/main/cookbooks/cosmos3/reasoner).

Brev rates are the organizers' planning figures; check the live rate in the Brev console before launching.

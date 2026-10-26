# Submission and judging: what the organizers ask for, and where we stand

Summary of the organizers' "Submission and Judging Details" (received Oct 26), followed by how our project answers each point. Update the right-hand column as work lands. Never fill a gap with an invented number.

**Deadline:** Sun **Nov 1, 11:59 PM CT**, submitted on the event website. Aim to submit by the early evening.
**After:** judges invite teams to an **oral** or **poster** presentation; accept the invitation by **Nov 4**. Finals **Nov 5, MSOE Diercks Hall**: 4 PM poster setup (atrium), 4:30–6:15 PM orals (auditorium), 6:30–8 PM posters and networking.
**Judges:** Dr. Tomasz Kornuta, Poonam Chitale, Joe Hamann, Dr. Chris GauthierDickey, and Rockwell representatives.

---

## 1. Video (about 5 minutes)

| The organizers ask the video to… | What we have | Gap |
| --- | --- | --- |
| Showcase the project | Dashboard replay of video 5 (Card 10); twin showcase video (Card 7) | Cosmos explanations in the dashboard (Card 9 → Card 10 step 10) |
| **Demonstrate the solution operating on the hardware in the CSI** | Nothing yet: all our footage is the supplied recording | **A CSI session.** Realistic version: CSI runs a planned recipe sequence, we observe, and process that recording with our system the same day. Needs a "new recording" mode in the dashboard and fresh reference vials under that day's lighting |
| Identify the specific problem and why it matters | Vial 7 (green in a blue batch); the Teledyne check only knows known/unknown colors | Script the 40 seconds |
| Explain impact on other manufacturers / generalization (scrap, rework, downtime, labor, other) | The mechanism (a shared path that carries the last product into the next) is common to any line that changes colors or products through shared piping | Real cost numbers only from CSI or mentors; otherwise describe the impact in kind (scrap avoided, flushes only when needed), not in invented dollars |
| Show measured results against a baseline and where it falls short | Card 3 baseline; Card 3b (color check beat every Cosmos version); Card 4 advisor (rank correlation 0.79–0.82); blank normalization; Card 7 lighting test; Card 8 (twin-trained model did not beat the color check: tall vials 8/8 vs 5/8 or 4/8; small vials 3/3 vs 1/3) | One results table for the video; the honest-limits slide (small vials, one judge, side lighting, 30 vials, one run) |

## 2. Executive summary (1 page)

Short summary of goals, data collected/generated and approach, answering:

| Question | Our answer, with evidence | Gap |
| --- | --- | --- |
| What problem(s) are you solving in manufacturing? | Off-recipe first vials after a recipe change (carryover through one shared pipe and nozzle); no warning, no "matches its recipe" check, no cause | — |
| How does your project use Physical AI? | Isaac Sim digital twin: calibrated renders for appearance variation and a twin-trained model tested on real vials, which did not beat the color check (Cards 6–8). Cosmos Reason: tested against color math (Card 3b) and used to explain flagged vials (Card 9) | Card 9 results |
| **How did you use the physical equipment in the CSI?** | The supplied recordings of Station 3 | **The CSI session** (see the video gap) |
| What evidence demonstrates that the problem is solved? | Card 3 (8/8 tall carryover vials caught, 0 false alarms on one judge's key), Card 4 (risk ranking), dashboard end-of-run table, Card 7 lighting test | CSI trial log; final results table; Claude review (`REVIEW.md`) |
| Links to supporting material | GitHub repo: `docs/PROGRESS.md` (the reasoning), `RUNBOOK.md` (every command), `PLAN.md` | Make sure the repo's README points to these |

## 3. Judging criteria and where we answer them

| Criterion | Where we answer it |
| --- | --- |
| Alignment with a grounded manufacturing problem | Problem statement; the organizers' own dataset description; gap list sent to the organizers |
| Effectiveness and validation of the solution | Answer key locked before scoring; leave-one-recipe-out; prompts frozen before results; held-out recipes in the twin calibration |
| **Physical operation and reliability** | **CSI session trial log** (every attempt, not only successes); dashboard never depends on Cosmos to make a decision; "lighting changed" warning |
| Engineering practicality | Runs on a laptop with the existing camera; color math takes milliseconds; Cosmos only for flagged vials; no PLC changes |
| Value to the manufacturing industry and generalizability | Any line with color or product changes through shared paths; the advisor only needs clean reference vials of each recipe |
| Broader impacts | Less scrap and fewer unnecessary flushes (fluid and time); honest about what it can't yet do |

## 4. Priorities this implies (Oct 26)

1. **CSI session**: ask today for a slot this week and access to the `vial_fill` recording (or live feed). It is an explicit video requirement and a judging criterion.
2. **"New recording" mode** for the dashboard, plus fresh references and the lighting warning, so a CSI recording can be processed on the day. Plan: `PLAN.md`, "New-recording mode for the CSI session".
3. **Card 9** (Cosmos explanations) → dashboard panel 3.
4. **Submission package**: video, one-page summary, results table, references; Claude's review before submitting.
5. Card 8 is done (Oct 26). Track B (twin mixing fix) only if time remains.

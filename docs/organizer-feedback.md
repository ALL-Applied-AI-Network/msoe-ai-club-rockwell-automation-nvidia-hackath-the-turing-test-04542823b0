# Organizer feedback on our team plan

Received after we submitted the team plan (Oct 14, 2026). The feedback is copied word for word below, followed by what each point changes in our plan.

---

## The feedback (verbatim)

> Thank you for submitting your team plan to the 2026 Physical AI for the Factory Floor Hackathon sponsored by Rockwell Automation and NVIDIA.
>
> Organizers reviewed your proposal and have some feedback for your team in these areas:
>
> **Problem/focus**
>
> Warning about risky recipe changes, checking the filled vial, and explaining the likely cause are great areas to target.
>
> Compare straightforward color/fill measurements with an in-context Cosmos approach before committing to model training. Ground explanations in the current and previous recipes and physical camera evidence. The twin approximates liquid color and does not include the tanks, so distinguish synthetic appearance variation from an accurate simulation of carryover.
>
> **Data needs**
>
> Please review the supplied synchronized recordings and the labeled 30-vial, 10-recipe sequence; fill timestamps and recipe volumes are already provided for that labeled portion. Identify the transitions or metadata that remain missing.

---

## What it changes

| # | What the organizers said | What we do about it |
|---|---|---|
| 1 | Our three goals (warn, check, explain) are the right focus. | Keep them. No change in scope. |
| 2 | Compare plain color/fill measurements with an **in-context Cosmos** approach **before** committing to model training. | New **Card 3b**: on the same 30 vials and the same answer key as the Card 3 baseline, ask Cosmos whether each vial matches its recipe, giving it the vial image, a clean reference image of the intended recipe, and the current and previous recipe as text. Example vials in the prompt come from other recipes only (leave-one-recipe-out). We compare its score with the color-math baseline **before** starting Cards 7–8 (twin-trained vial model). Training goes ahead only if neither approach is good enough. |
| 3 | Ground explanations in the current and previous recipes and the physical camera evidence. | Every Cosmos explanation (Card 9) must state the intended recipe, the previous recipe and what the camera shows (the vial's measured color against the reference, with the frame used). Version C of the A/B/C experiment becomes the default; A and B stay as comparisons. |
| 4 | The twin approximates liquid color and has no tanks, so separate "synthetic appearance variation" from "accurate simulation of carryover". | The twin is used **only** for appearance variation: lighting, glare, fill height, color range, camera jitter. We never claim it simulates carryover. How much carryover happens (residue volume `V_r`, which vials are affected) comes from the **real** recipe transitions in video 5, not from renders. |
| 5 | The 30-vial, 10-recipe labeled sequence with fill times and volumes is already provided; identify which **transitions or metadata are still missing**. | Our data request duplicated what's supplied. Replace it with a concrete gap list (below) and post it to the organizers. |

---

## Gap list: what the supplied data does and doesn't cover

**Already supplied (video 5):** 30 vials, 10 recipes (5–14), 3 vials each, fill start/end times (in mp4 seconds) and tank volumes per vial, three synchronized cameras.

**Data issues we found and can report** (not missing, but needed to use the data correctly):
- The mp4 files play 1.2158× faster than real time (camera ~24.68 fps, files say 30 fps). Label `start_s`/`end_s` are mp4 seconds, while still-image timestamps and `video_s` in `video5_frame_labels.csv` are real time, so the frame labels put stills under the wrong vials. Conversion: real_s = 1.215771 × mp4_s (see `scripts/time_base.py`).
- The still images stop at 20:15:27, so vials 26–30 exist only in the mp4s.

**Still missing (to confirm and list precisely):**
1. **Transitions not covered.** Video 5 has exactly 9 recipe changes (5→6, 6→7, …, 13→14), each seen once, all in one direction. A table of which color changes these are (e.g. orange → blue) will show which risky ones never occur, such as blue → orange, dark → pale and clear-heavy → dark, plus any repeat of the same change.
2. **The recipe before vial 1**, so vial 1 can be judged (it differs from vials 2–3).
3. **Recipe sequences for videos 1–4** (recipe ID per vial), which would add labeled vials and transitions.
4. **Tank contents per video** and whether the tanks hold dissolved dyes or pigments (affects the nozzle-buildup hypothesis and the tank reader).
5. **Flush events and long idle times**, if any happened during the recordings.
6. **The Teledyne check's pass/fail result per vial**, which would give an independent answer key for scoring.

**Next step:** build the transitions table from `video5_vial_recipes.csv` (previous recipe → next recipe, tank volumes of each, dominant dye before and after), confirm the list above, and have the captain post it to the organizers.

# Carryover Copilot: One-Page Summary

## 1. What problem are we solving?
On Fluid Mixing Station 3, every recipe flows through one shared pipe and nozzle, so leftovers from one recipe end up in the next vial. When an orange recipe was followed by a blue one, the first blue vial came out green. The station's Teledyne check only asks whether a color is familiar: it can't tell whether a vial matches *its own* recipe, why it's off, or warn beforehand.

**Carryover Copilot** does all three. It gives each recipe change a red, amber or green risk light before the fill, checks every vial against a clean reference of its own recipe with the existing camera, and shows a reviewed explanation for flagged vials.

## 2. How do we use Physical AI?
Color math makes every pass/fail decision; AI is used where it measurably helps.
- **Isaac Sim digital twin:** under ±30% lighting changes we couldn't create on the real line, comparing each vial with the empty vial beside it cut false alarms from 8 of 8 to 2 of 8. A twin-trained model caught 5 of 8 bad vials, against 8 of 8 for color math.
- **Cosmos Reason:** as a detector, it caught 5 of 8 with 3 false alarms. As an explanation writer, 1 of 8 drafts was fully correct, so a person approves each one before operators see it.

## 3. How did we use the CSI equipment?
On October 30, CSI's operator ran a ten-recipe order we designed on Station 3. We photographed the advisor's prediction before the first fill. From the recordings alone, the system found all 10 filled vials, and its predicted risk ranked the measured color shifts with a Spearman correlation of 0.95 across 9 new recipe changes. Each recipe ran once, so there was no clean same-day vial and pass/fail could not be scored.

## 4. What evidence shows it works?
- **Inspection:** 8 of 8 discolored tall vials caught, 0 false alarms, against an answer key locked before scoring.
- **Prediction:** risk ranking matched measured carryover (Spearman 0.79–0.82 on the supplied recording, 0.95 at CSI).
- **Practicality:** about 0.7 ms of math per vial on a laptop, the existing camera, no PLC changes.

## Value beyond this station
Paints, inks, beverages and liquid pharmaceuticals share this first-unit problem wherever products share one pipe. Setup needs a camera, an ordinary PC and three fills per recipe (costs: `docs/business-case.md`).

## Where it falls short, and what's next
One recording and one short CSI session, one human judge, few small vials; light from one side still fools the check, and Cosmos explanations need review. Next: live camera reading and a CSI session with three vials per recipe.

**More detail:** [`docs/PROGRESS.md`](PROGRESS.md) · [`docs/results.md`](results.md) · [`docs/business-case.md`](business-case.md) · [`RUNBOOK.md`](../RUNBOOK.md)

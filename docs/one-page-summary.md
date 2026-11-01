# Carryover Copilot: One-Page Summary

## 1. What problem
On Station 3, recipe changes tint the next vial (vial 7 green in a blue batch) through a shared nozzle. Teledyne checks 'known color', not 'this recipe's color', with no cause or warning. **Carryover Copilot** warns before a risky recipe change (a red/amber/green light per change, and a reorder when it removes a red one), checks every filled vial against its own recipe's clean reference with the existing vial_fill camera, and shows a reviewed explanation of the likely cause.

## 2. How we use Physical AI
We measured where AI helps; decisions stay with color math:
- **Isaac Sim twin:** Calibrated renders varied appearance. In lighting tests (±30%), blank normalization cut false alarms from 8 of 8 to 2 of 8. A twin-trained model did not beat color math (5 of 8 or 4 of 8 caught vs 8 of 8).
- **Cosmos Reason:** In Card 3b it lost to color math (on 16 tall vials: 5 of 8 caught, 3 false alarms, vs 8 of 8 and 0). Repurposed for explanations, 1 of 8 was fully correct; a person approves each once per recipe change.

## 3. How we used the CSI equipment
On Oct 30, CSI ran our 10-recipe order on Station 3 (4 recordings, 640×480). Predictions were photographed before fill; the detector found 10 of 10 vials without labels. Predicted risk ranked measured shifts with Spearman ρ = 0.95 over 9 changes. Pass/fail couldn't be scored: with no clean same-day vial, carryover and day-to-day differences can't be separated.

## 4. Evidence it works
- **Inspection accuracy:** Video 5 tall vials: 8 of 8 caught, 0 false alarms (one judge, answer key locked first).
- **Pre-fill risk ranking:** Spearman ρ = 0.79–0.82 on Video 5; ρ = 0.95 on 9 CSI changes.
- **Engineering practicality:** The color check takes ~0.7 ms of math per vial (~75 ms including reading the frame) on a laptop, with the existing camera and no PLC changes.

## Value beyond this station
Any line that changes colored or flavored liquids through one shared path has the same problem (paints, inks, beverages, cosmetics, liquid pharma). Adoption needs a fixed camera, any PC and 3 fills per recipe for a reference; Cosmos runs once per recipe change, not per vial. Costs and the value formula: docs/business-case.md (no invented dollar figures).

## Where it falls short
One run plus one CSI session, one judge, small vials (30–40 mL), light from one side, Cosmos needs review, live camera not built.

## Next steps
Same-day references at CSI, live camera reading, more recipe changes.

**Links:** [`docs/PROGRESS.md`](PROGRESS.md) · [`docs/results.md`](results.md) · [`docs/business-case.md`](business-case.md) · [`RUNBOOK.md`](../RUNBOOK.md)

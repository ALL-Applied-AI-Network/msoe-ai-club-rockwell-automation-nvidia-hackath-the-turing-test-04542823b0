# Business case: what it costs to deploy Carryover Copilot, and whether a factory needs Cosmos

Graphs and tables for this page: [`docs/business-case-graphs.pdf`](business-case-graphs.pdf).

Written Oct 30 for the one-page summary and the video. **Rule we follow (GEMINI.md, rule 5): we never invent business numbers.** So this page separates three kinds of number:

- **Measured:** from our own results (`docs/PROGRESS.md`, `docs/results.md`).
- **Price estimate:** rough public price ranges for equipment, to be checked against a real quote before anyone relies on them.
- **Your number:** only the plant knows it (cost of a scrapped vial, cost of a flush, changeovers per shift). These stay as blanks in a formula; we fill them only with numbers CSI or a mentor gives us.

---

## 1. What the system needs, step by step

| Step | What it does | Hardware it needs | Measured |
|---|---|---|---|
| 1. Before the fill | Risk light per recipe change, reorder suggestion | Any PC | Ranks changes in the right order (Spearman 0.79 HIGH, 0.82 LOW) |
| 2. After the fill | Color check of every vial against its recipe's reference | One fixed camera + any PC (no GPU) | ~0.7 ms of math per vial; tall vials 8 of 8 caught, 0 false alarms (one judge, video 5) |
| 3. Unsure zone | Operator looks at the vial | Nothing | 2 vials of 20 in video 5 |
| 4. Explanation | Cosmos drafts an explanation once per recipe change; a person approves it | A GPU with about 17 GB of memory, **only while drafting**; can be rented | 1 of 8 drafts fully correct, so the review step is required |

**The key design fact for cost:** steps 1–3 decide everything and run on an ordinary computer. Cosmos never runs per vial: explanations are drafted once per recipe change, reviewed once, and then reused from a cache. So the GPU is a small, occasional cost, not part of the line.

---

## 2. Two kinds of factory

### Modern line (like CSI Station 3)

Already has: a fixed camera on the fill station, recipes in a batch scheduler or MES, networked PCs.

| Item | Cost type | Estimate |
|---|---|---|
| Camera | Existing | $0 (our system reads the existing `vial_fill` camera) |
| PC for steps 1–3 | Price estimate | An existing station PC, or a small industrial PC (roughly $600–2,000) |
| GPU for Cosmos drafting | Price estimate | Rent when needed: an L40S on Brev is about $2/hour (organizers' planning rate); or a desk-size box such as a DGX Spark (about $4,000 list, check current price), or a GB10-class machine the site already has |
| Reading the recipe queue | Engineering time | Read-only link to the batch scheduler, or the operator types the queue |
| Setup per camera | Engineering time | Place and check the measurement patches once (our glass-edge check flags a moved camera) |
| Setup per recipe | Product | 3 fills per recipe to get a clean reference vial (the 3rd) |
| PLC changes | None | The system only observes and advises |

### Older line (no camera, paper recipe sheets)

| Item | Cost type | Estimate |
|---|---|---|
| Camera + lens + mount | Price estimate | An industrial machine-vision camera, roughly $300–1,500 |
| Even lighting / backdrop | Price estimate | An LED backlight or white backdrop, roughly $100–500. Important: our blank normalization only cancels **even** brightness changes; light from one side fooled the check in the twin test |
| PC | Price estimate | Roughly $600–2,000 (no GPU needed) |
| Recipe input | Engineering time | The operator types the queue, or a simple sheet import |
| Everything else | Same as modern | Same setup steps, same cached-explanation approach |

The only real difference between the two is **camera, lighting and recipe input**. The software and the method are the same.

---

## 3. The Cosmos bill is mostly people, not GPUs

Cosmos is called once per **recipe change pair**, never per vial.

- A line with 10 recipes has at most 10 × 9 = **90 possible changes** (ordered pairs).
- GPU time to draft them all = 90 pairs × repeats × seconds per call. **Seconds per call:** take the measured average from `outputs/card9/explanations.csv` (seconds column). As an illustration only: at 30 s per call and 3 repeats, that is about 2.3 GPU-hours, about $5 at $2/hour.
- **Review time:** a person approves or rejects each draft once. That is the real cost (90 drafts × a few minutes each), and it is required: in our test, 7 of 8 drafts had at least one mistake and all 24 answers said "confidence: high".
- **Ongoing:** only new recipes or new pairs need drafting and review.

---

## 4. What it can save (formula; fill the blanks only with real plant numbers)

**Measured in video 5:** the color check flagged the first vial after **8 of the 9** recipe changes (all except 8 → 9), and in two pale recipes the **second** vial was flagged too (vials 5 and 29). So on this line, roughly one or two vials per recipe change come out off-color.

```
Yearly value  =  (changeovers per year)
                 × (off-color vials per changeover)        ← measured here: about 1, sometimes 2
                 × (cost of one off-color vial reaching the customer or found late)   ← your number
              +  (flushes avoided or replaced by a reorder) × (cost of one flush)      ← your number
              +  (operator minutes saved diagnosing the cause) × (labor cost per minute) ← your number
              −  (system cost from section 2)
```

**Honest note on flushes:** in video 5, the advisor rated 8 of 9 changes RED and 1 AMBER, so on this recipe mix almost every change is risky. Skipping flushes would save little here. The bigger levers are:
1. catching off-color vials before they ship, which the current Teledyne check can't do because it doesn't know the intended recipe;
2. reordering the queue when it removes a RED change (example: queue 7, 12, 8 after Recipe 6 → suggested 12, 8, 7, with 3 RED changes cut to 2).

**Where else this applies:** any line that changes colored or flavored liquids through one shared path. Paints and coatings, inks, beverages, cosmetics, liquid pharmaceuticals and chemical dosing all have the same "the last product tints the next" problem.

---

## 5. Do we, or a factory, actually need Cosmos?

**Our measured answer:** not for deciding, and not for this one failure mode.

| Question | Evidence | Answer |
|---|---|---|
| Does Cosmos need to **detect** bad vials? | Card 3b: color check 8 of 8 caught, 0 false alarms; best Cosmos version 5 of 8, 3 false alarms | **No.** The color check decides |
| Does Cosmos need to **explain** carryover on this line? | Card 9: 1 of 8 explanations fully correct; it invented causes (misrouted tubing, a cleaning solution) with high confidence | **Not on its own.** On this line almost every off vial has the same cause (leftover from the previous recipe), and the dashboard already knows the previous recipe, the measured color shift and the risk light. A fill-in-the-blanks sentence built from those facts would state the right cause every time |
| So where does Cosmos add value? | Not tested with our data | Lines with **many possible causes** that a template can't list: a tank refilled with the wrong dye, an empty tank, foam or bubbles, splashing, layering, underfill, a dripping nozzle. Cosmos can look at the image or a short video and describe something new in plain words, which color math can't |

**What we recommend to a factory:**
1. **Must-have:** the camera color check and the risk advisor. Cheap, fast, no GPU.
2. **Optional:** Cosmos as an **explanation-drafting tool**. Run it occasionally (rented GPU or a GB10/DGX-class box), always followed by a person's review, cached per recipe change. Worth it when a line has varied failure modes or many recipes; not worth it for a single, well-understood cause like ours.
3. **Never:** let Cosmos make the pass/fail decision, or show unreviewed explanations to operators.

**How to say it to the judges:** we used Physical AI where it earns its place and measured where it doesn't. The digital twin (Isaac Sim) let us test lighting changes we couldn't create on the real line. Cosmos is tested, scored and gated behind human review. The decision stays with fast, explainable color math.

---

## Numbers still needed (ask CSI or a mentor; never guess)

- Cost of one scrapped or rejected vial
- Cost and time of one flush
- Changeovers per shift or per year
- Whether a reorder is allowed in practice (who approves it)
- Measured seconds per Cosmos call (from `outputs/card9/explanations.csv`)

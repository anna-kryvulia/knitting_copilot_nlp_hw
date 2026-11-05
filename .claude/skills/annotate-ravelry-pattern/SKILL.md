---
name: annotate-ravelry-pattern
description: Turn a free Ravelry pattern the user downloaded into gold evaluation labels (gold IR, per-row stitch counts, explanation facts, chart grid) without committing the copyrighted text. Use when adding real patterns to the evaluation set.
---

# Annotate a real Ravelry pattern

CRISP-DM phase: **3. Data Preparation** (for **5. Evaluation**). Real patterns are a **Must**: they show
how the system performs on real text compared with synthetic patterns.

## Inputs
- The pattern file in `data/private/ravelry/<slug>.(pdf|txt)` (the user downloads it; free patterns only).
- The Ravelry URL, designer name, and licence/terms note.

## Steps

1. Check `data/private/` is listed in `.gitignore`. Never copy pattern text outside `data/private/`.
2. Extract the text (PDF → text with the `pdf` skill or `pypdf`) into `data/private/ravelry/<slug>.txt`.
3. Check scope: flat or in the round, single piece for the Must tier, no colourwork or short rows.
   If out of scope, record the reason and stop.
4. Write the gold IR **by hand** (with the agent drafting, the user checking every row) to
   `data/eval/ravelry/<slug>.json`:
   - `meta`: url, designer, title, licence note, date annotated, scope tags.
   - `gold_ir`: IR as in `docs/CONVENTIONS.md`, metric units (convert inches / US needles with `units.py`).
   - `gold_counts`: per-row end counts for the chosen size, checked with the simulator.
   - `explain_facts`: 3–6 key facts per section that a correct explanation must contain.
5. Run the simulator on `gold_ir`. If counts disagree with the pattern's stated counts, decide with the
   user whether it is an annotation error or a real erratum; note it (errata are useful validator cases).
6. Add the case to the eval index with `source: ravelry`, `split: test` (real patterns are test-only
   unless there are more than 10).
7. Record time spent and any difficulties in `docs/03_data_preparation.md`.

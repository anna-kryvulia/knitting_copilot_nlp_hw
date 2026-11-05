---
name: generate-eval-cases
description: Create labelled evaluation cases (JSONL) for a Knitting Copilot component: synthetic patterns with gold IR from the generator, intents, setup dialogues, KB queries, yarn mentions, gauge and chart cases. Use when building or extending data/eval/*.jsonl.
---

# Generate eval cases

CRISP-DM phase: **3. Data Preparation** (for **5. Evaluation**).

## Inputs to confirm
- Target component and file (see `docs/CONVENTIONS.md` § Eval data format).
- Number of cases. Defaults: 80 intents, 30 setup dialogues, 40 KB queries, 60 synthetic patterns,
  40 yarn mentions, 25 yarn-advice cases, 25 gauge cases, 20 chart cases.

## Sources of gold labels (prefer code over judgement)
- **Patterns, counts, charts, gauge results:** from `src/knit_copilot/data/generator.py`, which renders a
  gold IR into pattern text in several styles. Gold labels come from the IR and the simulator, never
  from an LLM.
- **Yarn advice:** needle and gauge ranges from `data/kb/yarn_weights.yaml` (Craft Yarn Council table)
  and `data/yarns.csv`.
- **Intents, setup dialogues, KB queries, yarn mentions:** written by hand or drafted by the agent, then
  reviewed by the user.

## Steps
1. Read the relevant sources (KB files, `yarns.csv`, generator templates).
2. Cover a spread of difficulty and tag each case. Pattern tags: `easy`, `nested_repeat`, `in_the_round`,
   `multi_size`, `imperial_units`, `uk_terms`, `custom_glossary`, `verbose`, `terse`, `typo`.
   Yarn-mention tags: `exact`, `typo`, `partial`, `brand_only`, `colour_in_name`, `unknown_yarn`.
3. Assign `split`: ~60% `dev`, ~40% `test`, stratified by tag, fixed seed.
4. Ids: `<component>-<nnn>`; never reuse an id.
5. Validate: every line parses, required fields present, no duplicates, gold IRs simulate without
   errors; print the tag distribution.
6. **Human review:** print 20% random hand-written cases for the user to check; record the number of
   fixed labels in `docs/03_data_preparation.md`.

## Never
- Never label cases by looking at the system's own outputs.
- Never put eval cases into prompts or few-shot examples.
- Never mix Ravelry patterns into these files; they go through `annotate-ravelry-pattern`.

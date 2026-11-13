# CRISP-DM Log

Running log of decisions. Newest entries at the bottom. Format:

```
## YYYY-MM-DD — <Phase> — <short title>
- What: ...
- Why: ...
- Result / numbers: ...
- Next: ...
```

---

## 2026-11-02 — 0. Setup — Project chosen and agent environment created
- What: Chose the HR assistant task (from the assignment examples), extended with: office/employee-type
  aware policies, deterministic leave rules, manager approval via LangGraph interrupt, grounding check,
  sensitive-topic routing.
- Why: Clear per-component evaluation (retrieval, answer correctness, source support, routing, leave
  decisions), and goes beyond vanilla RAG (tool calls, DB state, routing, human-in-the-loop).
- Decisions:
  - LLM: free OpenRouter models (cost = 0). Risk: rate limits, weaker tool calling → mitigated by
    retry/fallback, JSON schema validation, on-disk LLM cache, and business rules kept in code.
  - Orchestration: LangGraph 1.2.x (explicit graph = generated diagram, built-in multi-turn memory,
    `interrupt` for manager approval). Components stay plain functions for isolated evals.
  - Created `AGENTS.md`, `CLAUDE.md`, `docs/CONVENTIONS.md`, and skills in `.claude/skills/`.
- Next: Phase 1 — Business Understanding doc with scope and metric targets.

## 2026-11-05 — 1. Business Understanding (pivot) — From HR assistant to Knitting Copilot
- What: Replaced the HR task with **Knitting Copilot**: explain written patterns, adjust a pattern to the
  knitter's gauge, yarn advice (needles, expected gauge, fibre properties), charts, row tracking,
  abbreviation knowledge base, and (last) pattern validation. Rewrote `AGENTS.md`, `CLAUDE.md`,
  `docs/CONVENTIONS.md` (Pattern IR schema), skills (`add-abbreviation`, `annotate-ravelry-pattern`
  replace `generate-policy`), renamed the package `hr_copilot` → `knit_copilot`.
- Why: A more engaging domain that still fits the assignment (collect → retrieve → generate → verify with
  tools), with an unusual strength for evaluation: patterns are a structured language, so a synthetic
  generator gives exact gold labels (IR, stitch counts, charts) instead of relying only on an LLM judge.
- Decisions:
  - Tiers. Must: KB + lookup, parser, simulator (single piece), explain, yarn advice, gauge adjustment
    (single piece), charts, row tracker, setup → lock workflow with chat setup via LLM tool calls,
    **real free Ravelry patterns in the eval**. Should: multi-piece garments + picking up stitches,
    mistake helper. Could: validator, cross-piece checks. Out: colourwork, short rows, crochet.
  - Project workflow: setup fields editable until "Generate working pattern" (gauge adjustment + charts);
    after that the project is locked and changes start a new version. Simpler than allowing any order
    at any time.
  - Row tracker is pure code; the LLM is not needed for counting rows.
  - English only; metric units only (mm, cm, sts/rows per 10 cm).
  - Yarn table: brands popular on the Ukrainian market (no brands from Russian producers).
  - Framing: an NLP system (semantic parsing, entity linking, intent classification, retrieval, grounded
    generation, tool calling) where code verifies every number.
- Next: Phase 1 document with use cases, success metrics and targets; then Phase 2 data survey.

## 2026-11-06 — 1. Business Understanding — Problem, use cases, rules and targets
- What: Wrote `docs/01_business_understanding.md`: problems knitters face, two personas, business
  objectives, use cases UC1–UC7 with inputs/outputs and tiers, user journey, business rules BR1–BR8,
  scope, mapping from business needs to NLP tasks, component- and system-level success metrics with
  targets (synthetic vs Ravelry), assumptions, risks.
- Why: Phase 5 needs fixed targets to judge "good" vs "bad" scores; the NLP-task mapping keeps the
  project framed as an NLP system.
- Result / numbers: n/a (targets set, e.g. parser count agreement ≥ 0.90 synthetic / ≥ 0.70 Ravelry,
  yarn linking top-1 ≥ 0.90, gauge maths 100%, 0 wrong numbers shown). Ravelry API access confirmed
  (read-only yarn search works).
- Next: Phase 2 — data survey (Ravelry yarns, CYC tables, existing pattern datasets, Ukrainian shops)
  and the choice of 10–12 free Ravelry patterns.

## 2026-11-06 — 2. Data Understanding — Yarn data, standards, datasets, real patterns
- What: `docs/02_data_understanding.md`; Ravelry client with cache (`src/knit_copilot/data/ravelry.py`);
  `scripts/survey_ravelry_yarns.py` (11 brands, 330 yarns inspected) and
  `scripts/find_ravelry_patterns.py` (24 candidate free patterns in 8 slots).
- Why: The assignment requires checking existing data before generating synthetic data.
- Result / numbers: Ravelry has all UC3 fields; gauge missing for up to 17% of active yarns, needle size
  up to 7% (fallback: CYC range). Discontinued yarns common → active only; Fibra Natura dropped (4 active),
  Vizell added. DROPS is "Garnstudio" on Ravelry. No usable text-pattern dataset on HF/Kaggle (images,
  machine knitting, crochet only) → synthetic generator + 12 hand-annotated Ravelry patterns.
- Next: Phase 3 — abbreviation KB, yarn_weights.yaml, fibres KB, yarns.csv, Pattern IR + generator, eval sets;
  user downloads the 12 chosen patterns into data/private/ravelry/.

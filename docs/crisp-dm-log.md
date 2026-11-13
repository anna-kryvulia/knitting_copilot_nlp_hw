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

## 2026-11-13 — 3. Data Preparation (part A) — IR, units, knowledge bases, yarn table
- What: `ir.py` (Pattern IR, multi-size values), `units.py`, `kb.py` + `data/kb/abbreviations.yaml`
  (74 entries), `yarn_weights.yaml` (CYC 0–7 + Ravelry mapping), `fibres.yaml` (14 fibres),
  `data/build_yarns.py` → `data/yarns.csv` (219 yarns, 11 brands); `docs/03_data_preparation.md`.
- Why: KB is the single source of stitch arithmetic and chart symbols; the yarn table backs UC3.
- Result / numbers: 48 unit tests pass. Yarn table: needle size from label for 215/219, gauge from label
  for 198/219 (rest from CYC); new quality issue Q9: 22 label gauges flagged as inconsistent with their
  weight category. KB alias check found 2 ambiguous aliases (removed).
- Next: Part B — stitch simulator + synthetic pattern generator with gold IR and counts.

## 2026-11-13 — 3. Data Preparation (part B) — Simulator and synthetic pattern generator
- What: `simulator.py`, `data/templates.py` (9 templates), `data/generator.py` (5 writing styles + typo
  noise) → `data/eval/parse_cases.jsonl`; tests for simulator and generator; docs updated.
- Why: No labelled dataset of written patterns exists; gold IR + simulation give exact labels.
- Result / numbers: 63 cases (36 dev / 27 test), all 45 template×style pairs; 14 multi-size, 14 in the
  round, 20 with typos; 104 tests pass. Loop back 3 → 4-design: IR gained `until_count`
  ("repeat until 44 sts") after checking real patterns (Gramma's Dishcloth). Review of samples fixed
  4 rendering errors ("until 48 sts remain" when increasing, "last 1 sts", sides on rows worked on both
  sides, "end of the row" in rounds).
- Next: Part C — hand-written eval sets (intents, setup dialogues, KB queries, yarn mentions, yarn advice).

## 2026-11-13 — 3. Data Preparation (part C) — Hand-written eval sets
- What: intent labels and setup tool schema in CONVENTIONS; sources `data/eval/src/*.yaml`;
  `data/build_eval_sets.py` (validation + stratified split + 20% review sample); 5 JSONL sets.
- Why: Router, setup agent, KB retrieval, yarn linker and yarn advisor need labelled inputs; no dataset exists.
- Result / numbers: 233 cases — intents 88, setup 30, KB 50, yarn links 40, yarn advice 25 (~60/40 dev/test).
  Validation caught 3 label/data problems: lace yarns wrongly flagged (rule fixed in build_yarns, flags 22 → 11),
  two wrong `warn_gauge` labels (corrected). 106 tests pass.
- Next: human review of docs/data/eval_review_sample.md; Part D (Ravelry annotations) once PDFs are downloaded;
  then Phase 4 (parser first — needs OPENROUTER_API_KEY).

## 2026-11-13 — 4. Modeling — Parsers and the first UI page
- What: grammar parser (`parser_grammar.py`), LLM/hybrid parser with code-side unit normalisation and
  simulator-guided repair (`components/parser.py`, `prompts/parser.md`), parser eval (`eval/eval_parser.py`,
  `eval/common.py`), Streamlit `app.py` (Pattern tab + abbreviation lookup); docs 04 and 05 started.
- Why: Parsing is the core NLP step for UC1/2/4/5/7; the grammar is the baseline and the free fast path.
- Result / numbers: grammar on dev 36/36 exact after 1 iteration (35 → 36); flagged as optimistic (same
  conventions as the generator). LLM eval blocked: no OPENROUTER_API_KEY. 112 tests pass. UI checked in the
  browser: hat example parsed (88 sts, 56 rounds), yfwd → yo lookup.
- Next: add the key, run `eval_parser --parser llm/hybrid` on dev; then explainer (UC1) and KB retrieval (UC6).

## 2026-11-13 — 4/5. Modeling + Evaluation — Row display, KB search (UC6)
- What: `display.py` (rows described from the IR with computed repeat counts, grouped view) after user
  feedback on the first UI; `retrieval/search.py` (exact + fuzzy lookup, BM25/dense/hybrid);
  `eval/eval_kb.py`; search in the UI sidebar; LLM client: output limit 12k tokens, cut-off answers rejected,
  per-model run without fallback, `LLMConfigError` (no retries without a key).
- Result / numbers: exact lookup 1.00 (dev and test). Question recall@3 v1 → v5 on dev: BM25 0.644 → 0.900,
  hybrid 0.511 → 0.778; on test BM25 0.750 → 0.683, hybrid 0.783 → default hybrid. Loops: 5 → 3 twice
  (2 incomplete labels fixed and documented; 6 KB descriptions given missing facts).
- Note: test split was looked at after v4; a fresh author-written question set is needed for an unbiased number.
- Next: pick the default parser model from the comparison; time budget for LLM parsing; explainer (UC1).

## 2026-11-13 — 4. Modeling — Free-model selection and time budget
- What: compared 9 free models on 2 dev patterns (`scripts/compare_parser_models.py`); hard per-request
  deadline in `llm.py` (worker thread), parse time budget 60 s, faster move-on for rate-limited models.
- Result / numbers: exact on both patterns: Nemotron 3.5 Super (32–57 s), Nemotron 3 Ultra (71–108 s),
  Dots 3 Note (47–75 s); Flint 1/2 (one 22-min hang); Gemma 4 ×2 always rate-limited; Inkling ×2 and
  Xingchen failed instantly. App model → Nemotron 3.5 Super; judge → Dots 3 Note (other family).
  Cable scarf via LLM: correct in 32 s. New target in doc 01: pattern reading ≤ 60 s. 118 tests pass.
- Next: full LLM/hybrid parser eval on dev (36 cases; ~20–40 min with free models), then explainer (UC1).

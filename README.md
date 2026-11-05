# Knitting Copilot

An NLP system that understands written knitting patterns. It parses pattern text into a structured
representation, explains it in plain English, recommends needles and expected gauge for a yarn
(including yarns popular in Ukraine), adapts the pattern to the knitter's own gauge, draws charts and
tracks progress row by row. Code checks every number the language model produces.

Built for *NLP Assignment 1: Build an NLP System*, following CRISP-DM (see [docs/crisp-dm-log.md](docs/crisp-dm-log.md)).

> Status: **project setup done; Phase 1 (business understanding) next.**

## Use cases

| | Use case | Tier |
|---|---|---|
| UC1 | Explain a written pattern | Must |
| UC2 | Adjust a pattern to your gauge | Must |
| UC3 | Yarn → needle size, expected gauge, fibre advice | Must |
| UC4 | Charts from a written pattern | Must |
| UC5 | Row-by-row tracker | Must |
| UC6 | Abbreviation knowledge base | Must |
| UC7 | Validate a written pattern | Could |

Units are metric only (mm, cm, stitches/rows per 10 cm). Language: English.

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env        # then add your free OpenRouter key: https://openrouter.ai/keys
```

## Run

```bash
pytest -q                            # unit tests
streamlit run app.py                 # app (available after Phase 4)
python -m eval.run_all --split dev   # evaluations (available after Phase 5)
```

## Repository guide

| Path | What |
|---|---|
| `AGENTS.md`, `CLAUDE.md` | Instructions that steer the AI coding agent (CRISP-DM rules, tiers, architecture, conventions) |
| `.claude/skills/` | Agent workflows: add-component, add-abbreviation, generate-eval-cases, annotate-ravelry-pattern, run-eval, crisp-dm-checkpoint |
| `docs/` | CRISP-DM phase documents, decision log, diagrams, conventions (incl. the Pattern IR schema) |
| `src/knit_copilot/` | Application code (LLM client, parser, simulator, gauge maths, charts, tracker, LangGraph graph) |
| `prompts/` | One prompt file per LLM component |
| `data/` | Knowledge base, yarn table, labelled eval sets (Ravelry pattern files stay in git-ignored `data/private/`) |
| `eval/`, `results/` | Per-component evaluation scripts and their results |

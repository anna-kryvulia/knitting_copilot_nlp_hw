# Knitting Copilot

An NLP system that understands written knitting patterns. It parses pattern text into a structured
representation, explains it in plain English, recommends needles and expected gauge for a yarn
(including yarns popular in Ukraine), adapts the pattern to the knitter's own gauge, draws charts and
tracks progress row by row. Code checks every number the language model produces.

Built for *NLP Assignment 1: Build an NLP System*, following CRISP-DM (see [docs/crisp-dm-log.md](docs/crisp-dm-log.md)).

> Status: all Must-tier use cases are built and evaluated. Docs: [system diagram](docs/diagrams/system.md),
> [chat graph](docs/diagrams/chat_graph.md), [evaluation](docs/05_evaluation.md), [modeling](docs/04_modeling.md).

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
cp .env.example .env
```

Then add one free LLM key to `.env` (any OpenAI-compatible API works; nothing in the code is provider-specific):
- **OpenRouter** (default): `OPENROUTER_API_KEY=` from https://openrouter.ai/keys; free models are limited to
  50 requests a day without credit.
- **Google AI Studio (Gemini)**, used for the final evaluation runs: `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`,
  `LLM_API_KEY=` from https://aistudio.google.com, `LLM_MODEL=gemini-3.5-flash`,
  `LLM_FALLBACK_MODELS=gemini-3.5-flash-lite`. The eval judge then stays on OpenRouter (a different model family):
  `JUDGE_BASE_URL=https://openrouter.ai/api/v1`.

LLM answers are cached in `.cache/llm/`, so a re-run of the same input is instant and costs no quota.

## Run

```bash
pytest -q                 # unit tests (no API key needed)
streamlit run app.py      # the app: http://localhost:8501
```

In the app: **My project** (setup by chat or form → *Generate working pattern* → row tracker; every chat reply has
an *LLM trace* with the graph node, model calls and tool calls), **Pattern explorer** (rows, chart, explanation,
adjust to my gauge), **Yarn** (needles, expected gauge, fibre advice); KB search in the sidebar.

## Evaluations

Each script writes `results/<component>_<split>.json`; numbers and error analysis are in
[docs/05_evaluation.md](docs/05_evaluation.md). Use `--split test` for the reported numbers.

```bash
python -m eval.eval_parser --parser grammar|llm|hybrid --split dev   # synthetic patterns
python -m eval.eval_parser_real --parser grammar|llm|hybrid          # real Ravelry patterns (needs data/private/)
python -m eval.eval_kb --split dev                                    # abbreviation lookup + retrieval
python -m eval.eval_yarn_linker --split dev
python -m eval.eval_yarn_advisor --split dev
python -m eval.eval_explainer --split dev --judge
python -m eval.eval_gauge --split dev
python -m eval.eval_rewriter --split dev
python -m eval.eval_charts --split dev                                # or --split ravelry
python -m eval.eval_router --mode rules|llm|hybrid --split dev
python -m eval.eval_setup_agent --split dev
```

The real Ravelry patterns are copyrighted: their PDFs, text and hand-made gold annotations stay in git-ignored
`data/private/`; the repo keeps only their metadata (`data/eval/ravelry/patterns.yaml`) and aggregate results.

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

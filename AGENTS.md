# AGENTS.md — Knitting Copilot

Instructions for any AI coding agent working in this repository. Read this file fully before
doing anything. If an instruction here conflicts with a chat prompt, ask the user which one wins.

## 1. Project

**Knitting Copilot** is an NLP system that understands written knitting patterns. It turns pattern
text into a structured representation (Pattern IR), explains it, adapts it to the knitter's yarn and
gauge, draws charts, and tracks progress row by row. Code verifies every number the language model
touches.

**Framing:** this is an *NLP system with code-based verification*, not a
knitting calculator with a chatbot. The NLP components are the core: semantic parsing of pattern text,
yarn entity linking, intent classification, retrieval, grounded generation, and tool-calling setup.
Reports, diagrams and docstrings should say so.

Language: **English only** (UI, prompts, eval sets). Units: **metric only** — needles in mm,
lengths in cm, gauge in stitches/rows per 10 cm, yarn in g and m. Never output inches or US needle sizes;
input in imperial units is converted by the parser.


## 2. Use cases and tiers

Build in this order. Do not start a lower tier until the higher tier works and is evaluated.

| Tier | Use case / component |
|---|---|
| **Must** | UC6 abbreviation knowledge base + lookup |
| **Must** | Pattern parser (text → Pattern IR) + unit normalisation |
| **Must** | Stitch simulator (single piece, flat and in the round) |
| **Must** | UC1 explain a written pattern |
| **Must** | UC3 yarn advice: exact yarn or fibre + weight → needles (mm), expected gauge, fibre advice |
| **Must** | UC2 adjust a pattern to the knitter's gauge (single piece) |
| **Must** | UC4 charts from a pattern |
| **Must** | UC5 row tracker (pure code) |
| **Must** | Project setup → lock workflow, including chat setup via LLM tool calls |
| **Must** | Real free Ravelry patterns (hand-annotated) in the evaluation |
| **Must** | Evals for every Must component |
| Should | Multi-piece garments + picking up stitches; mistake helper with tracker context |
| Could | UC7 pattern validator; cross-piece consistency checks |

Scope **out**: colourwork, short rows, crochet.

## 3. CRISP-DM workflow

Every task belongs to one CRISP-DM phase. Before starting a task, state the phase.
After finishing it, append an entry to `docs/crisp-dm-log.md` (use the `crisp-dm-checkpoint` skill).

| Phase | Output in this repo |
|---|---|
| 1. Business Understanding | `docs/01_business_understanding.md`: users, use cases, tiers, success metrics with targets |
| 2. Data Understanding | `docs/02_data_understanding.md`: sources checked (Ravelry, Craft Yarn Council, Kaggle/HF, Ukrainian yarn shops), what was used, why synthetic |
| 3. Data Preparation | `data/kb/`, `data/yarns.csv`, `data/eval/*.jsonl`, generator, `docs/03_data_preparation.md` |
| 4. Modeling | `src/knit_copilot/` components + LangGraph graph |
| 5. Evaluation | `eval/`, `results/`, `docs/05_evaluation.md`: metrics, error analysis, iterations |
| 6. Deployment | runnable Streamlit app + README run instructions |

Rules:
- **No component without its eval.** A component is "done" only when `eval/eval_<component>.py`
  exists, runs, and its results are in `results/`.
- When an eval score is below target: do error analysis (look at failing cases), write down the cause,
  then change one thing at a time and re-run. Record each iteration (v1 → v2 …) in `docs/05_evaluation.md`.
  Going back from Evaluation to Data Preparation or Modeling is expected; log it.
- Eval files have `split: dev|test`. Iterate on `dev`, report `test`. Report synthetic and real
  Ravelry patterns **separately**.
- Never copy eval cases into prompts or few-shot examples.

## 4. Architecture

### Pattern IR is the centre
The parser turns pattern text into **Pattern IR** (schema in `docs/CONVENTIONS.md` and
`src/knit_copilot/ir.py`). Every other pattern feature reads the IR, never the raw text.

### One abbreviation knowledge base drives everything
`data/kb/abbreviations.yaml`: each stitch has its aliases (US/UK), how many stitches it consumes and
produces, chart symbol, description (own words) and reference. The parser vocabulary, simulator,
chart symbols, explainer and UC6 lookup all read this file. Never hard-code stitch arithmetic elsewhere.

### Division of labour
- **LLM**: translate between language and structure (text → IR, IR → explanation, message → intent,
  message → tool calls, yarn advice text, rewriting an adjusted pattern in the original style).
- **Code**: every number. Stitch counts, gauge maths, needle sizes from the yarn-weight table,
  chart grids, row tracking, project stage rules.
- An LLM output that contains numbers must be checked by code (re-parse + simulate) before it is shown.

### Flow

```
user ─► [router] ─┬─ setup ─────► [setup agent: tool calls] → project DB (yarn, needles, gauge, pattern, size)
                  ├─ explain ───► [parser] → [simulator] → [explainer] (+ KB citations)
                  ├─ yarn ──────► [yarn linker] → [needle/gauge rules] → [yarn advisor] (+ fibre KB)
                  ├─ lookup ────► [KB retriever] → definition + reference
                  └─ question ──► [KB retriever] → grounded answer

project setup complete ─[Generate working pattern]─► [gauge adjuster] → [rewriter] → [parser+simulator verify]
                                                      → [chart builder] → saved version (LOCKED)
knitting stage: [row tracker] (code) · charts · explain
```

### Project stages
- **Setup** (editable): yarn → needles → measured gauge → pattern + size. Can be filled via chat
  (LLM tool calls) or the UI form. Yarn may be skipped if the gauge is entered directly.
- **Generate working pattern** is enabled only when gauge, needles, pattern and size are set. It runs
  gauge adjustment + charts and saves version N.
- **Knitting** (locked): setup fields are read-only; the row tracker and charts use the saved version.
  "Start over from setup" creates version N+1 and resets progress after a warning.
- Explain, abbreviation lookup, general yarn questions and the validator work at any stage and never
  modify the project.
- Stage rules live in `project.py` as plain code with unit tests.

### Module layout
- Components live in `src/knit_copilot/components/<name>.py` as **plain functions with no LangGraph
  imports**, so each can be evaluated in isolation.
- `graph.py` is the only place that wires components into a LangGraph `StateGraph`.
- `simulator.py`, `gauge.py`, `charts.py`, `tracker.py`, `project.py` are pure Python with unit tests.
- `db.py` is the only module that touches SQLite. `llm.py` is the only module that calls an LLM.

## 5. Tech stack (pinned; do not add dependencies without asking)

- Python 3.12, deps in `pyproject.toml` (`requirements.txt` installs it).
- LLM: **free models on OpenRouter** via the `openai` SDK (`base_url=https://openrouter.ai/api/v1`).
  Model ids come from `.env` (`LLM_MODEL`, `LLM_FALLBACK_MODELS`, `JUDGE_MODEL`), never hard-coded.
- Orchestration: **LangGraph 1.2.x**. Use only the current API: `StateGraph`, `START`, `END`,
  `add_conditional_edges`, a checkpointer (`InMemorySaver`). If unsure about an API, read the installed
  package source; don't rely on old 0.x tutorials. Do **not** use LangChain LLM wrappers; nodes call
  `knit_copilot.llm`.
- Retrieval: `rank-bm25` + `sentence-transformers` embeddings + numpy cosine (no vector DB).
- Charts: matplotlib (PNG) or SVG. DB: stdlib `sqlite3`. UI: Streamlit (`app.py`).

### Free-model constraints
- All LLM calls go through `llm.chat()` / `llm.chat_json()`: retry with backoff, model fallback,
  JSON validated against a Pydantic schema (re-asks once).
- Responses are cached on disk (`.cache/llm/`), so eval reruns are cheap and reproducible
  (`LLM_CACHE=0` bypasses).
- The judge model must be from a **different model family** than the app model.
- The parser has a **grammar-based baseline** (`parser_grammar.py`) used as fallback and as a comparison
  in the evaluation.

## 6. Data rules

- **Ravelry patterns** are copyrighted. Store PDFs/text only in `data/private/` (git-ignored).
  The repo keeps only our annotations, the Ravelry URL, designer and licence note. Use them for evaluation only.
- **Yarns**: brands popular on the Ukrainian market (e.g. YarnArt, Alize, Himalaya, Nako, Gazzal,
  Kartopu, Madame Tricote, DROPS, Lana Grossa, Fibra Natura, Etrofil). No brands from Russian producers.
  Source: Ravelry API + shop pages; record the source per row.
- **Knowledge-base text** (abbreviations, techniques, fibres) is written in our own words; cite the
  reference (e.g. Craft Yarn Council) per entry.
- Synthetic patterns come from `src/knit_copilot/data/generator.py` with gold IR and gold counts.

## 7. Code conventions

- Type hints everywhere; Pydantic models for every structured LLM output, tool argument and the IR.
- Prompts live in `prompts/<component>.md`, loaded with `llm.render(name, **vars)`. No long prompt strings in code.
- Small functions, one module per component, docstring = purpose / input / output / model calls /
  tool calls (used in the report).
- No secrets in code; read from `.env`. Never print API keys or Ravelry credentials.
- `logging`, not `print`, except in CLI scripts.
- Tests: `pytest` in `tests/`. Deterministic parts (simulator, gauge maths, charts grid, tracker,
  project stages, unit conversion, metrics) must have unit tests.
- Every graph node emits a trace record via `knit_copilot.tracing`.

## 8. Commands

```bash
uv venv --python 3.12 && source .venv/bin/activate && uv pip install -r requirements.txt
pytest -q                               # unit tests
python -m knit_copilot.data.generator   # synthetic patterns + gold IR → data/eval/
python -m knit_copilot.retrieval.index  # build the KB retrieval index
streamlit run app.py                    # run the app
python -m eval.run_all --split dev      # all component evals → results/
```

## 9. Definition of done for any change

1. Code follows section 7; `pytest -q` passes.
2. The affected component's eval was re-run; numbers in `results/` are updated.
3. `docs/crisp-dm-log.md` has an entry (what, why, result).
4. README updated if run instructions changed.

## 10. Don'ts

- Don't let the LLM compute stitch counts, gauge maths or needle sizes.
- Don't show an LLM-rewritten pattern unless it re-parses and simulates to the expected counts.
- Don't invent abbreviation definitions; if it's not in the KB or the pattern's own glossary, say so.
- Don't start Should/Could features before all Must features have evals.
- Don't add frameworks, vector DBs or paid APIs without asking.
- Don't edit `data/eval/*` labels to make a metric look better; fix the system or document the label error.
- Don't commit anything from `data/private/`.

# 1. Business Understanding

CRISP-DM phase 1. Defines the problem, users, scope, business rules and the success criteria that
Phase 5 (Evaluation) measures against. Targets may be revised after Phase 2 (Data Understanding); every
change is logged in `crisp-dm-log.md`.

## 1.1 Background and problem

Knitting patterns are written in a compressed technical language:

```
Row 3 (RS): k2, *yo, k2tog, k3; rep from * to last 2 sts, k2. (32 sts)
```

Beginner and intermediate knitters run into the same problems again and again:

| Problem | What happens today |
|---|---|
| **Cryptic notation**: abbreviations, nested repeats, "rep from *", US vs UK terms | Searching each abbreviation, guessing what a repeat covers |
| **Different gauge**: the knitter's swatch doesn't match the pattern's gauge | Garment comes out the wrong size, or the knitter does the maths by hand and makes mistakes |
| **Different yarn**: the pattern's yarn is unavailable locally (e.g. in Ukraine) | Unsure which needle size and gauge a substitute yarn gives |
| **Text-only patterns**: no chart | Hard to see the stitch structure, especially for lace and cables |
| **Losing place**: which row am I on, which repeat? | Paper notes, tally marks, mistakes after a break |
| **Imperial units** in most English-language patterns | Converting inches, yards and US needle sizes by hand |

## 1.2 Users

| Persona | Needs |
|---|---|
| **Beginner** (knows knit/purl, first "real" pattern) | Plain-English explanation of every row, abbreviation definitions, row tracking |
| **Intermediate** (several projects, wants to adapt patterns) | Gauge adjustment, yarn substitution, charts, metric units |

Both are English-speaking (UI and patterns in English) and buy yarn on the **Ukrainian market**.

## 1.3 Business objectives

1. A knitter can **understand** any in-scope pattern row by row without outside help.
2. A knitter can **knit the pattern with their own yarn and gauge** and get the intended size.
3. A knitter can **keep track of progress** and see the stitch structure (charts).
4. **Every number shown is correct**: stitch counts, needle sizes and adjusted counts are computed by
   code, never guessed by the language model.

## 1.4 Use cases

| ID | Use case | Input | Output | Tier |
|---|---|---|---|---|
| **UC1** | Explain a written pattern | Pattern text (pasted or from the project) | Row-by-row plain-English explanation, stitch counts, abbreviation definitions with KB citations | Must |
| **UC2** | Adjust a pattern to the knitter's gauge | Pattern + measured gauge (sts and rows per 10 cm) + size | Adjusted pattern in the original style, new counts and finished dimensions (cm), verified by re-parsing and simulation | Must |
| **UC3** | Yarn advice | Exact yarn name (e.g. "YarnArt Jeans") **or** fibre content + weight | Yarn weight category, needle size range (mm), expected gauge, fibre-specific advice (e.g. cotton has little elasticity) | Must |
| **UC4** | Charts from a pattern | Pattern (one piece) | Chart image with standard symbols, row numbers, RS/WS reading direction, legend | Must |
| **UC5** | Row-by-row tracker | Working pattern | Current row instruction, expected count, position in repeat; next/previous/go to row | Must |
| **UC6** | Abbreviation knowledge base | Abbreviation or question ("how do I make a left-leaning decrease?") | Definition, stitch arithmetic, US/UK term, reference | Must |
| **UC7** | Validate a written pattern | Pattern text | List of inconsistencies (stated vs computed counts, repeats that don't fit, undefined abbreviations) with suggested fixes | Could |
| — | Chat setup | Messages like "I'm using YarnArt Jeans and my swatch is 21 sts per 10 cm" | Project fields filled via LLM tool calls | Must |
| — | Multi-piece garments, picking up stitches | Garment pattern (back, front, sleeves, bands) | Same as UC1–UC5 across pieces | Should |
| — | Mistake helper | Problem description + tracker position | Diagnosis using the current row, fix steps from the technique KB | Should |

## 1.5 User journey and business rules

```
SETUP (editable)                                   KNITTING (locked, version N)
1. Choose yarn (UC3)  → needles + expected gauge    ├── adjusted pattern
2. Knit a swatch      → enter measured gauge        ├── charts (UC4)
3. Load pattern + choose size                       ├── row tracker (UC5)
        │                                           └── explain (UC1)
        └──[ Generate working pattern ]──► UC2 + UC4 ──► saved, locked
```

Business rules:
- **BR1 — Stages.** Setup fields (yarn, needles, gauge, pattern, size) can be edited freely until the
  working pattern is generated. After that the project is locked; changing anything means
  "Start over from setup", which creates version N+1 and resets progress after a warning.
- **BR2 — Prerequisites.** "Generate working pattern" requires gauge, needles, pattern and size. Yarn is
  optional when the gauge is entered directly.
- **BR3 — Always available.** UC1 explain, UC6 lookup, general yarn questions and UC7 never change the
  project and work at any stage.
- **BR4 — Numbers by code.** Stitch counts, gauge maths, needle sizes and chart grids are computed in
  code. LLM output containing numbers is shown only after it re-parses and simulates correctly.
- **BR5 — Metric only.** Needles in mm, lengths in cm, gauge per 10 cm, yarn in g and m. Imperial input
  is converted; output is never imperial.
- **BR6 — Grounding.** Definitions come from the KB or the pattern's own glossary. Unknown abbreviations
  are reported as unknown, not guessed.
- **BR7 — Yarn table.** Yarns popular on the Ukrainian market (no brands from Russian producers), from
  Ravelry data plus shop pages; each row records its source.
- **BR8 — Repeats stay intact.** Gauge adjustment rounds stitch counts to fit the stitch pattern's
  repeat (e.g. a multiple of 6 + 2) instead of breaking the motif.

## 1.6 Scope

**In scope (Must):** flat and in-the-round knitting, one piece; knit/purl, increases, decreases, yarn
overs, slipped stitches, simple cables; repeats (`*…*`, `(…) x n`, "rep to last n sts", "rep rows 1–4
until…"); US and UK terms; multi-size notation `40 (46, 52)`; imperial → metric conversion.

**Should:** multi-piece garments, picking up stitches, mistake helper.

**Out of scope:** colourwork, short rows, crochet, languages other than English, pattern sales or
distribution.

## 1.7 From business goals to NLP tasks

| Business need | NLP / technical task | Component |
|---|---|---|
| Understand notation | **Semantic parsing** (text → Pattern IR), normalisation of units and US/UK terms | parser, units |
| Explain rows | **Grounded generation** from structured data, with citations | explainer |
| Find definitions | **Retrieval** (lexical + dense) over the abbreviation KB | KB retriever |
| Recognise a yarn | **Entity linking** of free-text yarn mentions to the yarn table (typos, partial names, Cyrillic names listed by Ravelry) | yarn linker |
| Route the request | **Intent classification** | router |
| Fill the project from chat | **Tool calling** / slot filling | setup agent |
| Adapt the text | **Constrained rewriting** in the original pattern style | rewriter |
| Correct numbers | Deterministic verification (simulation, maths) | simulator, gauge, charts, tracker |

## 1.8 Success criteria

Targets are for the **test split**. Synthetic and real Ravelry patterns are reported separately; real
patterns have lower targets because their text is less regular.

### Component level

| Component | Metric | Target (synthetic) | Target (Ravelry) |
|---|---|---|---|
| Router | macro-F1 | ≥ 0.90 | — |
| Setup agent | correct tool + arguments | ≥ 0.85 | — |
| | final project state matches gold | ≥ 0.85 | — |
| KB lookup | exact abbreviation lookup accuracy | ≥ 0.98 | — |
| | Recall@3 for natural-language questions | ≥ 0.85 | — |
| Units | conversion accuracy | 1.00 | 1.00 |
| Parser | parse success (valid IR) | ≥ 0.95 | ≥ 0.80 |
| | row-level stitch count agreement after simulation | ≥ 0.90 | ≥ 0.70 |
| | op-level F1 | ≥ 0.90 | ≥ 0.75 |
| | LLM parser vs grammar baseline | LLM better on `verbose`/`typo` tags | report |
| Simulator | unit tests vs gold counts | 100% | 100% |
| Explainer | coverage of required facts | ≥ 0.85 | ≥ 0.75 |
| | faithfulness (no claim contradicting the IR) | ≥ 0.95 | ≥ 0.90 |
| | judge score (1–5), judge–human agreement ≥ 0.8 | ≥ 4.0 | ≥ 3.5 |
| Yarn linker | top-1 accuracy | ≥ 0.90 | — |
| | correct "no match" for unknown yarns | ≥ 0.80 | — |
| Yarn advisor | weight category accuracy | ≥ 0.95 | — |
| | needle size within reference range | ≥ 0.95 | — |
| | advice correctness (judge) | ≥ 4.0 | — |
| Gauge adjuster (maths) | count correctness vs reference calculation | 100% | 100% |
| | finished size error | ≤ 1 cm | ≤ 2 cm |
| | repeat preservation | 100% | 100% |
| Rewriter | re-parses and simulates to the adjusted counts | ≥ 0.90 | ≥ 0.75 |
| Charts | cell accuracy vs gold grid | ≥ 0.98 | ≥ 0.90 |
| Tracker, project stages | unit tests | 100% | — |

### System level

| Metric | Target |
|---|---|
| End-to-end scenario success (setup → generate → track; scripted runs) | ≥ 0.80 |
| Wrong number shown to the user (count, needle size, dimension) | 0 in the scenario set |
| Median latency per chat turn (free models) | ≤ 15 s |
| Cost | 0 (free models) |

## 1.9 Assumptions and constraints

- Free OpenRouter models: rate limits and weaker JSON / tool-calling reliability. Mitigated by retry and
  model fallback, schema validation, an on-disk response cache, a grammar-based parser baseline, and
  keeping all numbers in code.
- Ravelry API: read-only Basic Auth, non-commercial use; yarn data only. Pattern files are downloaded
  manually and kept in git-ignored `data/private/`.
- Gauge from Ravelry is "per 4 inches" (10.16 cm); converted to per 10 cm.
- The knitter's gauge is assumed to be measured after blocking.
- Single developer (the student) with an AI coding assistant; English-only UI.

## 1.10 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Free models fail on strict JSON for long patterns | Parser is on the critical path | Parse row by row, grammar fallback, re-ask on invalid JSON, cache |
| Real patterns differ a lot from synthetic ones | Low Ravelry scores | Varied generator styles; error analysis per tag; honest reporting |
| Scope too large | Unfinished prototype | Tiers; Should/Could only after all Must components have evals |
| Ravelry API changes or access issues | Yarn table incomplete | Cache API responses; manual CSV fallback from shop pages |
| LLM judge unreliable | Misleading scores | Calibrate on human-labelled subset; different model family from the app model |
| Copyright of real patterns | Legal/ethical | Keep text private; commit only annotations and links |

## 1.11 Project plan (CRISP-DM)

| Phase | Output |
|---|---|
| 2. Data Understanding | Survey of Ravelry yarn data, CYC tables, existing pattern datasets (Kaggle/HF), Ukrainian shops; choice of 10–12 free Ravelry patterns |
| 3. Data Preparation | Abbreviation/technique/fibre KB, yarn-weight table, `yarns.csv`, pattern generator, eval sets, Ravelry annotations |
| 4. Modeling | Components in tier order (see `AGENTS.md` §2), LangGraph graph, Streamlit UI |
| 5. Evaluation | Per-component and system metrics vs the targets above, error analysis, iterations |
| 6. Deployment | Local run instructions, demo video |

# 4. Modeling

CRISP-DM phase 4. Components are built in the tier order of `AGENTS.md` §2; each one gets its eval
before the next starts. This document grows with every component.

| # | Component | Type | Status | Eval |
|---|---|---|---|---|
| 1 | Grammar parser (`parser_grammar.py`) | rules | ✅ | `eval/eval_parser.py --parser grammar` |
| 2 | LLM / hybrid parser (`components/parser.py`) | LLM + simulator check | ✅ built, ⏳ eval needs `OPENROUTER_API_KEY` | `--parser llm`, `--parser hybrid` |
| 3 | KB search (`retrieval/search.py`): exact + fuzzy lookup, BM25 / dense / hybrid retrieval | retrieval | ✅ default hybrid | `eval/eval_kb.py` |
| 4 | Row display (`display.py`) | code | ✅ | `tests/test_display.py` |
| 5 | Streamlit UI: Pattern (Rows / Explanation) + Yarn tabs, KB search sidebar | UI | ✅ | manual check |
| 6 | Explainer (`components/explainer.py`, `facts.py`) | code facts + LLM + grounding check | ✅ built, ⏳ eval needs quota | `eval/eval_explainer.py` |
| 7 | Yarn linker (`components/yarn_linker.py`) | string-based entity linking | ✅ | `eval/eval_yarn_linker.py` |
| 8 | Yarn advisor (`components/yarn_advisor.py`) | code facts + LLM + grounding check | ✅ built, ⏳ eval needs quota | `eval/eval_yarn_advisor.py` |
| 9 | Gauge adjustment (`gauge.py`) | code | ✅ | `eval/eval_gauge.py`, `tests/test_gauge.py` |
| 10 | Rewriter (`components/rewriter.py`) | code edit list + LLM + re-parse check, code fallback | ✅ built, ⏳ eval needs quota | `eval/eval_rewriter.py` |
| 11 | Charts (`charts.py`) | code | ✅ | `eval/eval_charts.py`, `tests/test_charts.py` |

## 4.1 Parsers

### Grammar parser (baseline, no model)
`src/knit_copilot/parser_grammar.py`. Rules for standard notation:
1. **Header**: sizes `S (M, L)`, needles (mm or US → mm), gauge/tension per 10 cm or per 4 in (converted),
   cast-on with multi-size numbers.
2. **Verbose → terse normalisation**: "knit 2 together" → `k2tog`, "repeat [..] until 2 stitches remain" →
   `[..] to last 2 sts`, "work [..] three times" → `(..) 3 times`, "knit to the end of the round" → `k to end`.
3. **Row bodies**: star repeats (`*…; rep from * to last 2 sts`, `N more times` = N+1 in total), bracket
   groups, `X to end`, `k2 (3, 4)` per size, stated counts in `(44 sts)`, `[44 sts]`, `— 44 sts`.
   Abbreviations are resolved through the KB (US/UK aliases, typo-tolerant normalisation).
4. **Steps**: `Repeat Rows 1–4 until piece measures 59 in…` (→ cm), `a total of N times` (→ N−1 more),
   `until 4 sts remain`, bind-off variants, "break yarn and draw through" (gather).
5. Lines it can't read become **warnings** (never silently dropped).

### LLM parser and hybrid
`src/knit_copilot/components/parser.py`, prompt `prompts/parser.md`.

```
text ─► normalise_units (code: in→cm, per 4 in→per 10 cm, US→mm)
     ─► LLM: text → Pattern IR JSON (schema-validated, re-asked once if invalid JSON)
     ─► simulator check ── ok ──► IR
                         └ error ─► error message sent back to the LLM (1 repair) ─► IR or "failed"
hybrid: grammar first; the LLM runs only if the grammar has warnings or its IR does not simulate.
```

Design decisions:
- **Numbers by code** (AGENTS.md §4): unit conversion happens *before* the model sees the text; the model
  only maps structure. Every IR is simulated before it is accepted.
- **Simulator-guided repair**: the model gets the concrete error ("Row 3: repeat does not fit: 3 sts left
  over") instead of a generic retry. Tested with a mocked model (`tests/test_parser.py`).
- **Hybrid** keeps cost and latency at zero for clean text and uses the LLM for what rules can't read
  (free-form prose, unusual notation). The eval compares grammar vs LLM vs hybrid.

## 4.2 UI (first version)
`app.py` (Streamlit): paste a pattern or load an example → parse (hybrid or LLM) → metrics (construction,
cast-on, rows, which parser read it, gauge) → row-by-row table (side, repeat iteration, start → end
stitches, stated count, worked ops) with warnings for counts that don't add up. Sidebar: abbreviation
lookup (UC6, exact). Run: `streamlit run app.py`.

### Row display (`src/knit_copilot/display.py`)
First UI feedback (user review): the table listed every stitch (`k2, p2, k2, p2, …`) and a "Repeat" column
that started counting from the second time a row was worked, which looked like an off-by-one. Fix:
- each row is described **from its IR**, with repeat counts computed from the stitch count:
  `k2, (yo, k2tog, k3) ×8, k2`, nested repeats kept (`(k2tog ×3, (yo, k1) ×6, k2tog ×3) ×3`);
- a **grouped view** (default) shows a repeated block as one line ("Rows 9–400 · Rows 1–4 × 98 more");
  the "Show every row" toggle gives one line per worked row with "time 3 of 14".
The same descriptions will feed the explainer (UC1) and the row tracker (UC5).

### LLM model selection
First real calls showed (1) `max_tokens` = 2048 cut the IR JSON off → raised to 12 000; a cut-off answer is
now an error and never cached; (2) the Gemma 4 free models returned rate limits on every attempt.
`scripts/compare_parser_models.py` ran the LLM parser with each free model alone (no fallback) on two dev
patterns (`results/parser_model_comparison.json`):

| Model | parse-004 (hat, UK, 3 sizes) | parse-006 (feather & fan, nested) |
|---|---|---|
| google/gemma-4-31b-it:free | fail, 32 s | fail, 33 s |
| google/gemma-4-26b-a4b-it:free | fail, 33 s | fail, 32 s |
| nvidia/nemotron-3.5-super-vl:free | exact, 57 s | exact, 32 s |
| nvidia/nemotron-3-ultra-550b-a55b:free | exact, 71 s | exact, 108 s |
| thinkingmachines/inkling:free | fail, 0 s | fail, 0 s |
| thinkingmachines/inkling-small:free | fail, 0 s | fail, 0 s |
| recursive/flint-v1.0:free | fail, 1340 s | exact, 80 s |
| xingchen-agi/xing4.0-29b-a4b:free | fail, 0 s | fail, 0 s |
| dots-studio/dots-3-note-preview:free | exact, 75 s | exact, 47 s |

Decision: **app model `nvidia/nemotron-3.5-super-vl:free`** (exact on both, fastest), fallbacks
Nemotron 3 Ultra and Dots 3 Note; **judge `dots-studio/dots-3-note-preview:free`** (exact on both and a
different model family from the app model). Two patterns are a small sample; the full dev eval follows.

### Time budget
Flint hung for 22 minutes on one request: OpenRouter keeps slow connections alive, so the HTTP read
timeout never fires. Requests now run in a worker thread with a **hard deadline**; reading one pattern with
the LLM has a total budget of 60 s (`PARSE_TIME_BUDGET_S`) across models, retries and the repair attempt.
A rate-limited or timed-out model is retried once, then the next model is tried. When the budget runs out
the user gets a clear message (and, in hybrid mode, whatever the grammar could read). Separate target added
for the report: **pattern reading ≤ 60 s** (one-time setup step), distinct from ≤ 15 s per chat turn.
Check: cable scarf via LLM → correct in 32 s on the first attempt.

## 4.4 Explainer (UC1)
`facts.py` builds a **fact sheet** from the IR and the simulation: overview (construction, cast-on, total
rows, gauge), one block per step (each written row described with `display.describe_row`, start → end
stitches, change, stated vs computed count; for repeats: the rule and how many repeats/rows it means at the
gauge), and the KB definition of every abbreviation used. `components/explainer.py` sends it to the LLM
(`prompts/explainer.md`: beginner-friendly, one section per step, cite abbreviations as `[k2tog]`, use only
the facts). **Grounding check in code:** every standalone number in the answer must be in the fact sheet,
every citation must be an abbreviation the pattern uses; violations are sent back once, remaining ones are
shown to the user as a warning. Optional focus ("Row 3", "the crown") explains one part only.

## 4.5 Yarn advisor (UC3)
- **Linker** (no LLM): normalisation → fuzzy brand detection (incl. shop vs Ravelry names, a brand named
  twice) → name scoring (exact > all typed words contained, fewest extra words, plain variants such as
  "Solids"/"Classic" preferred > fuzzy ratio; colour numbers tried with and without) → match / ambiguous
  (same name in two brands, no brand given) / none.
- **Facts** (code): CYC category, needle and gauge range with their source (label or CYC), the CYC
  guideline, a suggested starting needle (midpoint, plus the fibre's needle adjustment, rounded to a
  standard size), the Q9 gauge warning, and the fibre KB entry.
- **Advisor** (LLM, `prompts/yarn_advisor.md`) answers the question from the facts; same number/citation
  check as the explainer (citations `[yarn:id]`, `[cyc:n]`, `[fibre:x]`).
- UI: the Yarn tab shows the linked yarn and the code-computed numbers immediately; the LLM is only called
  for the written answer.

## 4.6 Gauge adjustment (UC2)
`src/knit_copilot/gauge.py`, no model calls.
1. **Flatten the size**: every per-size value is resolved for the chosen size.
2. **Width**: target = cast-on × knitter sts / pattern sts. Candidate counts around the target (±30 %) are
   tried in order of distance; a candidate is **valid** when the whole piece simulates (every "rep to end /
   to last n sts" fits). For each candidate, single fixed-count repeats in a row ("(p2, k6) ×2") are re-solved
   for the new width, and "repeat until N sts" targets are scaled — except a target equal to the cast-on (a
   corner/point, e.g. the bias dishcloth) which follows the new cast-on.
3. **Length**: "until X cm" is unchanged (the simulator converts it with the knitter's row gauge); fixed
   repeat counts of row blocks are scaled by the row ratio (total passes, rounded).
4. **Report**: changes (old → new), finished width (widest point) and length before/after, and a note when a
   large motif makes an exact fit impossible (e.g. feather & fan: 18-stitch motif = steps of 10 cm), with the
   advice to change needle size.

## 4.7 Rewriter (UC2 text)
`components/rewriter.py`, prompt `prompts/rewriter.md`. Code derives an **edit list** from the adjusted IR
(gauge line, cast-on, stated counts, repeat counts written as totals, "repeat until" targets, one size). The
LLM applies only these edits to the original text. The result is **re-parsed (hybrid) and simulated** at the
knitter's gauge and must match the adjusted IR row by row; one repair with the concrete mismatch; otherwise
the **code-rendered** version (generator's terse renderer, also verified) is shown with a warning.
UI: Pattern → "My gauge" tab (swatch inputs → changes table, width/length before and after, notes →
"Write my version of the pattern").

## 4.8 Charts (UC4)
`src/knit_copilot/charts.py`, no model calls. The chart is built from the same expansion as the simulator:
one cell per stitch on the needle after the row; an op that makes n stitches spans n cells (cables drawn as a
diagonal across the crossed stitches, direction from the KB lean); ops that make no stitch have no cell;
narrower rows are padded with grey "no stitch" cells. Row 1 at the bottom, numbered with the pattern's row
numbers; RS rows and rounds read right → left (number on the right), WS rows left → right (number on the
left) with WS symbols (a knit on the WS is drawn as a purl bump •). Legend from the KB.
- **Default rows**: the block with the most stitch work (ops other than knit/purl), then the most distinct
  rows — e.g. the eyelet rows 1–4, the cable rows 1–8, the hat **crown**.
- **Motif mode** (automatic above 48 stitches, or chosen): edge stitches + one repeat, boxed in red. For
  rows with a multi-stitch repeat the first iteration is kept; for one-stitch repeats ("p to last 2 sts")
  the width ÷ number of repeats; plain rows that don't divide evenly are cut to the nearest motif row's width.
  The hat crown becomes the usual wedge (7, 7, 6, 6, … 1 stitches).
- UI: Pattern → Chart tab (rows multiselect, auto / full width / one repeat, PNG download).
- Fixes during development: default-row selection compared a score with a count (picked border rows);
  piece row numbers replaced by pattern row numbers; feather & fan plain rows misaligned in motif mode.

## 4.9 Markers (added for real patterns)
Real patterns shape with markers ("knit to 3 sts before the next marker", "[k1, p1] to last 4 sts before m").
- IR: `Until(remaining, marker=True)` — the repeat stops `remaining` stitches before the next marker.
- Simulator: per row, marker positions on the left needle (row-start coordinates) and on the right needle;
  `pm` places, `sm` slips, `rm` removes; knitting past a marker moves it implicitly, but **only when a stitch
  is consumed** (an increase at a marker stays before it); flat rows mirror marker positions, in the round the
  end of the round counts as the beginning-of-round marker; repeats whose length depends on the position
  (nested "to marker" inside "rep to end") run dynamically and must land exactly.
- Each worked row stores a record of the real repeat counts; display, fact sheets and charts read it instead
  of recomputing (which is impossible once stops depend on markers).
- Stated counts are checked on the first time a row is worked only.

### Parser: marker syntax and named rows
- Grammar: stops "to marker", "to N sts before (the next) marker / m" for single stitches, star repeats and
  bracket groups; `pm` / `sm` / `rm` and their spelled-out forms; row names made of words ("Dec rnd", "Set-up
  row", "Inc Row 3"; rounds detected from "rnd/round" in the name); ranges with a prefix ("Dec Rows 1–2");
  a repeated name gets " (2)". **No silent drops:** any "Name: instruction" line the grammar cannot read is
  now a warning (before, lines like "Dec rnd: …" were skipped without a warning — found on the marker set).
- LLM prompt (`prompts/parser.md`): marker ops, `"marker": true` stops, named rows.

# 5. Evaluation

CRISP-DM phase 5. Targets: `docs/01_business_understanding.md` §1.8. Iterate on **dev**, report **test**.
Raw results: `results/<component>_<split>.json`.

## 5.1 Parser

| Version | Parser | Split | n | answered | exact when answered | parse success | row count agreement | op F1 | exact match | side acc. |
|---|---|---|---|---|---|---|---|---|---|---|
| v1 | grammar | dev (synthetic) | 36 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| v1 | hybrid (grammar first) | dev | 36 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| v1 | llm (Nemotron 3.5 Super) | dev | 36 | 0.556 | **1.000** | 0.556 | 0.594 | 0.718 | 0.556 | 1.000 |
| v1 | llm, missing cases re-run after the daily quota reset | dev | 36 | 0.944 | **1.000** | 0.944 | 0.949 | 0.978 | 0.944 | 1.000 |

**Marker set** (`parse_cases_markers.jsonl`, 20 cases): grammar v2 (marker syntax) dev 12/12 and test 8/8
exact; original set unchanged (dev 36/36, test 27/27 — first run of the original test split for the grammar).
Before the change the grammar read the shawls with warnings and **silently skipped** the named crown rows of
the hats; a warning for unread instruction lines was added. **LLM parser with the marker prompt** (dev, 12):
answered 5, **all 5 exact** (marker stops included); 7 stopped at the 60 s budget (busy free models) —
again an availability problem, not an accuracy one.

**LLM parser: accuracy vs availability.** Every pattern the LLM answered was parsed exactly (20/20, op
precision 1.00, all styles incl. verbose, UK and typos). All 16 failures are availability, not errors:
- 13 consecutive cases (parse-050 … 063) at the end: OpenRouter returned **429 "free-models-per-day"** — the
  free tier allows **50 free-model requests per day**, used up by the model comparison and this eval;
- 3 cases hit the 60 s parse budget (busy free models).
The per-style numbers for the LLM (e.g. imperial 0.167) therefore reflect *which* cases came late in the run,
not difficulty. **Re-run after the quota reset:** 34/36 answered, all 34 exact; the 2 misses hit the 60 s
budget (busy free models). The eval now reports `answered` and `exact_when_answered` separately. The 16 cases will be
re-run when the quota resets (answered cases are cached, so a re-run costs only the missing calls).

**Consequences for the design:** the free tier makes the LLM unsuitable as the *only* parser; **hybrid**
(grammar first, LLM only as fallback) is the default — it answers 100% at zero cost, and the LLM is kept for
text the grammar cannot read (real patterns, Part D). The daily quota is a constraint for all LLM evals.

**Iterations (grammar, dev):**
1. First run: 35/36 exact. Failure: verbose "Knit 2 together to the end of the round" — the "to the end"
   rule only covered knit/purl. Fix: generic `<op> to the end of the row/round` after phrase
   normalisation → 36/36.

**Reading the 100% honestly.** The grammar and the generator were written with the same notation
conventions, so synthetic text is the grammar's home ground; this number is an upper bound, not
evidence that it reads real patterns. The meaningful comparisons are:
- grammar vs LLM vs hybrid on the **Ravelry** patterns (free-form prose, glossaries, "work as for…"), and
- the LLM parser on synthetic text (it was not written with the generator in mind).
The test split has not been used yet.

## 5.2 Abbreviation lookup and retrieval (UC6)

`eval/eval_kb.py` on `kb_queries.jsonl`: 25 exact lookups (variants, UK terms, typos) and 25 questions.
Retrieval metrics on questions: hit@1, recall@3 (|relevant ∩ top-3| / min(3, |relevant|)), MRR.
Target (§1.8): exact accuracy ≥ 0.98, recall@3 ≥ 0.85.

**Exact / fuzzy lookup:** accuracy **1.00** on dev (15) and test (10), including typos (`sskk` → ssk,
`k2tgo` → k2tog) via fuzzy alias matching; no question is answered by the lookup path with a wrong entry.

**Question retrieval, iterations (recall@3):**

| Version | Change (one at a time) | Split | BM25 | Dense (bge-small) | Hybrid (RRF) |
|---|---|---|---|---|---|
| v1 | baseline: name + aliases + description + category/lean words | dev | 0.644 | 0.556 | 0.511 |
| v2 | BM25 stopwords ("how do I **make**…" matched "make one left"); BGE query prefix | dev | 0.667 | 0.578 | 0.567 |
| v3 | **label fix**: the two lean questions listed only 3 of 7 left-leaning / 3 of 4 right-leaning decreases; the system returned correct ones (sk2p, sssk, p2tog tbl) marked wrong | dev | 0.756 | 0.600 | 0.656 |
| v4 | **data fix**: KB descriptions lacked facts any knitter knows (M1 leaves no hole, a yo makes an eyelet, a dropped stitch forms a ladder) | dev | 0.822 | 0.622 | 0.744 |
| v4 | first look at test | **test** | 0.750 | 0.783 | 0.783 |
| v5 | light stemming (slipping → slip, stitches → stitch), motivated by the two BM25 test misses | dev | 0.900 | 0.622 | 0.778 |
| v5 | | test* | 0.683 | 0.783 | 0.783 |

\* test was looked at after v4, so v5 test numbers are not an unbiased estimate.

**What this shows.** BM25 keeps improving on the 15 dev questions (0.644 → 0.900) while dropping on test
(0.750 → 0.683): its gains partly fit the dev wording. Dense retrieval with the small embedding model is
weaker on dev but steadier; **hybrid is the most stable across splits (0.778 / 0.783) and is the default.**
None of the methods reaches the 0.85 target on test.

**Why scores are not higher:**
- KB entries are short (one or two sentences): little text for BM25 and embeddings to match a paraphrase.
- Questions often describe an effect ("without a hole", "a ladder") rather than the stitch name.
- n is small (10 test questions): one question = 0.1 hit@1.

**Next improvements (not done yet):** a larger embedding model (bge-base) for the dense part; LLM query
rewriting ("left-leaning decrease" → "ssk skp decrease leans left") before retrieval; and a **fresh
held-out question set written by the author** without looking at the KB, to replace the used test split.

## 5.3 Yarn linker (UC3)

`eval/eval_yarn_linker.py` on 40 mentions (24 dev / 16 test). Accuracy = right decision (yarn / none /
ambiguous with the right candidates).

| Version | Change | Split | accuracy | top-1 | none precision | none recall | ambiguous recall |
|---|---|---|---|---|---|---|---|
| v1 | first version | dev | 0.958 | 0.947 | 0.750 | 1.000 | 1.000 |
| v1 | "Yarn Art Jeans": filler word "yarn" removed before brand detection → fixed order | dev | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| v1 | | **test** | 0.938 | 0.923 | 0.667 | 1.000 | 1.000 |
| v2 | brand named twice ("Garnstudio Drops Air") → other aliases of the detected brand removed | test* | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

\* fixed after seeing the test error; the clean test number is v1 (0.938). Unknown yarns are always
recognised as unknown (none recall 1.0), which matters most: a wrong match would give wrong needle advice.
Weak spot: the linker only knows the 219 yarns in the table; any other yarn falls back to fibre + weight.

## 5.4 Explainer (UC1)

`eval/eval_explainer.py`: one synthetic pattern per template (9 on dev), input = **gold IR** (isolated from the
parser). Code metrics: grounding (no number outside the fact sheet, no citation outside the pattern's
abbreviations), fact coverage (cast-on, every repeat count, the stitch count after every written row that
changes it, every non-basic abbreviation cited), citation recall, one section per step.

| Version | Change | grounded 1st try | grounded final | fact coverage | citation recall | structure | median time |
|---|---|---|---|---|---|---|---|
| v1 | first version | 1.000 | 1.000 | 0.960 | 1.000 | 1.000 | 26 s |
| v2 | prompt: give the count after each changing row (hat crown was summarised, coverage 0.64); fix "Rnds 1–1" headings | 1.000 | 1.000 | 0.944 | 0.889 | 1.000 | 29 s |
| v3 | check: a citation by *name* ("[yarn over: …]") is a problem → repair names the id | 0.889 | **1.000** | **1.000** | **1.000** | 1.000 | (cached) |

Error analysis: v2 fixed the hat (0.64 → 1.00) but the eyelet explanation (different sample, temperature
0.2) cited abbreviations by name, which code cannot verify → v3 makes this a check failure, and the repair
round fixes it. Remaining risk: the judge score (clarity for a beginner) is not measured yet — it needs the
judge model plus a human-rated calibration set. One v1 case took 19 min: the Mac slept 19:29–19:47
(confirmed in the system log); the 90 s budget itself works.

## 5.5 Gauge adjustment (UC2)

`eval/eval_gauge.py`: every synthetic pattern × 2 knitter gauges (±10–18 % stitches, ±5–12 % rows).

| Split | n | success | closest valid count (brute force) | motifs kept | width ≤ 1 cm | width misses unavoidable | width error mean / max | length ≤ 1 cm | length error mean / max |
|---|---|---|---|---|---|---|---|---|---|
| dev | 72 | 1.000 | 1.000 | 1.000 | 0.764 | 1.000 | 0.84 / 5.5 cm | 0.847 | 0.52 / 1.6 cm |
| test | 54 | 1.000 | 1.000* | 1.000 | 0.796 | 1.000 | 0.74 / 4.9 cm | 0.889 | 0.51 / 1.9 cm |

\* first run 0.981: the eval compared with the target rounded to 2 decimals (93.5 vs 93.5000…01), so two
equally close counts looked like a miss; the eval now uses the exact target and accepts ties.

**Reading the numbers.** The maths is right every time (closest valid count, motifs intact). The 1 cm width
target from §1.8 is not reachable for patterns with large motifs: feather & fan repeats every 18 stitches
(≈ 10 cm per step) and the cable scarf every 8 — **every** width miss is such a case, where no valid count
gets within 1 cm (mean width error per template: feather & fan 3.3–3.6 cm, cable 1.4–1.5 cm, all others
≤ 0.7 cm). The system says so and advises changing needle size. Length errors come from finishing on a whole
4- or 8-row repeat. Hand-calculated cases are unit tests (`tests/test_gauge.py`).

## 5.6 Charts (UC4)

`eval/eval_charts.py`: every written row of every synthetic pattern charted at full width and read back.

| Split | patterns | rows | ops match simulator | width = stitch count | symbols | reading direction | motif rows aligned | default shows stitch work |
|---|---|---|---|---|---|---|---|---|
| dev | 36 | 184 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 (11 motif charts) | 1.000 |
| test | 27 | 138 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 (8 motif charts) | 1.000 |

These are consistency checks of code against code (chart builder vs simulator), so 1.0 is the expected
result and mainly guards against regressions. The meaningful chart test is end-to-end: charts of **parsed**
real patterns (Part D), where a parsing error shows up as a wrong chart. A visual check of five templates
(eyelet, cable, feather & fan, hat crown, rib) found and fixed three presentation problems (§4.8).

## 5.7 Yarn advisor (UC3)

`eval/eval_yarn_advisor.py`, 16 dev cases, gold yarn id (isolated from the linker).

| Version | facts correct | needle size given (needle/gauge questions) | required facts mentioned | swatch warning (flagged yarns) | grounded 1st try | grounded final |
|---|---|---|---|---|---|---|
| v1 | 1.000 | 1.000* | 1.000 | 1.000 | 1.000 | 1.000 |

\* first scored over all questions (0.688): the 5 "misses" were care/suitability questions ("How do I wash
it?", "Is it good for a baby?") where a needle size is not expected — a metric specification error, fixed
before any change to the system. Required-facts matching accepts synonyms ("not very elastic" = "low
elasticity"); the list is in the script. Not measured yet: judge score (answer quality beyond the facts).
Median latency ≈ 11 s.

## 5.8 Rewriter (UC2 text)

`eval/eval_rewriter.py`, one pattern per template (9), adjusted to a tighter or looser gauge.

| Version | verified LLM rewrite | first try | code fallback | final output verified | style similarity LLM / code render |
|---|---|---|---|---|---|
| v1 | 0.778 | 0.778 | 0.222 | **1.000** | 0.714 / 0.554 |

Both fallbacks were time-outs of the free model (90 s budget), not wrong rewrites; every LLM rewrite that
came back passed the row-by-row check. The LLM keeps the original style much better than the code render
(similarity to the original text 0.71 vs 0.55; e.g. bias dishcloth 0.96 vs 0.02, because the code render uses
terse notation where the original was verbose). Robustness fix found in the log: during verification the
LLM parser once returned `gauge.stitch_pattern: null`, rejected by the schema → field made optional.

## 5.9 Router (intent classification)
Set: `data/eval/intents.jsonl` (dev 55, test 33, 11 intents). Rules are written from the intent definitions,
not from eval cases. The LLM part gets the intent definitions only (`prompts/router.md`), no examples.

| Version | Model | Split | Mode | Answered | Accuracy | Macro-F1 | Rule coverage / precision |
|---|---|---|---|---|---|---|---|
| v1 | — | dev | rules | — | — | — | 0.436 / 1.000 |
| v1 | — | test | rules | — | — | — | 0.515 / 0.941 |
| v2 | Nemotron (OpenRouter) | dev | hybrid | 36 / 55 | 0.636 (35/36 answered) | 0.724 | 0.436 / 1.000 |
| v3 | Gemini 3.5 Flash | dev | hybrid | 47 / 55 | 0.855 (47/47 answered) | 0.899 | 0.436 / 1.000 |
| v3 | Gemini 3.5 Flash | dev | llm | 54 / 55 | 0.964 (53/54 answered) | 0.972 | — |
| **v4** | Gemini 3.5 Flash-Lite | dev | hybrid | 55 / 55 | **0.982** | 0.982 | 0.436 / 1.000 |
| v4 | Gemini 3.5 Flash-Lite | dev | llm | 55 / 55 | 0.982 | 0.982 | — |
| **v4** | Gemini 3.5 Flash-Lite | **test** | hybrid | 33 / 33 | **0.939** | 0.938 | 0.515 / 0.941 |
| v4 | Gemini 3.5 Flash-Lite | test | llm | 33 / 33 | 0.939 | 0.939 | — |

v2 and v3 failures were free-tier quota errors (OpenRouter 50 requests/day; Gemini 3.5 Flash 20 requests/day), so
availability and accuracy are reported apart. v4 adds a pause between requests (`LLM_MIN_INTERVAL_S=4`) and uses
Flash-Lite (larger free quota): every case answered.

**Error analysis (v4).**
- dev and test, LLM: "What is blocking and do I need to do it?" → yarn_advice (gold knitting_question). Blocking
  depends on the fibre, so this is a borderline label. Both nodes answer from the KB.
- test, LLM: "how to read RS and WS" → abbreviation_lookup (gold knitting_question). RS/WS *are* KB abbreviations;
  the lookup answer is still useful.
- test, LLM only: "How do I do German short rows?" → knitting_question (gold out_of_scope). This is a real error:
  the router does not know which techniques are out of scope. The out-of-scope rule catches crochet, colourwork
  and sewing, but not short rows. Seen on test only, so it is not fixed here; the next step would be adding short
  rows to the out-of-scope rule (from the scope definition, not from this case). In the hybrid run the same
  message was classified correctly, so the model is unstable on it.
- test, rules: "Row 12 says 64 sts but I get 62, is the pattern wrong?" → setup (gold validate). The numbers rule
  fires on "64 sts"; it already skips texts with pattern notation, but not a question about counts.
Hybrid and LLM-only reach the same accuracy, but hybrid makes 44 % (dev) / 52 % (test) fewer model calls, and its
rule decisions have precision 1.0 (dev) / 0.94 (test). That is why the app uses hybrid.

## 5.10 Setup agent (tool calls)
Set: `data/eval/setup_cases.jsonl` (dev 18, test 12 dialogues: single and multi-slot messages, imperial units,
corrections, ambiguous and unknown yarns, locked project, status questions, messages that need no tool).

| Version | Model | Split | Answered | Tool sequence | Argument accuracy | Final state | No-tool correct |
|---|---|---|---|---|---|---|---|
| v2 | Gemini 3.5 Flash | dev | 8 / 18 (quota) | 1.000 | 0.889 | 1.000 | 1.000 |
| **v3** | Gemini 3.5 Flash-Lite | dev | 18 / 18 | 0.944 | 0.913 | **1.000** | 1.000 |
| **v3** | Gemini 3.5 Flash-Lite | **test** | 12 / 12 | 0.917 | 0.875 | **1.000** | 1.000 |

*Final state* is the metric that matters for the user (the project fields after the dialogue). Converting units
(US 8 → 5 mm, 18 sts over 4 in → 17.7 per 10 cm) happens in `project.py`, so the LLM never does arithmetic.

**Error analysis.** No error changed the project wrongly:
- "I'm using Jeans yarn" → `set_yarn(name="Jeans yarn")` (gold "Jeans"): the linker ignores "yarn" and still asks
  which of the 2 Jeans yarns. Counted as an argument miss.
- "gazal baby wool, 3mm" → `set_yarn(name="gazal baby wool")` (gold "Gazzal Baby Wool"): the prompt tells the agent
  to copy names as written, and the linker resolves the typo. The gold label and the prompt disagree; the label is
  kept (labels are not edited to raise a score).
- "Make it the crib size / and my gauge is 17 sts per 10 cm": two extra `get_project_status` calls (read-only).
- "I have everything, generate my pattern": the agent checked the status instead of generating. The test project
  has no gauge yet, so generating would have been refused anyway.

Eval fix found here: the final state compared yarn *names*, so a correctly linked "Alize Cotton Gold" failed against
the table's "Alize Cotton Gold Solids". Yarns are now compared by linked yarn id. This also exposed a display bug,
"DROPS DROPS Karisma" (brand repeated when the name already contains it), fixed with `yarn_linker.display_name`.

## 5.11 Real Ravelry patterns (reported apart from synthetic)
Set: 10 annotated free Ravelry patterns (5 full, 5 partial; `data/eval/ravelry/patterns.yaml`). The input is the
text extracted from the PDF, as a knitter would paste it. The gold IR was written by hand and simulates to every
count the designers print. Both stay private (copyright). Script: `eval/eval_parser_real.py`.
For partial patterns only the annotated section is scored.

### Parser
| Version | Parser | Answered | Verified | Rows to divergence | Row-count agreement | Op F1 | Exact |
|---|---|---|---|---|---|---|---|
| v1 | grammar | 0.5 | — | 0.0 | 0.0 | 0.0 | 0 / 10 |
| v2 | llm (Gemini 3.5 Flash) | 0.5 | 0.5 | 0.099 | 0.356 | 0.475 | 0 / 10 |
| v3 | llm, fixed scoring + parser fixes | **1.0** | 0.6 | **0.431** | 0.417 | 0.591 | **3 / 10** |
| v3 | grammar, same scoring | 0.5 | — | 0.0 | 0.0 | 0.0 | 0 / 10 |

Hybrid = grammar first, then the LLM. The grammar reads none of the real patterns, so on this set hybrid gives the
same results as llm. Gemini 3.5 Flash with `LLM_REASONING_EFFORT=low`; under the free per-minute limit some answers
came from the fallback model `gemini-3.5-flash-lite`.

**v2 → v3: error analysis of the LLM parser.** Each pattern's first differing row was compared with the gold
(script: `eval/eval_parser_real.py`). There were three kinds of causes:

*A. Scoring treated equal knitting as different (eval fixes, documented in the script's docstring):*
- Legwarmers: the only difference was a beginning-of-round marker (`sm`). Markers make no stitch and are
  optional, so marker ops are now left out of the comparison.
- Sherbet Bandana: "SL 1 PWISE WYIF" was read as two KB ops `sl_pw` + `wyif` instead of the one KB stitch
  `sl_wyif`. The knitting is the same, so the pair now equals the single stitch.
- Nick Chopper: the size was not found ("S/M" in the gold, "S/M Adult" in the parse), so the Kids size was scored
  against the S/M gold. Sizes are now matched by name, or else by position.

*B. The parser threw away valid readings (system fixes, general rules):*
- The Sigrid Scarf gives no row gauge, so "work until 28 cm" could not be simulated and the parser rejected a
  correct reading. A missing row gauge is missing information, not a reading error: the parser now checks such
  patterns with a typical row gauge (1.4 × the stitch gauge) and warns. Sigrid is now **exact**.
- When verification fails after the repair round, the parser now keeps the last IR as `unverified`. The app never
  uses it; the eval scores it up to its first simulation error. This separates "no answer" (availability) from
  "wrong answer" (accuracy).

*C. Real reading errors (no fix: the patterns are the test set):*
| Pattern | What went wrong | Caught by the simulator? |
|---|---|---|
| Blueberry, Moose, headscarf, Double Hat | stitch counts in a row do not add up (row 1 or a set-up round with markers) | yes: the app would show an error, not a wrong pattern |
| 3x1 Hood | one extra pair of rows before the set-up row ("repeat until …, end with a WS row") | no: 57 / 58 rows right |
| Nick Chopper | set-up and rib section in the wrong order; repeat counts lost (24 rows instead of 97) | no |
| Sister Scarf | the rib section was skipped, and "until the desired length" was not turned into rows | no |

Four of the seven wrong readings were caught by the simulator, so the user would see "cannot read this pattern"
instead of wrong numbers. The three that pass the check are wrong in **structure** (which rows repeat, how often),
not in stitch arithmetic. These are the errors the row-count self-check cannot see. The next improvement would be
to check the parsed pattern against counts the designer states in prose ("you have knitted 23 rows",
"measures 9 cm"), which the gold work showed most real patterns contain.

**Error analysis (grammar).** The grammar reads synthetic notation perfectly (dev 36/36, test 27/27, markers 20/20)
and fails on every real pattern. Causes, from the parser warnings:
1. Stitches written in words: "Knit one, purl until the last stitch", "slip 1 stitch purl-wise with the yarn
   held in front", "SL 1 PWISE WYIF" (Sigrid, Sister Scarf, Sherbet).
2. Whole-row phrases: "P all stitches", "purl all sts", "K until 2 sts remain", "P4 (K1, P3) until 1 st remains"
   (Blueberry, headscarf, 3x1 Hood).
3. Lengths and repeats in prose: "Work then in Stockinette stitch until the hat measures …", "Work 9.5 cm in
   (k1, p1) ribbing", "Repeat row 1 and 2 until the work measures …" (Double Hat, Moose).
4. Layout: PDF line breaks split one instruction over two lines; colour labels in row headers
   ("Rounds 1-4 (Color A):"); a cast-on written inside a sentence (Legwarmers, Nick Chopper).

The grammar was **not** tuned on these patterns: they are the parser's test set. The result is the
expected one and shows why the system needs a language model: the variety of real wording cannot be covered by
hand-written rules. The LLM and hybrid runs are the main real-pattern result and are pending. Real patterns are
also much longer than synthetic ones, so PARSE_TIME_BUDGET_S may need to be raised for them; record it if so.

### Charts (UC4) on the gold IR
`python -m eval.eval_charts --split ravelry`: 10 patterns, 66 written rows. ops_match, width_match,
symbol_match and direction_ok are 1.0. 3 patterns are charted in motif mode, all aligned, and every default chart
shows the stitch work. The chart builder works on real constructions (markers, size-dependent repeats, shifting
increases) as well as on synthetic ones.

### Explainer (UC1) on the gold IR
`python -m eval.eval_explainer --split ravelry`. Input is the hand-made gold IR, so explanation quality is measured
apart from parser errors. Gemini 3.5 Flash-Lite. The explanation text is not saved (it restates a copyrighted pattern).

| Version | Answered | Fact coverage | Citation recall | Grounded (first / final) | Structure | Median time |
|---|---|---|---|---|---|---|
| v4 | 10 / 10 | **0.992** | 0.975 | 0.9 / 0.9 | 1.0 | 4.1 s |

The synthetic dev set (5.4) scored 1.0 / 1.0 / 0.889 → 1.0; the real patterns are longer (up to 267 rows) and use
markers, slipped edges and size-dependent repeats, and scores stay close.

**Error analysis.**
- Double Hat: the slip-marker abbreviation `[sm]` was used but not cited (coverage 0.92, citation recall 0.75).
- stickjournalen's headscarf, not grounded after the repair round: the explanation says "do this group of 7
  stitches 12 times". This is **correct** (k2tog, k1, yo, k1, yo, k1, sl1-k1-psso uses 7 sts; 12 × 7 + 2 = 86), but
  7 is not on the fact sheet, so the strict number check rejects it. The check favours precision: it also blocks
  correct numbers that the model works out itself. Fix for a next version: put each repeat block's stitch count on
  the fact sheet. Not changed here, to keep the test run honest.
- LLM judge: pending. The judge runs on OpenRouter (a different model family from Gemini), and its free quota
  (50 requests/day) was used up on the day of the run.


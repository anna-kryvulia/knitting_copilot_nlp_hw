"""Builds notebooks/report.ipynb (the assignment report). Run from the repo root, then execute and export:
    python scripts/build_report.py && jupyter nbconvert --to notebook --execute --inplace notebooks/report.ipynb \
        && jupyter nbconvert --to html notebooks/report.ipynb
"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
C = []


def md(s):
    C.append(nbf.v4.new_markdown_cell(s.strip("\n")))


def code(s):
    C.append(nbf.v4.new_code_cell(s.strip("\n")))


md(r"""
# Knitting Copilot — NLP Assignment 1 report

**An NLP system with code-based verification for written knitting patterns.** It reads a pattern (semantic parsing
into a structured *Pattern IR*), explains it, adapts it to the knitter's own yarn and gauge, draws charts and keeps
count of rows. Language models translate between language and structure; code computes and checks every number.

| | |
|---|---|
| Repository | `README.md` (setup and run), `docs/` (CRISP-DM phase documents), `eval/` + `results/` (evaluations) |
| Run the app | `streamlit run app.py` |
| Re-run this report | `jupyter nbconvert --to html --execute notebooks/report.ipynb` (numbers are read from `results/`) |
| LLMs | free models only: Gemini 3.5 Flash-Lite (Google AI Studio free tier); earlier runs on OpenRouter free models |
| Orchestration | LangGraph (`src/knit_copilot/graph.py`) |

**Contents.** 1 Business understanding · 2 Data · 3 System (diagrams, components, walkthrough, live demo) ·
4 Evaluation (every component) · 5 Agentic coding setup · 6 Limitations and next steps
""")

code(r"""
import json, subprocess, sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import Image, Markdown, display

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
pd.set_option("display.max_colwidth", 80)

def R(name):
    "metrics of results/<name>.json"
    d = json.loads((ROOT / "results" / f"{name}.json").read_text())
    m = d["metrics"]
    return m.get("overall", m), d

RED, GREEN, SAND, GREY = "#C8283C", "#2E7D4F", "#8C6A4F", "#B9ABA2"
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})
""")

# ---------------- 1 business ----------------
md(r"""
## 1. Business understanding

**Problem.** Knitting patterns are written in a compressed language: abbreviations (`ssk`, `sl1 pwise wyif`),
nested repeats (`*k2, p2; rep from * to last 2 sts`), several sizes in one line (`CO 88 (96, 104) sts`), US and UK
terms and imperial units. Knitters struggle to (a) understand a pattern, (b) adapt it when their gauge or yarn differs,
(c) see the stitch structure without a chart and (d) keep their place row by row.

**Users.** Beginners (need plain-English explanations and definitions) and intermediate knitters (adapt patterns to
their own yarn, metric units; yarns from the Ukrainian market).

| ID | Use case | Tier |
|---|---|---|
| UC1 | Explain a written pattern (row by row, with stitch counts and dictionary citations) | Must |
| UC2 | Adjust a pattern to the knitter's gauge (repeats kept whole, rewritten in the original style, verified) | Must |
| UC3 | Yarn advice: exact yarn or fibre + weight → needles (mm), expected gauge, fibre advice | Must |
| UC4 | Charts from a written pattern | Must |
| UC5 | Row-by-row tracker in a project: setup → generate working pattern (locked) → knit | Must |
| UC6 | Abbreviation knowledge base: lookup and questions | Must |
| — | Project setup by chat (LLM tool calls) | Must |
| — | Real Ravelry patterns in the evaluation | Must |
| UC7 | Validate a pattern (stated vs computed counts) | Could (basic version built) |
| — | Multi-piece garments, picking up stitches, mistake helper | Should (not built) |

**Business logic kept in scope** (`docs/01_business_understanding.md` §1.5, implemented in `project.py` with unit tests):
- **BR1 Stages.** Setup fields (yarn, needles, gauge, pattern, size) are editable until *Generate working pattern*;
  then the project is locked. *Start over* creates version N+1 and resets progress after a warning.
- **BR2 Prerequisites.** Generating needs pattern, size (if the pattern has sizes), gauge and needles; yarn is optional.
- **BR3 Always available.** Explain, lookup, yarn questions and validation never change the project.
- **BR4 Numbers by code.** Stitch counts, gauge maths, needle sizes and chart grids are computed in code; LLM output with
  numbers is shown only after it is checked (re-parse + simulation, or the fact sheet).
- **BR5 Metric only.** Imperial input (inches, US needles) is converted by code; output is always mm / cm / per 10 cm.
- **BR6 Grounding.** Definitions come from the knowledge base; unknown abbreviations are reported, not guessed.
- **BR7 Yarn table.** Brands popular in Ukraine, no Russian producers; each row records its source.
- **BR8 Repeats stay intact.** Gauge adjustment rounds to whole repeats instead of breaking a motif.

**Out of scope:** colourwork, short rows, crochet, languages other than English.

**From business needs to NLP tasks**

| Need | NLP task | Component |
|---|---|---|
| Understand notation | semantic parsing (text → Pattern IR) + unit normalisation | parser |
| Explain rows | grounded generation with citations | explainer |
| Find definitions | retrieval (exact/fuzzy + BM25 + dense, fused) | KB retrieval |
| Recognise a yarn | entity linking (typos, aliases, Cyrillic names, ambiguity) | yarn linker |
| Route a chat message | intent classification (rules + LLM) | router |
| Fill the project from chat | tool calling / slot filling | setup agent |
| Adapt the text | constrained rewriting in the original style | rewriter |
| Correct numbers | deterministic verification | simulator, gauge, charts, tracker |
""")

# ---------------- 2 data ----------------
md(r"""
## 2. Data

**Sources checked** (`docs/02_data_understanding.md`): Ravelry (API for yarns and pattern search; free pattern PDFs),
Craft Yarn Council standards (weights, needle ranges, abbreviations), Ukrainian yarn shops, Kaggle / Hugging Face.
No public dataset pairs knitting pattern text with a structured representation, so the labelled data is built here:

- **Knowledge base** (`data/kb/`): abbreviations with aliases (US/UK), stitch arithmetic (consumes / produces),
  chart symbols, descriptions in our own words and a reference per entry; fibres and techniques.
- **Yarn table** (`data/yarns.csv`): yarns from brands sold in Ukraine (Ravelry API + shop pages, source per row).
- **Synthetic patterns** (`src/knit_copilot/data/generator.py`): 11 templates (scarves, hats, dishcloths, lace,
  cables, markers…) × 5 writing styles (terse, brackets, verbose, UK, imperial) + typo noise, each with a gold IR
  and gold stitch counts.
- **Real patterns**: 14 free Ravelry patterns chosen by the author (recent and popular, 2022+), 10 in scope and
  hand-annotated. PDFs, text and gold annotations are copyrighted and stay in git-ignored `data/private/`; the repo
  keeps the metadata index and aggregate results.
- **Hand-written eval sets**: intents, setup dialogues, KB queries, yarn mentions, yarn questions.
""")

code(r"""
rows = []
for f in sorted((ROOT / "data" / "eval").glob("*.jsonl")):
    cases = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    sp = pd.Series([c.get("split", "-") for c in cases]).value_counts()
    rows.append({"eval set": f.name, "cases": len(cases), "dev": sp.get("dev", 0), "test": sp.get("test", 0)})
from knit_copilot import kb
from knit_copilot.components import yarn_linker
display(pd.DataFrame(rows))
print(f"Knowledge base: {len(kb.abbreviations())} entries · yarn table: {len(yarn_linker.yarns())} yarns")
""")

code(r"""
import yaml
meta = yaml.safe_load((ROOT / "data" / "eval" / "ravelry" / "patterns.yaml").read_text())
display(pd.DataFrame([{"pattern": m["title"], "designer": m["designer"], "year": m.get("year"),
                       "Ravelry projects": m.get("projects"), "role": m["role"],
                       "annotated": m.get("annotated", False), "coverage": m.get("coverage", "")} for m in meta]))
""")

# ---------------- 3 system ----------------
md(r"""
## 3. System

### 3.1 Data flow
Red: NLP components (an LLM is involved, its output is checked). Green: code only. Brown: data.
""")
code(r"""display(Image(filename=str(ROOT / "docs" / "diagrams" / "system.png"), width=1100))""")
md(r"""
**Why this design.** Free LLMs read language well but make arithmetic mistakes and are slow and rate-limited.
So the *Pattern IR* sits in the middle: the LLM's job is to translate text ↔ structure, and a **stitch simulator**
(driven by the knowledge base's stitch arithmetic) verifies every reading by working the pattern stitch by stitch.
A reading that does not add up is sent back once for repair, or rejected. Generation (explainer, yarn advisor) starts
from a **fact sheet built by code** and is checked for numbers and citations that are not on it. Gauge adjustment is
pure code; the rewriter's text is re-parsed and must simulate to the adjusted counts. A grammar parser reads common
notation without any model call (*hybrid* mode), which keeps the app usable under free-tier limits.

### 3.2 Chat graph (LangGraph)
""")
code(r"""display(Image(filename=str(ROOT / "docs" / "diagrams" / "chat_graph.png"), width=1100))""")

md(r"""
### 3.3 Components

| Component | Purpose | Input → output | Model calls | Tool calls |
|---|---|---|---|---|
| Router `components/router.py` | intent of a chat message (11 intents) | text, project stage → intent | LLM only when no rule applies (`prompts/router.md`) | — |
| Setup agent `components/setup_agent.py` | fill the project from chat | messages + project status → tool calls, reply | yes, ≤ 3 rounds per message | `set_yarn`, `set_needles`, `set_gauge`, `set_pattern`, `select_size`, `get_project_status`, `generate_working_pattern`, `start_over` → `project.py` |
| Parser `components/parser.py` (+ `parser_grammar.py`) | text → Pattern IR | pattern text → IR + warnings | hybrid: grammar first, LLM fallback with one repair round | simulator as verifier |
| Simulator `simulator.py` | work the pattern stitch by stitch | IR, size → rows with ops and counts, errors | — | — |
| Explainer `components/explainer.py` | plain-English explanation | IR → text with `[id]` citations | yes (`prompts/explainer.md`), one repair round | fact sheet (`facts.py`), number/citation check |
| KB retrieval `retrieval/search.py` | abbreviation lookup and questions | query → KB entries | — (local embeddings `bge-small`) | — |
| Yarn linker `components/yarn_linker.py` | free-text yarn → yarn table row | mention → match / ambiguous / none | — | — |
| Yarn advisor `components/yarn_advisor.py` | needles, gauge, fibre advice | yarn (or fibre + weight), question → answer | yes (`prompts/yarn_advisor.md`) | facts from table + CYC rules |
| Gauge adjuster `gauge.py` | recalculate for the knitter's gauge | IR, size, gauge → adjusted IR, changes | — | simulator |
| Rewriter `components/rewriter.py` | adjusted pattern in the original style | text + edits → text | yes (`prompts/rewriter.md`) | parser + simulator verify; code render as fallback |
| Charts `charts.py` | knitting chart | IR → grid → PNG | — | — |
| Project / tracker `project.py`, `tracker.py`, `db.py` | stages BR1–BR3, row position | project → status, current row | — | SQLite |
| Chat graph `graph.py` | wiring: route → one node → END | message → reply (+ chart / tracker) | via the components | trace per node (`tracing.py`) |

### 3.4 One input through the system
Message in the *My project* chat: *"I'm knitting YarnArt Jeans on US 6 needles, my swatch is 22 sts and 30 rows over 10 cm"*
1. **Router**: the "numbers" rule matches (mm / sts with digits, no pattern notation) → `setup`, no model call.
2. **Setup agent**: the LLM receives the tool list and the current project status and calls
   `set_yarn(name="YarnArt Jeans")`, `set_needles(size=6, system="us")`, `set_gauge(stitches=22, rows=30, over=10, unit="cm")`,
   copying numbers and units as written.
3. **Project rules (code)**: the yarn linker resolves the name to one row of `yarns.csv`; US 6 → 4.0 mm from a table;
   the gauge is stored per 10 cm; each tool returns ok + message (in a locked project every setter refuses).
4. The tool results go back to the LLM, which writes the reply. The project is saved in SQLite. The trace shows
   `route` (rule, no LLM) → `setup` (2 model calls, 3 tool calls); the app shows it under the reply (*LLM trace*).
5. **Generate working pattern** (button or chat): `gauge.py` finds the closest cast-on that keeps every repeat whole,
   simulates the adjusted pattern, shows a preview (cast on, width, length) and locks the project; the tracker starts.

### 3.5 Live demo (code path, no model calls)
The cells below run the deterministic part of that flow on our own example pattern.
""")

code(r"""
from knit_copilot import project, tracker, charts, gauge
from knit_copilot.simulator import simulate
from knit_copilot.display import row_lines

HAT = '''Hat
Sizes: S (M)
Needles: 4 mm
Gauge: 21 sts and 28 rows = 10 cm in stockinette.
CO 88 (96) sts.
Join to work in the round.
Rnd 1: *k2, p2; rep from * to end.
Repeat Rnd 1 3 more times.
Rnd 2: *k6, k2tog; rep from * to end.
BO all sts.'''

p = project.new_project("Report demo")
print(project.set_pattern(p, HAT).message)                       # hybrid: the grammar reads it, no LLM call
sim = simulate(p.pattern, "M")
display(pd.DataFrame([{"Rows": l.rows, "Instruction": l.instruction, "Stitches": l.stitches, "Worked as": l.worked_as}
                      for l in row_lines(p.pattern, sim, grouped=True)]))
""")

code(r"""
for r in [project.select_size(p, "M"), project.set_needles(p, 6, "us"), project.set_gauge(p, 18, 24, over=4, unit="in"),
          project.generate_working_pattern(p)]:
    print("ok" if r.ok else "refused", "·", r.message)
print("locked project, try to change needles:", project.set_needles(p, 5).message)
v = tracker.view(p)
while v.label != "Rnd 2" and v.rows_left:          # knit the rib rounds until the decrease round
    v = tracker.next_row(p)
print(f"tracker: {v.label} ({v.time_of or 'once'}) · {v.instruction} · {v.start_count} → {v.end_count} sts · {v.rows_left} round{'s' if v.rows_left != 1 else ''} left")
""")

code(r"""
from io import BytesIO
display(Image(data=charts.render_png(charts.build(p.working.pattern, None))))
""")

# ---------------- 4 evaluation ----------------
md(r"""
## 4. Evaluation

**Method.** Every component has its own script (`eval/eval_<component>.py`) and writes `results/<component>_<split>.json`.
Cases have `split: dev|test`: we iterate on dev and report test. Synthetic and real Ravelry patterns are reported
separately. Components are evaluated **in isolation** where possible (e.g. the explainer gets the gold IR, so parser
errors do not count against it), and end to end where it matters (parser on real text). Model availability (free-tier
quota, time-outs) is reported apart from accuracy (`answered` vs accuracy on answered cases).

**Choice of metrics.** Comparisons are made on *behaviour*, not surface form: the parser is scored on the simulation
of its IR (stitch operations and counts per row), so `k to end` and `k44` count as equal; generation is scored with
checkable facts (coverage, grounding, citations); retrieval with recall@3 / MRR; classification with accuracy and
macro-F1 plus rule coverage/precision; the setup agent with the final project state (what the user sees) as well as
tool sequence and arguments.

**Models.** Free models changed during the project as free-tier limits ran out (OpenRouter: 50 requests/day;
Gemini 3.5 Flash: 20/day). The table lists the model behind every result file; comparisons are only made between
runs of the same model, and code-only evaluations use no model.
""")

code(r"""
mrows = []
for f in sorted((ROOT / "results").glob("*.json")):
    d = json.loads(f.read_text())
    if not isinstance(d, dict) or "component" not in d:
        continue
    mrows.append({"component": d["component"], "split": d["split"], "version": d.get("version"),
                  "model": d.get("model") if d.get("model") not in (None, "none", "grammar") else "— (code only)",
                  "judge": d.get("judge_model") or "", "date": d.get("date")})
display(pd.DataFrame(mrows).sort_values(["component", "split"]).reset_index(drop=True))
""")

md(r"""
### 4.1 Overview against the targets (`docs/01_business_understanding.md` §1.8)
""")

code(r"""
def g(name, *keys):
    try:
        o, _ = R(name)
        for k in keys:
            o = o[k]
        return o
    except (FileNotFoundError, KeyError, TypeError):
        return None

rows = [
 ("Parser (grammar)", "exact match, synthetic", 0.95, g("parser_grammar_dev","exact_match"), g("parser_grammar_test","exact_match"), g("parser_grammar_ravelry","exact")),
 ("Parser (LLM)", "op F1, synthetic", 0.90, g("parser_llm_dev","op_f1"), g("parser_llm_test","op_f1"), None),
 ("Parser (LLM)", "op F1, real patterns", 0.75, None, None, g("parser_llm_ravelry","op_f1")),
 ("Parser (LLM)", "rows to first difference, real", None, None, None, g("parser_llm_ravelry","rows_to_divergence")),
 ("KB lookup", "exact lookup accuracy", 0.98, g("kb_lookup_dev","exact","accuracy"), g("kb_lookup_test","exact","accuracy"), None),
 ("KB retrieval (hybrid)", "recall@3 questions", 0.85, g("kb_lookup_dev","questions","hybrid","recall@3"), g("kb_lookup_test","questions","hybrid","recall@3"), None),
 ("Yarn linker", "accuracy", 0.90, g("yarn_linker_dev","accuracy"), g("yarn_linker_test","accuracy"), None),
 ("Yarn advisor", "facts correct", 0.95, g("yarn_advisor_dev","facts_correct"), g("yarn_advisor_test","facts_correct"), None),
 ("Explainer", "fact coverage", 0.85, g("explainer_dev","fact_coverage"), g("explainer_test","fact_coverage"), g("explainer_ravelry","fact_coverage")),
 ("Explainer", "grounded (final)", 0.95, g("explainer_dev","grounded_final"), g("explainer_test","grounded_final"), g("explainer_ravelry","grounded_final")),
 ("Gauge adjuster", "closest valid count", 1.0, g("gauge_dev","closest_valid"), g("gauge_test","closest_valid"), None),
 ("Gauge adjuster", "motifs kept", 1.0, g("gauge_dev","motifs_kept"), g("gauge_test","motifs_kept"), None),
 ("Rewriter", "final output verified", 0.90, g("rewriter_dev","final_verified"), g("rewriter_test","final_verified"), None),
 ("Charts", "ops match simulator", 0.98, g("charts_dev","ops_match"), g("charts_test","ops_match"), g("charts_ravelry","ops_match")),
 ("Router (hybrid)", "macro-F1", 0.90, g("router_hybrid_dev","macro_f1"), g("router_hybrid_test","macro_f1"), None),
 ("Setup agent", "final project state", 0.85, g("setup_agent_dev","state_match"), g("setup_agent_test","state_match"), None),
 ("Setup agent", "tool sequence", 0.85, g("setup_agent_dev","tool_sequence"), g("setup_agent_test","tool_sequence"), None),
]
overview = pd.DataFrame(rows, columns=["component", "metric", "target", "dev", "test", "real (Ravelry)"])
display(overview.style.format(precision=3, na_rep="—"))
""")

code(r"""
plot = overview.dropna(subset=["target"]).copy()
plot["best"] = plot[["test", "dev", "real (Ravelry)"]].bfill(axis=1).iloc[:, 0]
labels = plot["component"] + " · " + plot["metric"]
fig, ax = plt.subplots(figsize=(9, 6))
y = range(len(plot))
ax.barh(list(y), plot["best"], color=[GREEN if b >= t else RED for b, t in zip(plot["best"], plot["target"])], height=0.6)
ax.scatter(plot["target"], list(y), marker="|", s=300, color="#2E2522", label="target", zorder=3)
ax.set_yticks(list(y), labels, fontsize=8); ax.invert_yaxis(); ax.set_xlim(0, 1.05)
ax.set_xlabel("score (test where available, else dev; real-pattern rows use the Ravelry set)"); ax.legend(loc="lower right")
ax.set_title("Components against their targets (green = target met)")
plt.tight_layout()
from io import BytesIO
buf = BytesIO(); fig.savefig(buf, format="png", dpi=130); plt.close(fig)
display(Image(data=buf.getvalue()))
""")

md(r"""
### 4.2 Parser (semantic parsing)
Synthetic patterns: the grammar baseline and the hybrid parser read every pattern exactly (dev 36, test 27; marker set
20). This is an upper bound: the grammar and the generator share notation conventions. The LLM parser was exact on
every pattern it answered on dev (Nemotron; misses were free-tier time-outs and quota) and, on **test** with Gemini 3.5
Flash-Lite, answered all 27 with 25 exact (op F1 1.0; one decrease row off by 2 stitches, one stitch op different).

**Real Ravelry patterns (the parser's test set, 10 patterns).** Input is the text extracted from the PDF.
""")
code(r"""
real = []
for name, label in [("parser_grammar_ravelry", "grammar"), ("parser_llm_ravelry", "LLM (Gemini 3.5 Flash)")]:
    o, d = R(name)
    real.append({"parser": label, **{k: o[k] for k in ["answered", "verified", "rows_to_divergence",
                                                         "row_count_agreement", "op_f1", "exact"]}})
display(pd.DataFrame(real).style.format(precision=3))
o, d = R("parser_llm_ravelry")
display(pd.DataFrame([{"pattern": x["slug"], "coverage": x["coverage"], "verified": x["verified"],
                       "rows right before 1st difference": f'{x["same_prefix"]}/{x["rows_gold"]}', "exact": x["exact"]}
                      for x in d["patterns"]]))
""")
md(r"""
**Error analysis and iterations** (details: `docs/05_evaluation.md` §5.11).
- *Grammar 0/10*: real patterns write stitches in words ("Knit one, purl until the last stitch", "slip 1 stitch
  purl-wise with the yarn held in front"), use whole-row phrases ("P all stitches"), prose lengths and PDF line breaks.
  It was **not** tuned on these patterns (they are the test set). This is the main argument for an LLM parser.
- *LLM v2 → v3* (exact 0 → 3): three scoring problems treated equal knitting as different (an optional
  beginning-of-round marker; `sl_pw`+`wyif` vs the single stitch `sl_wyif`; size names "S/M" vs "S/M Adult"), and
  the parser threw away a correct reading because the pattern gives no row gauge (now a warning).
- *Remaining errors are real*: 4 readings do not add up and are **caught by the simulator** (the user sees
  "cannot read" instead of wrong numbers); 3 are structurally wrong but add up (an extra pair of rows, a skipped
  rib section, sections in the wrong order). Next step: check the parse against counts designers state in prose
  ("you have knitted 23 rows"), which most real patterns contain.
""")

md(r"""
### 4.3 Knowledge base: lookup and retrieval (UC6)
""")
code(r"""
kbrows = []
for sp in ["dev", "test"]:
    o, _ = R(f"kb_lookup_{sp}")
    kbrows.append({"split": sp, "exact lookup": o["exact"]["accuracy"],
                   **{f"recall@3 {m}": o["questions"][m]["recall@3"] for m in ["bm25", "dense", "hybrid"]},
                   "MRR hybrid": o["questions"]["hybrid"]["mrr"]})
display(pd.DataFrame(kbrows).style.format(precision=3))
""")
md(r"""
Exact/fuzzy lookup is perfect (typos like `k2tgo` → k2tog). Question retrieval misses its 0.85 target. Iterations on
dev (stopwords, label fixes, richer KB descriptions, stemming) raised BM25 from 0.64 to 0.90 on dev, but BM25 *fell* on
test (0.75 → 0.68): it was fitting the dev wording. Hybrid (BM25 + dense, reciprocal rank fusion) is the most stable
across splits and is the default. Why scores are limited: short KB entries; questions describe effects ("no hole",
"a ladder") rather than names; 10 test questions (one question = 0.1). Next: a larger embedding model, LLM query
rewriting, and a fresh author-written question set.

### 4.4 Yarn linker and yarn advisor (UC3)
""")
code(r"""
yl = [{"split": sp, **{k: R(f"yarn_linker_{sp}")[0][k] for k in ["accuracy", "top1_accuracy", "none_precision", "none_recall", "ambiguous_recall"]}} for sp in ["dev", "test"]]
display(pd.DataFrame(yl).style.format(precision=3))
display(pd.DataFrame([{"split": sp, **{k: R(f"yarn_advisor_{sp}")[0][k] for k in ["n", "facts_correct", "needle_mentioned", "must_mention", "warning_recall", "grounded_final"]}} for sp in ["dev", "test"]]).style.format(precision=3))
""")
md(r"""
Linker: the clean test number is 0.938 (one brand-named-twice case, "Garnstudio Drops Air", fixed after seeing it).
Unknown yarns are always recognised as unknown, which matters most: a wrong match would give wrong needle advice.
Advisor: all facts come from code (yarn label, CYC table, fibre KB), and they are correct in every case; the LLM writes
the answer. **Changing the model mattered:** with the original prompt, Gemini Flash-Lite answered narrowly (no fibre
for "What needle size?", no swatch warning for a washing question) — required facts 0.72 and warnings 0.5 on dev.
v5 made those rules unconditional in the prompt and lets **code** add the swatch warning if the answer lacks it
(it is a computed fact): dev 0.92 / 1.0, test 1.0 / 1.0 (test had been run once before v5, so it is not unbiased).
The judge score is not measured.

### 4.5 Explainer (UC1)
""")
code(r"""
ex = []
for name, label in [("explainer_dev", "synthetic dev"), ("explainer_test", "synthetic test"), ("explainer_ravelry", "real, gold IR")]:
    o, _ = R(name)
    ex.append({"set": label, "model": _["model"], **{k: o[k] for k in ["n", "fact_coverage", "citation_recall", "grounded_first", "grounded_final", "structure_ok"]}})
display(pd.DataFrame(ex).style.format(precision=3))
""")
md(r"""
Iterations: v2 asked for the count after every changing row (a hat crown had been summarised, coverage 0.64 → 1.0);
v3 made a citation by *name* a check failure so the repair round fixes it. On the real patterns one explanation was
rejected for the number 7 — which is **correct** (a 7-stitch repeat worked 12 times + 2 = 86) but not on the fact
sheet: the check favours precision and blocks numbers the model derives itself. Fix for a next version: add each
repeat block's stitch count to the fact sheet. **LLM judge** (different model family, on OpenRouter): not run — the
free quota was used up; it also needs calibration against human ratings before it can be trusted.

### 4.6 Gauge adjustment (UC2) and rewriter
""")
code(r"""
ga = [{"split": sp, **{k: R(f"gauge_{sp}")[0][k] for k in ["n", "closest_valid", "motifs_kept", "width_within_1cm", "width_error_unavoidable", "length_within_1cm"]}} for sp in ["dev", "test"]]
display(pd.DataFrame(ga).style.format(precision=3))
display(pd.DataFrame([{"split": sp, **R(f"rewriter_{sp}")[0]} for sp in ["dev", "test"]]).style.format(precision=3))
""")
md(r"""
The maths is right every time (the chosen cast-on is the closest count that keeps every repeat whole, checked by brute
force). The 1 cm width target is not reachable for large motifs: feather & fan repeats every 18 stitches (≈ 10 cm per
step) — **every** width miss is such a case where no valid count is closer, and the app says so and suggests a
different needle size. Rewriter: every LLM rewrite passed the row-by-row check on the first try on dev and test
(with the slower first model, 2 of 9 timed out and fell back to a code-written version), so the final output is always
verified. The LLM keeps the original style much better than the code render (similarity 0.79–0.85 vs 0.55–0.59).

### 4.7 Charts (UC4)
""")
code(r"""
display(pd.DataFrame([{"set": n, **{k: R(f"charts_{n}")[0][k] for k in ["patterns", "rows", "ops_match", "width_match", "symbol_match", "direction_ok", "motif_aligned"]}} for n in ["dev", "test", "ravelry"]]))
""")
md(r"""
These are consistency checks of code against code (chart builder vs simulator), so 1.0 is expected and guards against
regressions; on the real gold patterns too (markers, size-dependent repeats). A visual review of five templates found
three presentation problems (reading direction labels, motif box alignment, default rows), fixed before these runs.

### 4.8 Router (intent classification)
""")
code(r"""
rt = []
for mode in ["rules", "hybrid", "llm"]:
    for sp in ["dev", "test"]:
        try:
            o, d = R(f"router_{mode}_{sp}")
        except FileNotFoundError:
            continue
        rt.append({"mode": mode, "split": sp, "model": d.get("model"), **{k: o.get(k) for k in ["accuracy", "macro_f1", "rule_coverage", "rule_precision", "llm_calls"]}})
display(pd.DataFrame(rt).style.format(precision=3, na_rep="—"))
""")
md(r"""
Rules alone decide 44–52 % of messages with precision 1.0 / 0.94; the LLM handles the rest. Hybrid and LLM-only reach
the same accuracy, but hybrid needs about half the model calls — important under free-tier limits. Errors: two
borderline labels ("What is blocking?" → yarn advice; "how to read RS and WS" → abbreviation lookup), one real gap
("German short rows" not recognised as out of scope; seen on test only, not fixed), one rule misfire ("Row 12 says
64 sts but I get 62…" → setup). Earlier runs (v2, v3) lost cases to free-tier quotas (OpenRouter 50 requests/day,
Gemini 3.5 Flash 20/day); v4 paces requests and uses Flash-Lite, and every case was answered.

### 4.9 Setup agent (tool calling)
""")
code(r"""
sa = [{"split": sp, **{k: R(f"setup_agent_{sp}")[0][k] for k in ["n", "answered", "tool_sequence", "args_accuracy", "state_match", "no_tool_correct"]}} for sp in ["dev", "test"]]
display(pd.DataFrame(sa).style.format(precision=3))
_, d = R("setup_agent_test")
display(pd.DataFrame([{"case": f["id"], "messages": " / ".join(f.get("turns", [])), "expected": [w["tool"] for w in f.get("want", [])],
                       "called": [x["tool"] for x in f.get("got", [])]} for f in d["failures"]]))
""")
md(r"""
The final project state — what the user actually gets — is correct in every dialogue (30/30). The argument and
sequence misses change nothing: an extra read-only status call, a yarn name copied with its typo as the prompt asks
("gazal baby wool", which the linker resolves), and "generate my pattern" answered by checking the status first (the
test project had no gauge, so generating would have been refused). An eval bug was found on the way (yarns compared
by name: "Alize Cotton Gold" vs the table's "Alize Cotton Gold Solids" → now by linked id), and with it a display bug
("DROPS DROPS Karisma").

### 4.10 Deterministic parts: unit tests
Simulator, gauge maths, chart grid, tracker, project stages, unit conversion and the metrics have unit tests.
""")
code(r"""
out = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")], capture_output=True, text=True, cwd=ROOT)
print(out.stdout.strip().splitlines()[-1])
""")

# ---------------- 5 agentic ----------------
md(r"""
## 5. Agentic coding setup

The system was built with an AI coding agent (Claude Code) steered by instruction files, not only by chat prompts:

| File | What it controls |
|---|---|
| `AGENTS.md` | framing (NLP system with code verification), tiers and their order, CRISP-DM rules ("no component without its eval", iterate on dev / report test, never copy eval cases into prompts, never edit labels to raise a score), division of labour (LLM vs code), architecture and module layout, data and copyright rules, tech stack, definition of done, don'ts |
| `CLAUDE.md` | imports `AGENTS.md`; Claude-specific rules: use the project skills, read the last log entries at the start of a session, read only relevant files, read the IR schema before parser/simulator/chart work |
| `docs/CONVENTIONS.md` | shared contracts: Pattern IR schema, intents, setup tools |
| `.claude/skills/` | repeatable procedures (below) instead of re-explaining them in chat |
| `docs/crisp-dm-log.md` | one entry per task: phase, what, why, numbers, next step; read at the start of each session (context recovery) |
""")
code(r"""
import re
sk = []
for f in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
    t = f.read_text()
    desc = re.search(r"^description:\s*(.+)$", t, re.M)
    sk.append({"skill": f.parent.name, "description": (desc.group(1).strip() if desc else "")[:150]})
display(pd.DataFrame(sk))
log = (ROOT / "docs" / "crisp-dm-log.md").read_text()
entries = [e for e in re.findall(r"^## (\S+) — (.+?) — (.+)$", log, re.M) if e[0][:1].isdigit()]
loops = sum(1 for _, ph, _ in entries if ("4" in ph and "5" in ph))
revisions = sum(1 for _, ph, _ in entries if "revision" in ph)
print(f"CRISP-DM log (docs/crisp-dm-log.md): {len(entries)} entries, each with phase, what, why, numbers and next step.")
print(f"Path: Business → Data → Data preparation (parts A–D) → Modeling ⇄ Evaluation ({loops} combined iterations) "
      f"→ Data understanding revised {revisions}× for the real patterns → Deployment (app, report).")
""")
md(r"""
**What the instruction files changed in practice** (examples from the log):
- *Test discipline.* When the grammar parser scored 0/10 on real patterns, the rule "real patterns are the test set"
  kept the agent from tuning it on them; the finding was reported instead. Likewise the router's short-rows gap.
- *Labels are not edited to raise scores.* Where gold labels and system behaviour disagreed (setup agent "gazal baby
  wool"), the label was kept and the disagreement documented; real label errors were fixed only with a written reason
  (KB lean questions).
- *Numbers by code.* Every LLM component got a code-side check (simulation, fact sheet, re-parse) because AGENTS.md
  forbids showing unchecked numbers.
- *Copyright.* Ravelry text and gold annotations stay in `data/private/`; eval scripts avoid writing pattern text
  (e.g. explanations of real patterns are not saved).
- *Where the agent needed correcting:* the author steered scope (metric only, Ukrainian yarns, Ravelry patterns as a
  Must), reviewed data choices (modern patterns), and flagged UI problems (row table, setup flow) that metrics did not
  show.

## 6. Limitations and next steps
- **Real-pattern parsing** is the weakest point (3/10 exact; 4 more rejected safely). Next: verify against counts
  stated in prose, add markers/pick-ups to the grammar, few-shot with *synthetic* examples of prose styles.
- **Free-tier models** shape the design (hybrid router and parser, caching, pacing) and limit evaluation volume; the
  LLM judge for explanation/advice quality was not run and needs human calibration.
- **Retrieval** misses the 0.85 target on questions; small test sets (10–33 cases) make single errors move scores a lot.
- **Should tier** (multi-piece garments, picking up stitches, mistake helper) was not built.
""")

nb["cells"] = C
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, "notebooks/report.ipynb")
print("written", len(C), "cells")

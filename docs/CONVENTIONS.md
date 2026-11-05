# Conventions

Detailed conventions referenced from `AGENTS.md`.

## Folder layout

```
knitting_copilot_nlp_hw/
├── AGENTS.md, CLAUDE.md          # agent instructions
├── .claude/skills/               # reusable agent workflows
├── app.py                        # Streamlit UI (Setup tab → Knitting tabs: Pattern / Chart / Tracker / Chat)
├── src/knit_copilot/
│   ├── config.py                 # settings from .env
│   ├── llm.py                    # the only LLM entry point (retry, fallback, cache, JSON validation)
│   ├── tracing.py                # per-node trace records
│   ├── ir.py                     # Pattern IR Pydantic models
│   ├── kb.py                     # loads data/kb/*.yaml (abbreviations, techniques, fibres)
│   ├── units.py                  # imperial → metric, US needle → mm
│   ├── simulator.py              # executes IR row by row (pure Python)
│   ├── gauge.py                  # gauge adjustment maths (pure Python)
│   ├── charts.py                 # IR + simulation → chart grid → PNG/SVG
│   ├── tracker.py                # row tracker (pure Python)
│   ├── project.py                # project stages: setup → locked versions
│   ├── db.py                     # the only SQLite access layer
│   ├── graph.py                  # LangGraph wiring
│   ├── components/               # router, setup_agent, parser, explainer, yarn_linker, yarn_advisor,
│   │                             # rewriter, kb_answer (LLM-facing components)
│   ├── retrieval/                # KB index building and search
│   └── data/                     # generator.py (synthetic patterns), yarn table builder
├── prompts/<component>.md        # one prompt file per LLM component
├── data/kb/                      # abbreviations.yaml, techniques.yaml, fibres.yaml, yarn_weights.yaml
├── data/yarns.csv                # Ukrainian-market yarns
├── data/eval/*.jsonl             # labelled eval sets
├── data/eval/ravelry/*.json      # annotations of real Ravelry patterns (no pattern text)
├── data/private/                 # Ravelry pattern files (git-ignored)
├── eval/eval_<component>.py      # one eval script per component + run_all.py
├── results/<component>_<split>.json
├── tests/                        # pytest unit tests
├── notebooks/evaluation.ipynb    # charts for the report
└── docs/                         # CRISP-DM phase docs, log, diagrams
```

## Pattern IR

Defined as Pydantic models in `src/knit_copilot/ir.py`. All measurements are metric.

```jsonc
{
  "title": "Simple Lace Scarf",
  "source": {"kind": "synthetic|ravelry", "url": null, "designer": null},
  "construction": "flat",                 // flat | round
  "gauge": {"sts_per_10cm": 22, "rows_per_10cm": 30, "needle_mm": 4.0, "stitch_pattern": "stockinette"},
  "sizes": ["S", "M", "L"],               // [] when one size
  "glossary": {"sk2p": "slip 1, k2tog, pass slipped stitch over"},   // pattern-specific abbreviations
  "pieces": [                             // Must tier: exactly one piece
    {
      "name": "body",
      "cast_on": {"S": 40, "M": 46, "L": 52},       // or a plain int when one size
      "steps": [
        {"type": "rows", "rows": [
          {"label": "Row 1", "side": "RS",          // RS | WS | round
           "ops": [
             {"op": "k", "n": 2},
             {"repeat": [{"op": "yo"}, {"op": "k2tog"}, {"op": "k", "n": 3}],
              "times": null, "until": {"remaining": 2}},   // times: int  OR  until: {"remaining": n} | "end"
             {"op": "k", "n": 2}],
           "stated_count": 40}                       // count printed in the pattern, if any
        ]},
        {"type": "repeat_rows", "rows_ref": ["Row 1", "Row 2", "Row 3", "Row 4"],
         "until": {"length_cm": 150}},              // or {"times": 10}
        {"type": "bind_off", "method": "loose"}
      ]
    }
  ]
}
```

Rules:
- `op` must be a key or alias in `data/kb/abbreviations.yaml` or in the pattern's `glossary`.
- Repeats can nest. A repeat has exactly one of `times` / `until`.
- Lengths ("work until piece measures 20 cm") stay as lengths in the IR; `gauge.py` converts them to
  rows using the knitter's gauge. This is what makes gauge adjustment possible.
- The simulator output per row is `{label, side, start_count, end_count, cells: [op per stitch]}`.

## Abbreviation KB entry (`data/kb/abbreviations.yaml`)

```yaml
- id: k2tog
  name: knit two together
  aliases: [k2tog, K2tog, knit 2 together]
  uk_term: null              # different UK name if any
  consumes: 2
  produces: 1
  category: decrease          # basic | increase | decrease | cable | slip | other
  lean: right                 # left | right | centre | null
  chart_symbol: "/"
  chart_symbol_ws: "/"
  description: "Insert the right needle into the next two stitches as if to knit and knit them together."
  reference: "Craft Yarn Council, Knitting Abbreviations Master List"
```

## Component contract

Each file in `components/` exposes one main function:

```python
def run(inp: <Component>Input) -> <Component>Output:
    """Purpose: ...
    Input: ...
    Output: ...
    Model calls: yes/no (which prompt)   Tool calls: ...
    """
```

- Input/Output are Pydantic models defined in the same file.
- No LangGraph imports. `graph.py` adapts state ↔ component input/output.

## Prompt files

`prompts/<component>.md` with sections:

```
# <component>
## System
...
## User template
... {placeholders} ...
## Output schema
(JSON description, must match the Pydantic model)
```

## Eval data format (JSONL, one case per line)

Common fields: `id`, `split` (`dev`|`test`), `component`, `source` (`synthetic`|`ravelry`|`handwritten`),
`input`, `expected`, `tags`, `notes`.

| File | `input` | `expected` |
|---|---|---|
| `intent_cases.jsonl` | message | `intent` |
| `setup_cases.jsonl` | dialogue | tool calls + final project fields |
| `kb_queries.jsonl` | question / abbreviation | KB entry ids (ranked) |
| `parse_cases.jsonl` | pattern text | gold IR + per-row counts |
| `explain_cases.jsonl` | pattern text | required facts per row (for faithfulness/coverage) |
| `yarn_link_cases.jsonl` | yarn mention | `yarn_id` or `null` |
| `yarn_advice_cases.jsonl` | yarn / fibre + weight | weight class, needle range (mm), gauge range |
| `gauge_cases.jsonl` | IR + knitter gauge + size | adjusted counts + finished dimensions (cm) |
| `chart_cases.jsonl` | IR | gold chart grid |

Tags describe difficulty, e.g. `easy`, `nested_repeat`, `in_the_round`, `multi_size`, `imperial_units`,
`uk_terms`, `custom_glossary`, `verbose`, `terse`, `typo`, `ravelry`.

## Results format

`results/<component>_<split>.json`:

```json
{"component": "...", "split": "dev", "version": "v2", "model": "...", "date": "YYYY-MM-DD",
 "metrics": {"overall": {}, "by_source": {"synthetic": {}, "ravelry": {}}},
 "n": 40, "failures": [{"id": "...", "why": "..."}]}
```

## Naming

- snake_case for modules/functions, PascalCase for Pydantic models.
- Intents: `setup`, `explain`, `yarn_advice`, `abbreviation_lookup`, `knitting_question`,
  `chart`, `tracker`, `out_of_scope`, `smalltalk`.
- Citations: `abbreviations:k2tog`, `techniques:tink_back`, `fibres:cotton`.

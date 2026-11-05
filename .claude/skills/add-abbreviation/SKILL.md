---
name: add-abbreviation
description: Add or fix entries in the knitting abbreviation knowledge base (data/kb/abbreviations.yaml) with correct stitch arithmetic, aliases, chart symbols and a reference. Use when the parser meets an unknown abbreviation or when extending the KB.
---

# Add an abbreviation

CRISP-DM phase: **3. Data Preparation**.

The KB drives the parser vocabulary, the simulator, chart symbols, the explainer and UC6 lookup, so
a wrong entry breaks several components at once.

## Steps

1. Read the entry format in `docs/CONVENTIONS.md` § Abbreviation KB entry, and grep
   `data/kb/abbreviations.yaml` for the abbreviation and its aliases to avoid duplicates.
2. Fill every field:
   - `consumes` / `produces`: stitches taken from the left needle / put on the right needle.
     Check: `k`=1/1, `k2tog`=2/1, `ssk`=2/1, `yo`=0/1, `m1l`=0/1, `kfb`=1/2, `s2kpo`=3/1, `c4f`=4/4.
   - `aliases`: all common spellings and casings, including spelled-out forms.
   - `uk_term`: set when UK patterns use a different name (e.g. US `bind off` = UK `cast off`).
   - `lean`, `category`, `chart_symbol` (RS) and `chart_symbol_ws` (WS view).
   - `description`: **in our own words**, one or two sentences, imperative.
   - `reference`: where the definition was checked (e.g. Craft Yarn Council master list).
3. Add a unit test to `tests/test_kb.py` if the entry has unusual arithmetic.
4. Run `pytest -q tests/test_kb.py tests/test_simulator.py`.
5. Rebuild the retrieval index (`python -m knit_copilot.retrieval.index`) and re-run the
   `kb_lookup` eval if entries changed.
6. Run `crisp-dm-checkpoint` when adding more than a couple of entries.

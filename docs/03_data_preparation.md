# 3. Data Preparation

CRISP-DM phase 3. Turns the sources from Phase 2 into the data the components use. Done in four parts:

| Part | Content | Status |
|---|---|---|
| **A** | Pattern IR schema, unit conversion, knowledge bases, yarn table | ✅ done |
| **B** | Stitch simulator + synthetic pattern generator with gold labels | ✅ done |
| **C** | Hand-written eval sets (intents, setup dialogues, KB queries, yarn mentions, yarn advice) | ✅ done |
| **D** | Annotations of real Ravelry patterns | ✅ gold written (10 of 14), ⏳ author review |

## 3.1 Part A

### Pattern IR (`src/knit_copilot/ir.py`)
Pydantic models for the schema in `docs/CONVENTIONS.md`: `Pattern → Piece → Step (rows | repeat_rows |
bind_off) → Row → Op | Repeat`. Decisions:
- **Multi-size values** (`CO 40 (46, 52)`) are stored as `{"S": 40, "M": 46, "L": 52}` wherever a number
  can differ by size (op counts, repeat counts, cast-on, stated counts); `resolve(value, size)` picks one.
- A repeat has **exactly one** stop rule: `times` or `until: {remaining: n}` (validated).
- "Work until the piece measures X cm" stays a **length** (`until_length_cm`), so gauge adjustment can
  turn it into a row count for the knitter's own row gauge.

### Unit conversion (`src/knit_copilot/units.py`)
Inches → cm, yards → m, gauge per 4 in → per 10 cm (× 10/10.16), US needle sizes → mm (CYC
conversion table), fractions ("5 ½").

### Abbreviation KB (`data/kb/abbreviations.yaml`, loader `src/knit_copilot/kb.py`)
74 entries: 47 stitch operations and markers + 27 instruction terms.

| Category | Entries | Examples |
|---|---|---|
| basic / slip | 8 | k, p, k tbl, sl1 wyib |
| increase | 9 | yo, m1l, m1r, kfb, lifted increases |
| decrease | 12 | k2tog, ssk, skp, k3tog, sk2p, s2kp (cdd) |
| cable | 10 | 1/1, 2/2, 3/3, 4/4 crosses, 2/1 purl crosses |
| other / marker | 8 | bo, co, drop, pm, sm, wyif |
| term | 27 | RS, rep, rem, patt, st st, gauge/tension, seed vs moss |

- Each stitch operation has `consumes`/`produces` (stitch arithmetic for the simulator), a lean, and
  RS/WS chart symbols. Descriptions are in our own words; reference: CYC.
- Aliases include spelling variants and **UK terms** (yfwd/yon/yrn → yo, cast off → bo, skpo → skp,
  tension → gauge, stocking stitch → st st). US "moss stitch" vs UK "moss stitch" (= US seed) is
  documented as an ambiguity.
- The loader normalises case, spaces and punctuation (`K2 Tog`, `k2-tog.` → k2tog) and **refuses
  ambiguous aliases** at load time. Removed during preparation: `inc` from kfb (also the generic term
  "increase") and the typo alias `co off`.

### Yarn weights and fibres (`data/kb/yarn_weights.yaml`, `data/kb/fibres.yaml`)
- CYC categories 0–7 with stitches per 10 cm, needle ranges (mm) and the mapping from Ravelry weight
  names; plus the list of standard metric needle sizes for rounding.
- 14 fibres (wool, merino, alpaca, mohair, cotton, linen, bamboo, viscose, acrylic, polyamide,
  polyester, angora, silk, cashmere): elasticity, warmth, drape, needle adjustment, good/avoid for,
  care, blocking, tips. Chosen to cover every main fibre found in the yarn survey.

### Yarn table (`data/yarns.csv`, builder `src/knit_copilot/data/build_yarns.py`)
**219 yarns** from 11 brands (20 most-used active yarns each; Vizell has 19).

| Step | Rule |
|---|---|
| Filter | Active only; Thread/Cobweb weights excluded |
| Name | Cyrillic alias in brackets moved to `aliases` ("Jeans (Джинс)" → name "Jeans", alias "Джинс"); spaces normalised |
| Units | yards → metres, gauge per 4 in → per 10 cm |
| Missing needle size (4 yarns) / gauge (21 yarns) | Filled from the CYC range of the weight; `needle_source` / `gauge_source` = `cyc` |
| Inconsistent label gauge (11 yarns, **Q9**) | Kept but `gauge_flag = outside_cyc_range` when the midpoint is > 3 sts/10 cm outside the CYC range (e.g. Nako Pirlanta: Sport weight, label gauge 17 sts). Lace weight is exempt (knitted on larger needles, §2.7 of Phase 2); this exemption was added in part C, which reduced the flags from 22 to 11 |
| Fibre | Ravelry fibre names mapped to fibre KB keys; `main_fibre` = largest share (all 219 mapped) |
| Popularity | `ravelry_rating_count` (Ravelry returns no project count for yarns) |

Distribution: Sport 57, Fingering 38, DK 37, Lace 23, Aran 21, Worsted 14, Super Bulky 14, Light
Fingering 12, Bulky 3. Main fibres: acrylic 67, cotton 43, merino 43, wool 35, alpaca 9, others 22.

New data quality finding:
- **Q9** — about 10% of Ravelry label gauges disagree with the yarn's own weight category. Likely causes:
  crochet or loose lace gauges entered as knitting gauge, or wrong weight category. Consequence: the
  yarn advisor shows the label value **and** the CYC range when the flag is set, and says the knitter
  should swatch.
- Only 1 yarn carries a Cyrillic alias in its Ravelry name, so the yarn linker cannot rely on Ravelry for
  Ukrainian spellings (English-only scope makes this acceptable).

### Tests
`tests/test_units_ir.py`, `tests/test_kb.py`: 48 tests (IR validation, unit conversion, stitch arithmetic
for 16 operations, 14 alias lookups, KB consistency, yarn weights, fibres). All pass.

## 3.2 Part B

### Stitch simulator (`src/knit_copilot/simulator.py`)
Executes a Pattern IR row by row using only the KB's stitch arithmetic. For every worked row it records
the row number, label, side, start and end counts, and the expanded list of stitch operations (the
input for charts, the tracker and the parser eval). It reports, with the row label:
- a repeat that doesn't fit ("3 st(s) left over before the last 2"),
- a row that leaves stitches unworked, an op that needs more stitches than are left, unknown ops,
- stated counts that differ from computed counts (`count_mismatches()`, input for the validator).

"Work until X cm" uses the row gauge (the pattern's or the knitter's), so the same IR gives a different
number of rows for a different gauge, which is what gauge adjustment needs. Repeats of row blocks stop
after whole blocks.

**IR change found while building it:** real patterns often say "repeat these rows until 44 sts
remain/are on the needle" (Gramma's Dishcloth, crown shaping). Added `until_count` to `repeat_rows`;
the simulator raises an error if the repeat moves away from the target.

### Templates (`src/knit_copilot/data/templates.py`)
9 templates that build gold IR with random parameters (stitch multiples always valid):

| Template | Construction | What it exercises |
|---|---|---|
| garter_scarf | flat | "k to end", repeat until length |
| rib_scarf | flat | 2x2 rib with star repeats, WS mirror |
| seed_cowl | round | rounds, alternating rounds |
| ribbed_hat | round, **3 sizes** | rib brim, body until length per size, 8-section crown decreases with stated counts |
| eyelet_scarf | flat | yo/k2tog/ssk lace, "to last 2 sts", named border rows |
| feather_fan | flat | **nested repeats** ((k2tog) 3 times inside a star repeat) |
| cable_scarf | flat | C6B/C6F crossings every 8 rows, repeats with a count |
| bias_dishcloth | flat | increases then decreases, **repeat until stitch count** |
| bordered_blanket | flat, **2 sizes** | garter borders, "k5, p to last 5 sts, k5" |

Each template was simulated for 20 random seeds and every size: no errors, all stated counts agree.

### Renderer and styles (`src/knit_copilot/data/generator.py`)
The same IR is written in one of five styles:

| Style | Example |
|---|---|
| terse | `Row 1 (RS): K2, *yo, k2tog, k3; rep from * to last 2 sts, k2. (44 sts)` |
| brackets | `Row 1 (RS): K3, (p2, k6) 2 times, p2, k3.` |
| verbose | `Rnd 1: Repeat [knit 1, purl 1] to the end of the round.` |
| uk | `Tension: …`, `yfwd`, `skpo`, `Cast off`, `stocking stitch` |
| imperial | `Needles: US 7`, `Gauge: 19 sts and 27 rows = 4 in`, `until piece measures 59 in` |

Details that make parsing realistic: multi-size numbers `88 (96, 104)`; "rep from * 2 more times"
(= 3 in total) vs "Work Rows 1–2 a total of 3 times"; stated counts in three formats (`(44 sts)`,
`— 44 sts`, `[44 sts]`); named rows without a side ("Inc row") because they are worked on both sides;
"until 4 sts remain" only when decreasing; headers (title, sizes, needles, gauge) and finishing notes.
**Typos** (≈ 30% of cases): casing (`K2tog`), spacing (`k2 tog`), missing punctuation, `-` instead of `:`.

For the imperial style the gold IR is converted from the rounded imperial values actually printed
(e.g. 59 in → 149.9 cm; 19 sts/4 in → 18.7 sts/10 cm), so text and gold always agree.

### Eval set: `data/eval/parse_cases.jsonl`
63 cases = 9 templates × 7, all 45 template × style pairs covered; split stratified by template:
**36 dev / 27 test**. Each case stores the text, the chosen size, the gold IR, total rows, final count
and per-row counts. Patterns have 43–571 worked rows and 11–27 text lines. 14 multi-size, 14 in the
round, 20 with typos.

How the parser eval will compare (Phase 5): by **simulating** both the parsed and the gold IR and
comparing per-row expanded operations and counts, not the IR structure. So `k to end` vs `k44` vs
`*k1; rep from * to end` all count as correct. Sides are compared only for rows whose text states one.

### Tests
`tests/test_simulator.py` (10), `tests/test_generator.py` (46: every template × style renders and
simulates; reproducibility; gold consistency). Total suite: 104 tests pass.

### Not covered by the generator (to be measured on real patterns)
Pattern-specific glossaries, "work as for…", charts-only instructions, prose like "continue in pattern
as set", short rows/colourwork (out of scope). These are the expected gap between synthetic and real
patterns.

## 3.3 Part C: hand-written eval sets

Human-readable sources in `data/eval/src/*.yaml` are compiled by `src/knit_copilot/data/build_eval_sets.py`
into JSONL. The build **validates every label against the real data**, so a typo becomes a build error
instead of a wrong gold label.

| File | Cases (dev/test) | Component | Gold label | Checked by the build |
|---|---|---|---|---|
| `intent_cases.jsonl` | 88 (55/33) | router | 11 intents × 8 | label set = CONVENTIONS, no duplicate texts |
| `setup_cases.jsonl` | 30 (18/12) | setup agent | ordered tool calls + resulting project state | known tools/args, sizes exist, **state computed by code** (US 8 → 5.0 mm; 18 sts/4 in → 17.7/10 cm) |
| `kb_queries.jsonl` | 50 (30/20) | KB lookup / retrieval | 25 exact lookups → 1 id; 25 questions → relevant ids + primary | ids exist, primary ∈ relevant |
| `yarn_link_cases.jsonl` | 40 (24/16) | yarn linker | yarn_id, `null`, or ambiguous candidates | `[brand, name]` resolves to exactly one row of `yarns.csv` |
| `yarn_advice_cases.jsonl` | 25 (16/9) | yarn advisor | CYC category, needle and gauge ranges (+ source), main fibre, facts to mention, gauge warning | numbers from `yarns.csv`/CYC; every `must_mention` fact exists in the fibre KB; `warn_gauge` agrees with the Q9 flag |

Splits are stratified (by intent, by first tag, by match/none) with a fixed seed; ~60% dev / 40% test.

Coverage highlights:
- Intents: `indirect` phrasings without keywords, typos, `ambiguous` messages (labelled with what the
  system should do first), messages that need project context ("Where was I?").
- Setup: single and multi-slot messages, imperial input (code converts), corrections ("no wait, 4.5"),
  ambiguous and unknown yarns, a locked project (no state change), messages that need **no** tool.
- KB: US/UK variants (yfwd, skpo, cast off), typos (sskk, k2tgo), questions without keyword overlap
  ("How can I add a stitch without leaving a hole?" → m1l, m1r, kfb, lifted increases).
- Yarn mentions: case/spacing/typos, Cyrillic alias (Джинс), colour numbers, brand missing, names that
  exist in two brands (Jeans, Baby Wool, Angora Gold → must ask), yarns not in the table (→ none).
- Yarn advice: label vs CYC values, flagged label gauges (must warn), fibre-only input (cotton DK, lace mohair).

**What the validation caught while building** (loop 3 → 3):
1. DROPS Kid-Silk (lace) was flagged as an inconsistent gauge although Phase 2 decided lace yarns follow
   their label → fixed the rule in `build_yarns.py` (lace exempt), flags 22 → 11.
2. Two of my advice labels were wrong: Himalaya Everyday *is* inconsistent (DK, label 17.7 sts) → must warn;
   YarnArt Merino De Luxe is *not* (label range 14.8–21.7, midpoint within tolerance) → relabelled
   as `wide_gauge_range`.

**Human review:** `docs/data/eval_review_sample.md` holds a random 20% sample of each set with a checkbox
per label, to be checked by the author. Fixed labels are recorded here.

Not built yet (they need components from Phase 4 to exist first): gauge-adjustment cases and chart cases
(gold derived from the generator + simulator), explainer facts, and the judge-calibration set (needs real
model outputs to rate).

## 3.4 Part D: real Ravelry patterns

Set: 14 patterns chosen with the author (doc 02 §2.5), PDFs + text in git-ignored `data/private/ravelry/`.
Text: `pypdf`; one design-tool PDF (Blueberry Bandana) gave one character per line → re-extracted with
`extraction_mode="layout"`; one image-only PDF (MONOKROM) was dropped earlier.

**Scope triage after reading every pattern:**

| Group | Patterns | Why |
|---|---|---|
| full gold (5) | Sherbet Bandana, Sister Scarf, Feeling Good, Sigrid Scarf, Nick Chopper (3 sizes) | one piece, in scope |
| partial gold (5) | Double Hat (outer hat), Stickjournalen (first repeat), Blueberry (triangle body), Moose Balaclava & 3x1 Hood (top rectangle) | later sections pick up stitches, use an applied i-cord, or a motif that shifts by design |
| probes, no gold (4) | Heidi (brioche-type stitches, flat → round), Warm and simple (thumb on hold), Garten (raglan), Picnic Folks Top | out of Must scope; used to show where the system stops |

**Gold annotation** (`data/private/ravelry/gold/build_gold.py`, private): written by hand from the text,
never from the parser (no label leakage). Reading decisions are recorded per pattern (e.g. "until the desired
length" → stated finished length; Sigrid gives no row gauge → 28 rows/10 cm assumed; section-restarting row
numbers made unique). **Check:** every gold IR simulates, and every stitch/row count the designers print
matches — row counts (Double Hat 104 → 16 → 8; Nick Chopper all 3 sizes), and counts stated in prose
(Blueberry "you now have 7 sts", Moose "23 (25) rows", Nick Chopper "64 (56, 64)" then "56").

**What real patterns needed that synthetic ones did not (loop 3 → 4):**
1. **Markers** — "knit to 3 sts before the next marker" (Double Hat, Nick Chopper, Sigrid). The IR got
   `until: {marker: true}`; the simulator tracks markers (pm/sm/rm, implicit passing, mirrored on flat rows,
   end of round = BOR marker) and records real repeat counts for display and charts.
2. Two simulator bugs found by the gold: an increase made right at a marker (k3, M1R, sm) must stay before
   it; a printed count describes the first time a row is worked, not its repeats.
3. Not representable (documented, not modelled): motifs that shift as a triangle shrinks, picked-up sections,
   applied i-cord edgings, brioche-type stitches, partial rows with turns.

**Author review:** `data/private/ravelry/gold/REVIEW.md` lists every row (readable form + counts) with a
checkbox; corrections go back into `build_gold.py`.

## 3.5 Reproduce

```bash
python -m knit_copilot.data.build_yarns   # uses cached Ravelry responses in .cache/ravelry/
python -m knit_copilot.data.generator     # data/eval/parse_cases.jsonl (seed 7, 63 cases)
python -m knit_copilot.data.build_eval_sets  # hand-written eval sets + 20% review sample
python data/private/ravelry/gold/build_gold.py  # private gold for the real patterns (needs the PDFs)
pytest -q
```

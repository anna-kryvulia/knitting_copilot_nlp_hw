# 3. Data Preparation

CRISP-DM phase 3. Turns the sources from Phase 2 into the data the components use. Done in four parts:

| Part | Content | Status |
|---|---|---|
| **A** | Pattern IR schema, unit conversion, knowledge bases, yarn table | ✅ done |
| B | Stitch simulator + synthetic pattern generator with gold labels | next |
| C | Hand-written eval sets (intents, setup dialogues, KB queries, yarn mentions, yarn advice) | |
| D | Annotations of 12 real Ravelry patterns | waits for the PDFs in `data/private/ravelry/` |

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
| Inconsistent label gauge (22 yarns, **Q9**) | Kept but `gauge_flag = outside_cyc_range` when the midpoint is > 3 sts/10 cm outside the CYC range (e.g. Nako Pirlanta: Sport weight, label gauge 17 sts) |
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

## 3.2 Reproduce

```bash
python -m knit_copilot.data.build_yarns   # uses cached Ravelry responses in .cache/ravelry/
pytest -q
```

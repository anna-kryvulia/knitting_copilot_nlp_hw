# 2. Data Understanding

CRISP-DM phase 2. What data exists for each component, how good it is, and what we must create
ourselves. Following the assignment, existing datasets were checked **before** deciding to generate
synthetic data.

Scripts (reproducible, responses cached in git-ignored `.cache/ravelry/`):
- `scripts/survey_ravelry_yarns.py` → `docs/data/yarn_survey.json`
- `scripts/find_ravelry_patterns.py` → `docs/data/ravelry_pattern_candidates.md`

## 2.1 Data needed per component

| Component | Data needed | Source found | Decision |
|---|---|---|---|
| Abbreviation KB (UC6), parser vocabulary, simulator, charts | Abbreviations with stitch arithmetic and chart symbols | Craft Yarn Council (CYC) knitting abbreviations list; Wikipedia "Knitting abbreviations" | Write our own YAML (~100 entries), own wording, cite CYC |
| Yarn linker + yarn advisor (UC3) | Yarns sold in Ukraine: weight, fibres, grams, length, needle size, gauge | **Ravelry API** (yarn database) + Ukrainian shop sites for brand selection | Build `data/yarns.csv` from Ravelry |
| Needle/gauge rules (UC3) | Yarn weight category → needle size and gauge range | **CYC Standard Yarn Weight System** | Encode as `data/kb/yarn_weights.yaml` |
| Fibre advice (UC3) | Properties of fibres (elasticity, warmth, care, blocking) | General references, no structured dataset | Write a small fibre KB (~15 fibres) |
| Parser, explainer, gauge, charts, tracker | Pattern text **with** structured labels (IR, stitch counts) | No suitable dataset (§2.4) | **Synthetic generator** with gold IR + **10–12 real free Ravelry patterns**, annotated by hand |
| Router, setup agent | User messages with intents; setup dialogues | None (task-specific) | Hand-written, reviewed eval sets |

## 2.2 Yarns: Ravelry API

Access: read-only Basic Auth (non-commercial developer account). The yarn records contain everything
UC3 needs:

| Field | Example (YarnArt Jeans, id 9876) | Note |
|---|---|---|
| `yarn_company_name`, `name` | YarnArt, "Jeans (Джинс)" | Some names carry a Cyrillic alias in brackets |
| `yarn_weight` | Sport | Ravelry's own weight names (mapped to CYC in §2.3) |
| `yarn_fibers` | Cotton 55%, Acrylic 45% | |
| `grams`, `yardage` | 50 g, 175 **yards** | Must convert to metres |
| `min_needle_size` | 3.5 mm | Metric value available |
| `min_gauge`, `max_gauge`, `gauge_divisor` | 24 sts over **4 inches** | Must convert to per 10 cm (×10/10.16) |
| `machine_washable`, `discontinued`, `texture` | | Used for advice and filtering |

### Brand survey (Ukrainian market)

Brands were chosen from Ukrainian online yarn shops (Candy-Yarn, Rucodel, Puffy, Wereteno, Klubok,
Prajlandia, Wooolama): Turkish brands dominate (Alize, YarnArt, Nako, Gazzal, Kartopu, Madame Tricote,
Himalaya); DROPS, Lana Grossa and Etrofil are sold by fewer shops. Brands from Russian producers are
excluded.

For each brand, the 30 most-used yarns on Ravelry were inspected (2026-11-06):

| Brand | Yarns on Ravelry | Inspected | Active (not discontinued) | Fibre % present | Needle size present | Gauge present |
|---|---|---|---|---|---|---|
| YarnArt | 276 | 30 | 30 | 100% | 97% | 93% |
| Alize | 199 | 30 | 29 | 97% | 100% | 90% |
| Himalaya | 165 | 30 | 18 | 100% | 100% | 94% |
| Nako | 211 | 30 | 29 | 100% | 100% | 93% |
| Gazzal | 68 | 30 | 28 | 100% | 96% | 93% |
| Kartopu | 138 | 30 | 23 | 100% | 96% | 91% |
| Madame Tricote | 82 | 30 | 29 | 100% | 93% | 83% |
| DROPS (company "Garnstudio") | 123 | 30 | 26 | 100% | 100% | 100% |
| Lana Grossa | 499 | 30 | 18 | 100% | 100% | 100% |
| Fibra Natura | 66 | 30 | 4 | 100% | 100% | 100% |
| Etrofil | 50 | 30 | 28 | 100% | 93% | 86% |

Also found: **Vizell** (sold by Ukrainian shops, 23 yarns on Ravelry) and the Ukrainian brand
**Yaroslav** (only 2 yarns on Ravelry). "Oren Bayan" is listed under Madame Tricote.

### Data quality findings

| # | Finding | Consequence for Phase 3 |
|---|---|---|
| Q1 | Discontinued yarns are common (Himalaya 12/30, Lana Grossa 12/30, Fibra Natura 26/30) | Keep only active yarns; **drop Fibra Natura** (4 active yarns, barely sold in Ukraine); add Vizell |
| Q2 | Gauge missing for 0–17% of active yarns, needle size for 0–7% | Fall back to the CYC range for the yarn's weight; mark the value as "from weight category" |
| Q3 | A few yarns have fibres without percentages (Alize 3%) | Keep fibre names; advice uses the main fibre only when percentages exist |
| Q4 | Imperial units (yards, per 4 inches) | Convert in `units.py`; unit-tested |
| Q5 | Shop brand ≠ Ravelry company (DROPS → Garnstudio, Oren Bayan → Madame Tricote) | Alias table for the yarn linker |
| Q6 | Names contain Cyrillic aliases ("Jeans (Джинс)") and stray spaces ("DROPS Karisma ") | Normalise names; keep aliases as extra linking keys |
| Q7 | Weight distribution: many Sport/DK/Fingering; some "Thread" weight (crochet threads) | Exclude Thread/Cobweb yarns (not for hand knitting in scope) |
| Q8 | Dominant fibres: acrylic and cotton (Turkish brands), wool/merino/alpaca (DROPS, Gazzal, Lana Grossa) | The fibre KB must cover acrylic, cotton, wool, merino, alpaca, mohair, polyamide/nylon, bamboo, viscose/rayon, linen, polyester, angora |

Expected size of `data/yarns.csv`: about 80–120 active yarns (top yarns per brand).

## 2.3 Yarn weight standard (CYC)

The CYC Standard Yarn Weight System gives knitting guidelines per category. The page labels them
"guidelines only" and notes that lace weight is usually knitted on larger needles for openwork, so
its range is less reliable.

| CYC category | Name | Typical yarns | Stitches per 10 cm (≈ per 4 in) | Needles (mm) | Ravelry weight names mapped here |
|---|---|---|---|---|---|
| 0 | Lace | Fingering, 10-count thread | 33–40 | 1.5–2.25 | Cobweb, Lace, Thread (excluded, Q7) |
| 1 | Super Fine | Sock, Fingering, Baby | 27–32 | 2.25–3.25 | Light Fingering, Fingering |
| 2 | Fine | Sport, Baby | 23–26 | 3.25–3.75 | Sport |
| 3 | Light | DK, Light Worsted | 21–24 | 3.75–4.5 | DK |
| 4 | Medium | Worsted, Aran | 16–20 | 4.5–5.5 | Worsted, Aran |
| 5 | Bulky | Chunky | 12–15 | 5.5–8 | Bulky |
| 6 | Super Bulky | Roving | 7–11 | 8–12.75 | Super Bulky |
| 7 | Jumbo | Jumbo, Roving | ≤ 6 | ≥ 12.75 | Jumbo |

Rule for UC3: use the **yarn's own label values** from Ravelry when present; otherwise use the CYC
range for its category. Both are shown with their source.

## 2.4 Existing pattern datasets

| Dataset | What it is | Usable? |
|---|---|---|
| HF `arkrajkundu/knitting_patterns` | 7,589 images (PNG), labels empty, no licence | No: images, no text, no labels, no licence |
| HF `arkrajkundu/knitgpt` | Empty repository | No |
| HF `Fsoft-AIC/knitcad`, `cadknitter/KnitCAD` | Machine-knitting CAD data | No: industrial machine knitting, not written hand-knitting patterns |
| HF `peiyugeorgia/CrochetBench` | Crochet benchmark | No: crochet is out of scope |
| Kaggle "Textile Knitting Dataset" | 12.5k rows of factory production data (loop length, GSM, machine gauge) | No: manufacturing parameters, not text |
| Ravelry pattern database | Metadata for >25,000 free knitting patterns (gauge, needles, sizes, attributes); the pattern text itself is a PDF owned by the designer | Metadata only; PDFs can be used privately for evaluation |

**Conclusion:** there is no dataset of written hand-knitting patterns with structured labels. This
justifies (1) a **synthetic pattern generator** that produces text together with gold IR and exact
stitch counts, and (2) a small set of **real Ravelry patterns annotated by hand** to measure the gap
between synthetic and real text.

## 2.5 Real patterns: Ravelry candidates

Search filters: knitting, free, downloadable from Ravelry, English, written instructions; colourwork,
short rows, brioche, entrelac and similar techniques excluded; sorted by number of projects. The full
list (24 candidates, 3 per slot) is in `docs/data/ravelry_pattern_candidates.md`.

Recommended 12 (covers every Must slot, flat and in the round, US terms, several multi-size patterns,
lace, cables, textures, increases/decreases):

| # | Pattern | Why |
|---|---|---|
| 1 | Drop Stitch Scarf | Easy, flat, dropped stitches |
| 2 | Irish Hiking Scarf | Flat cables |
| 3 | Saroyan | Flat lace with chart + written version, customisation notes |
| 4 | Feather and Fan Short Scarf | Classic 4-row lace repeat |
| 5 | Barley (worsted) | Hat in the round, multi-size, garter texture, crown decreases |
| 6 | wurm | Hat in the round, metric sizes, textured bands |
| 7 | Sockhead Slouch Hat | Hat in the round, 7 sizes, ribbing |
| 8 | Antler Toque | Cables in the round, multi-size |
| 9 | Honey Cowl | Cowl in the round, slipped-stitch texture |
| 10 | GAP-tastic Cowl | Very simple seed stitch in the round (control case) |
| 11 | Gramma's Dishcloth | Knit on the bias: increases then decreases, counts change every row |
| 12 | Malt | Flat blanket, multi-size, ribbed texture |
| (Should) | French Macaroon | Baby sweater in seamed pieces, for multi-piece/pick-up work |

Observations:
- Most patterns state sizes and dimensions in **inches** (some give both), so unit normalisation is needed
  on real text.
- Ravelry's US/UK terminology flags are empty for most patterns, so the parser has to detect terminology
  itself.
- Several patterns rely on **charts** with a written version; only the written instructions are parsed.
- The PDFs are copyrighted: they are downloaded manually into git-ignored `data/private/ravelry/`; only
  our annotations and links are committed (`annotate-ravelry-pattern` skill).

## 2.6 Knowledge base sources

| KB | Content | Source / reference |
|---|---|---|
| `abbreviations.yaml` | ~100 knitting abbreviations: aliases, US/UK term, consumes/produces, lean, chart symbol | CYC knitting abbreviations list (reference), descriptions in our own words. CYC notes that designers also define pattern-specific abbreviations, so the pattern's own glossary is parsed too |
| `yarn_weights.yaml` | CYC categories, ranges, Ravelry name mapping | CYC Standard Yarn Weight System |
| `fibres.yaml` | ~15 fibres: elasticity, warmth, drape, care, needle advice | Written by us from general references |
| `techniques.yaml` (Should) | Fixing mistakes: tinking, laddering down, lifelines, dropped stitches | Written by us |

## 2.7 Risks found in this phase

| Risk | Mitigation |
|---|---|
| Real patterns use prose notes ("work as for back until…", "continue in pattern") that synthetic text lacks | Add such phrasing to the generator styles; report the synthetic/real gap |
| Ravelry API returns 500 for unknown filter values (`pa=flat`, `pc=dishcloth`) | Script uses verified values (`worked-flat`, `washcloth`) |
| Lace-weight CYC ranges are unreliable | Lace yarns get advice from their own label values, not CYC |

## 2.8 Sources

- Ravelry API: https://www.ravelry.com/api
- Craft Yarn Council, Standard Yarn Weight System: https://www.craftyarncouncil.com/standards/yarn-weight-system
- Craft Yarn Council, Knitting abbreviations: https://www.craftyarncouncil.com/standards/knitting-abbreviations
- Hugging Face dataset search ("knitting", "knit", "crochet"), 2026-11-06
- Kaggle Textile Knitting Dataset: https://www.kaggle.com/datasets/toufique33/textile-knitting-dataset
- Ukrainian yarn shops: candy-yarn.com.ua, rucodel.com.ua, puffy.com.ua, wereteno.com.ua, klubok-yarn.com.ua,
  prajlandia.com, wooolama.com

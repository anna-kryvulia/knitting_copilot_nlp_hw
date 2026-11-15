"""CRISP-DM phase 2: find candidate free Ravelry patterns for the real-pattern evaluation set.

Searches free, downloadable-from-Ravelry knitting patterns with written instructions, by category,
drops out-of-scope techniques, and writes a candidate table to docs/data/ravelry_pattern_candidates.md.
Only metadata is stored; the user downloads the chosen PDFs manually into data/private/ravelry/.

Run: python scripts/find_ravelry_patterns.py            # classic set: most projects of all time
     python scripts/find_ravelry_patterns.py --modern   # recently popular, published 2019 or later
"""

import argparse

from knit_copilot.config import ROOT
from knit_copilot.data import ravelry

# (label, tier, search filters)
SLOTS = [
    ("Garter / rib scarf (flat, easy)", "Must", {"pc": "scarf", "pa": "written-pattern+worked-flat"}),
    ("Ribbed hat (in the round)", "Must", {"pc": "hat", "pa": "written-pattern+in-the-round"}),
    ("Lace scarf or shawl (flat)", "Must", {"pc": "scarf", "pa": "written-pattern+lace"}),
    ("Cabled hat or scarf", "Must", {"pc": "hat", "pa": "written-pattern+cables"}),
    ("Cowl (in the round)", "Must", {"pc": "cowl", "pa": "written-pattern+in-the-round"}),
    ("Textured dishcloth (flat)", "Must", {"pc": "washcloth", "pa": "written-pattern+worked-flat"}),
    ("Baby blanket (flat, texture)", "Must", {"pc": "babyblanket", "pa": "written-pattern+worked-flat"}),
    ("Simple sweater in pieces (for the Should tier)", "Should", {"pc": "pullover", "pa": "written-pattern+seamed"}),
]
# Modern set: what knitters make now (Ravelry "recently popular" = recent project activity), published ≥ 2019
MODERN_SLOTS = [
    ("Beanie (in the round)", "Must", {"pc": "beanie-toque", "pa": "written-pattern+in-the-round"}),
    ("Balaclava", "Must", {"pc": "balaclava", "pa": "written-pattern"}),
    ("Kerchief / bandana (flat, shaping)", "Must", {"pc": "kerchief", "pa": "written-pattern"}),
    ("Scarf (chunky / mohair / textured)", "Must", {"pc": "scarf", "pa": "written-pattern"}),
    ("Cowl / neck warmer (in the round)", "Must", {"pc": "cowl", "pa": "written-pattern+in-the-round"}),
    ("Headband / ear warmer", "Must", {"pc": "headband", "pa": "written-pattern"}),
    ("Leg warmers (in the round)", "Must", {"pc": "legwarmers", "pa": "written-pattern"}),
    ("Tote / market bag", "Must", {"pc": "tote", "pa": "written-pattern"}),
    ("Cables (hat or scarf)", "Must", {"pc": "hat", "pa": "written-pattern+cables"}),
    ("Lace (scarf or shawl)", "Must", {"pc": "shawl-wrap", "pa": "written-pattern+lace"}),
    ("Vest / top (for the Should tier)", "Should", {"pc": "vest", "pa": "written-pattern"}),
]
# "More like the chosen ones": the user picked recent (2023+) accessories by small designers — balaclava,
# bandanas, lace headscarf, scarf, leg warmers, double hat — and skipped classic beanies, cowl, shrug, tote
MORE_SLOTS = [
    ("Balaclava", "Must", {"pc": "balaclava", "pa": "written-pattern"}),
    ("Kerchief / bandana", "Must", {"pc": "kerchief", "pa": "written-pattern"}),
    ("Leg warmers", "Must", {"pc": "legwarmers", "pa": "written-pattern"}),
    ("Scarf", "Must", {"pc": "scarf", "pa": "written-pattern"}),
    ("Hat / beanie", "Must", {"pc": "beanie-toque", "pa": "written-pattern"}),
    ("Earflap hat", "Must", {"pc": "earflap", "pa": "written-pattern"}),
    ("Collar / neck piece", "Must", {"pc": "collar", "pa": "written-pattern"}),
    ("Other headwear (hoods, headscarves)", "Must", {"pc": "other-headwear", "pa": "written-pattern"}),
    ("Fingerless mitts", "Must", {"pc": "fingerless", "pa": "written-pattern"}),
    ("Shawl / triangle wrap", "Must", {"pc": "shawl-wrap", "pa": "written-pattern"}),
]
# Garments and mittens (user request): raglans and one-piece tops are Should tier (sleeve stitches on hold),
# mittens are borderline (thumb gusset on hold); scarves are Must
GARMENT_SLOTS = [
    ("Raglan sweater (top-down, seamless)", "Should", {"pc": "pullover", "query": "raglan", "pa": "written-pattern+top-down"}),
    ("One-piece top / tee", "Should", {"pc": "tee", "pa": "written-pattern+seamless"}),
    ("Sleeveless top", "Should", {"pc": "sleeveless-top", "pa": "written-pattern"}),
    ("Scarf", "Must", {"pc": "scarf", "pa": "written-pattern+worked-flat"}),
    ("Mittens", "borderline", {"pc": "mittens", "pa": "written-pattern"}),
]
MIN_YEAR = 2019
MIN_PROJECTS = 30          # trending-but-unknitted patterns (0 projects) are untested; skip them
OUT_OF_SCOPE = {"colorwork", "stranded", "intarsia", "fair-isle", "short-rows", "mosaic", "duplicate-stitch",
                "brioche", "double-knit", "entrelac"}
PER_SLOT = 3


def year(p: dict) -> int | None:
    date = p.get("published") or p.get("created_at") or ""
    return int(date[:4]) if date[:4].isdigit() else None


def candidates(filters: dict, modern: bool = False, min_year: int | None = None, min_projects: int | None = None,
               per_slot: int = PER_SLOT, exclude: set[str] = frozenset()) -> list[dict]:
    hits = ravelry.search_patterns(page_size=100 if modern else 25, craft="knitting", availability="free+ravelry",
                                   language="en", sort="recently-popular" if modern else "popularity",
                                   **filters)["patterns"]
    full = {}
    for i in range(0, len(hits), 50):
        full |= ravelry.patterns_by_ids([p["id"] for p in hits[i:i + 50]])["patterns"]
    order = [str(p["id"]) for p in hits] if modern else None          # keep Ravelry's recent-popularity order
    ranked = [full[i] for i in order if i in full] if modern else \
        sorted(full.values(), key=lambda p: -(p.get("projects_count") or 0))
    chosen = []
    for p in ranked:
        attrs = {a["permalink"] for a in p.get("pattern_attributes", [])}
        if attrs & OUT_OF_SCOPE or not p.get("free") or not p.get("ravelry_download"):
            continue
        if modern and ((year(p) or 0) < (min_year or MIN_YEAR)
                       or (p.get("projects_count") or 0) < (min_projects or MIN_PROJECTS)):
            continue
        if p["permalink"] in exclude:
            continue
        chosen.append(p)
        exclude = exclude | {p["permalink"]}
        if len(chosen) == per_slot:
            break
    return chosen


def row(p: dict) -> str:
    needles = ", ".join(str(n["metric"]) for n in p.get("pattern_needle_sizes", []) if n.get("knitting"))
    attrs = ", ".join(sorted(a["permalink"] for a in p.get("pattern_attributes", [])
                             if a["permalink"] in {"worked-flat", "in-the-round", "lace", "cables", "chart", "seamed",
                                                   "seamless", "textured", "ribbed", "garter"}))
    # Ravelry leaves these flags empty for most patterns, so "?" is common
    terms = "/".join(t for t, k in (("US", "has_us_terminology"), ("UK", "has_uk_terminology")) if p.get(k)) or "?"
    return (f"| [{p['name']}](https://www.ravelry.com/patterns/library/{p['permalink']}) "
            f"| {p['pattern_author']['name']} | {p.get('yarn_weight_description') or '?'} | {needles or '?'} "
            f"| {p.get('sizes_available') or '—'} | {attrs} | {terms} | {p.get('projects_count', 0):,} "
            f"| {p.get('difficulty_average') or 0:.1f} | {year(p) or '?'} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modern", action="store_true")
    ap.add_argument("--more", action="store_true", help="more like the user's picks: 2023+, ≥ 20 projects, 5 per slot")
    ap.add_argument("--garments", action="store_true", help="raglans, one-piece tops, scarves, mittens (2022+)")
    args = ap.parse_args()
    if args.more:
        return more()
    if args.garments:
        return more(GARMENT_SLOTS, "ravelry_pattern_candidates_garments.md", min_year=2022, min_projects=30,
                    title="Modern raglans, one-piece tops, scarves and mittens")
    how = (f"Sorted by Ravelry's **recently popular** (recent activity), published {MIN_YEAR} or later, at least "
           f"{MIN_PROJECTS} projects."
           if args.modern else "Sorted by number of projects (all time).")
    lines = ["# Candidate free Ravelry patterns for the evaluation set" + (" — modern" if args.modern else ""), "",
             "Generated by `scripts/find_ravelry_patterns.py" + (" --modern" if args.modern else "") + "`. Filters: "
             "knitting, free, downloadable from Ravelry, English, written instructions; colourwork, short rows, "
             f"brioche etc. excluded. {how} **Pick 10–12** (at least one per Must slot) and download them into "
             "`data/private/ravelry/`.", "", "Difficulty is Ravelry's user average on a 1–10 scale.", ""]
    for label, tier, filters in (MODERN_SLOTS if args.modern else SLOTS):
        lines += [f"## {label} — {tier}", "",
                  "| Pattern | Designer | Yarn weight | Needles (mm) | Sizes | Attributes | Terms | Projects | Difficulty | Year |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        found = candidates(filters, modern=args.modern)
        lines += [row(p) for p in found] or ["| (no match) ||||||||||"]
        lines.append("")
        print(f"{label:48} {len(found)} candidates")
    out = ROOT / "docs" / "data" / ("ravelry_pattern_candidates_modern.md" if args.modern
                                     else "ravelry_pattern_candidates.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out.relative_to(ROOT)}")


def more(slots=None, filename: str = "ravelry_pattern_candidates_more.md", min_year: int = 2023,
         min_projects: int = 20, title: str = "More modern candidates (like the user's picks)") -> None:
    import re
    slots = slots or MORE_SLOTS
    shown = set()
    for f in ("ravelry_pattern_candidates_modern.md", "ravelry_pattern_candidates_more.md"):
        path = ROOT / "docs" / "data" / f
        if path.exists() and f != filename:
            shown |= set(re.findall(r"patterns/library/([^)]+)\)", path.read_text(encoding="utf-8")))
    lines = [f"# {title}", "",
             f"Generated by `scripts/find_ravelry_patterns.py`: recently popular, published {min_year} or later, "
             f"≥ {min_projects} projects, free + Ravelry download, written instructions, colourwork/short rows "
             "excluded, patterns already listed in the other candidate files skipped.", ""]
    seen = set(shown)
    for label, tier, filters in slots:
        found = candidates(filters, modern=True, min_year=min_year, min_projects=min_projects, per_slot=5, exclude=seen)
        seen |= {p["permalink"] for p in found}
        lines += [f"## {label} — {tier}", "",
                  "| Pattern | Designer | Yarn weight | Needles (mm) | Sizes | Attributes | Terms | Projects | Difficulty | Year |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        lines += [row(p) for p in found] or ["| (no match) ||||||||||"]
        lines.append("")
        print(f"{label:40} {len(found)}")
    out = ROOT / "docs" / "data" / filename
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

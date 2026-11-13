"""Build data/yarns.csv: active yarns of brands sold on the Ukrainian market, from the Ravelry API.

Purpose: the yarn table behind UC3 (yarn linker + advisor). Metric units only.
Input: Ravelry API (cached in .cache/ravelry/). Output: data/yarns.csv, one row per yarn.
Rules (docs/02_data_understanding.md §2.2): active yarns only; Thread/Cobweb weights excluded; missing
needle size or gauge filled from the CYC range of the yarn's weight, with the value source recorded.

Run: python -m knit_copilot.data.build_yarns
"""

import csv
import re

from knit_copilot import kb, units
from knit_copilot.config import ROOT
from knit_copilot.data import ravelry

# shop brand -> company name on Ravelry
BRANDS = {"YarnArt": "YarnArt", "Alize": "Alize", "Himalaya": "Himalaya", "Nako": "Nako", "Gazzal": "Gazzal",
          "Kartopu": "Kartopu", "Madame Tricote": "Madame Tricote", "DROPS": "Garnstudio",
          "Lana Grossa": "Lana Grossa", "Etrofil": "Etrofil", "Vizell": "Vizell"}
PER_BRAND = 20
SEARCH_DEPTH = 40  # most-used yarns inspected per brand before filtering
EXCLUDED_WEIGHTS = {"Thread", "Cobweb"}
GAUGE_TOLERANCE = 3  # sts per 10 cm outside the CYC range before a label gauge is flagged
CYRILLIC_ALIAS = re.compile(r"\s*\(([^)]*[А-Яа-яЇїІіЄєҐґ][^)]*)\)")
OUT = ROOT / "data" / "yarns.csv"

COLUMNS = ["yarn_id", "brand", "name", "aliases", "weight", "cyc_category", "grams", "length_m",
           "fibres", "main_fibre", "needle_min_mm", "needle_max_mm", "needle_source",
           "gauge_min_sts_10cm", "gauge_max_sts_10cm", "gauge_source", "gauge_flag", "machine_washable",
           "ravelry_rating_count", "ravelry_url", "source"]


def _fibre_key(ravelry_name: str) -> str | None:
    """Map a Ravelry fibre name to a key of data/kb/fibres.yaml."""
    name = ravelry_name.lower()
    for key, f in kb.fibres().items():
        if name in [a.lower() for a in f["aliases"]] or name == key:
            return key
    return None


def _cyc_category(weight_name: str) -> dict | None:
    for c in kb.yarn_weights()["categories"]:
        if weight_name in c["ravelry_names"]:
            return c
    return None


def _row(brand: str, y: dict) -> dict | None:
    weight = (y.get("yarn_weight") or {}).get("name")
    cyc = _cyc_category(weight) if weight else None
    if y.get("discontinued") or weight in EXCLUDED_WEIGHTS or cyc is None:
        return None

    raw_name = (y.get("name") or "").strip()
    aliases = CYRILLIC_ALIAS.findall(raw_name)
    name = re.sub(r"\s+", " ", CYRILLIC_ALIAS.sub("", raw_name)).strip()

    fibres = sorted(y.get("yarn_fibers") or [], key=lambda f: -(f.get("percentage") or 0))
    fibre_text = "; ".join(f"{f['fiber_type']['name']} {f['percentage']}%" if f.get("percentage")
                           else f["fiber_type"]["name"] for f in fibres)
    main_fibre = _fibre_key(fibres[0]["fiber_type"]["name"]) if fibres else None

    if y.get("min_needle_size"):
        lo = y["min_needle_size"]["metric"]
        hi = (y.get("max_needle_size") or {}).get("metric") or lo
        needle = (lo, hi, "label")
    else:
        needle = (*cyc["needle_mm"], "cyc")

    divisor = y.get("gauge_divisor") or 4
    if y.get("min_gauge"):
        g_lo = units.gauge_to_per_10cm(y["min_gauge"], divisor)
        g_hi = units.gauge_to_per_10cm(y["max_gauge"], divisor) if y.get("max_gauge") else g_lo
        gauge = (min(g_lo, g_hi), max(g_lo, g_hi), "label")
    else:
        gauge = (*cyc["sts_per_10cm"], "cyc")

    # Ravelry label gauges are sometimes inconsistent with the weight (data quality Q9): keep, but flag
    mid = (gauge[0] + gauge[1]) / 2
    lo, hi = cyc["sts_per_10cm"]
    flag = "outside_cyc_range" if gauge[2] == "label" and not lo - GAUGE_TOLERANCE <= mid <= hi + GAUGE_TOLERANCE else ""

    return {
        "yarn_id": y["id"], "brand": brand, "name": name, "aliases": "|".join(aliases),
        "weight": weight, "cyc_category": cyc["id"], "grams": y.get("grams"),
        "length_m": units.yards_to_m(y["yardage"]) if y.get("yardage") else None,
        "fibres": fibre_text, "main_fibre": main_fibre,
        "needle_min_mm": needle[0], "needle_max_mm": needle[1], "needle_source": needle[2],
        "gauge_min_sts_10cm": gauge[0], "gauge_max_sts_10cm": gauge[1], "gauge_source": gauge[2],
        "gauge_flag": flag,
        "machine_washable": y.get("machine_washable"), "ravelry_rating_count": y.get("rating_count"),
        "ravelry_url": f"https://www.ravelry.com/yarns/library/{y['permalink']}", "source": "ravelry_api",
    }


def build() -> list[dict]:
    rows = []
    for brand, company in BRANDS.items():
        hits = ravelry.search_yarns(brand, page_size=100, page=1, sort="projects")["yarns"]
        hits = [h for h in hits if company.lower() in (h.get("yarn_company_name") or "").lower()][:SEARCH_DEPTH]
        details = {}
        for i in range(0, len(hits), 50):
            details |= ravelry.yarns_by_ids([h["id"] for h in hits[i:i + 50]])["yarns"]
        kept = []
        for h in hits:  # keep popularity order
            r = _row(brand, details[str(h["id"])])
            if r:
                kept.append(r)
        rows += kept[:PER_BRAND]
        print(f"{brand:15} inspected={len(hits):3} kept={len(kept[:PER_BRAND]):3}")
    return rows


def main() -> None:
    rows = build()
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} yarns -> {OUT.relative_to(ROOT)}")
    for col in ("needle_source", "gauge_source"):
        print(col, {v: sum(r[col] == v for r in rows) for v in ("label", "cyc")})
    print("gauge flagged outside CYC range:", sum(bool(r["gauge_flag"]) for r in rows))
    print("main_fibre unmapped:", sorted({r["fibres"] for r in rows if not r["main_fibre"]})[:10])


if __name__ == "__main__":
    main()

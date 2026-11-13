"""CRISP-DM phase 2: survey Ravelry yarn data for brands sold on the Ukrainian market.

For each brand: how many yarns Ravelry lists, how many are discontinued, and how complete the fields we
need are (weight, fibres, needle size, gauge, grams, yardage). Writes docs/data/yarn_survey.json.

Run: python scripts/survey_ravelry_yarns.py
"""

import json
from collections import Counter

from knit_copilot.config import ROOT
from knit_copilot.data import ravelry

BRANDS = ["YarnArt", "Alize", "Himalaya", "Nako", "Gazzal", "Kartopu", "Madame Tricote", "DROPS",
          "Lana Grossa", "Fibra Natura", "Etrofil"]
# Brand name used in shops -> company name on Ravelry, where they differ
RAVELRY_COMPANY = {"DROPS": "Garnstudio"}
TOP_N = 30  # most popular yarns per brand that we inspect in detail


def brand_yarns(brand: str) -> list[dict]:
    """All search hits whose company name contains the brand, most-used first."""
    hits, page = [], 1
    while True:
        data = ravelry.search_yarns(brand, page_size=100, page=page, sort="projects")
        company = RAVELRY_COMPANY.get(brand, brand).lower()
        hits += [y for y in data["yarns"] if company in (y.get("yarn_company_name") or "").lower()]
        pag = data["paginator"]
        if page >= pag["page_count"] or page >= 5:
            return hits
        page += 1


def details(ids: list[int]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        out += list(ravelry.yarns_by_ids(ids[i:i + 50])["yarns"].values())
    return out


def completeness(yarns: list[dict]) -> dict[str, float]:
    checks = {
        "weight": lambda y: bool(y.get("yarn_weight")),
        "fibres": lambda y: bool(y.get("yarn_fibers")),
        "fibre_percentages": lambda y: bool(y.get("yarn_fibers")) and all(f["percentage"] for f in y["yarn_fibers"]),
        "needle_size": lambda y: bool(y.get("min_needle_size")),
        "gauge": lambda y: bool(y.get("min_gauge")),
        "grams": lambda y: bool(y.get("grams")),
        "yardage": lambda y: bool(y.get("yardage")),
    }
    n = len(yarns) or 1
    return {k: round(sum(f(y) for y in yarns) / n, 2) for k, f in checks.items()}


def main() -> None:
    survey = {}
    for brand in BRANDS:
        all_hits = brand_yarns(brand)
        top = details([y["id"] for y in all_hits[:TOP_N]])
        active = [y for y in top if not y.get("discontinued")]
        survey[brand] = {
            "listed_on_ravelry": len(all_hits),
            "inspected": len(top),
            "discontinued_in_inspected": len(top) - len(active),
            "field_completeness_active": completeness(active),
            "weights": dict(Counter((y.get("yarn_weight") or {}).get("name", "unknown") for y in active)),
            "main_fibres": dict(Counter(max(y["yarn_fibers"], key=lambda f: f["percentage"] or 0)["fiber_type"]["name"]
                                        for y in active if y.get("yarn_fibers")).most_common(5)),
            "examples": [y["name"] for y in active[:5]],
        }
        print(f"{brand:15} listed={len(all_hits):4}  inspected={len(top):3}  active={len(active):3}  "
              f"completeness={survey[brand]['field_completeness_active']}")

    out = ROOT / "docs" / "data" / "yarn_survey.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(survey, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Yarn linker (UC3): free-text yarn mention → one row of data/yarns.csv, "ambiguous", or "no match".

Purpose: entity linking for yarn names as users type them: typos ("gazal baby wool"), missing brand
("Cool Wool"), partial names ("Alize Cotton Gold"), colour numbers ("YarnArt Jeans 33"), the Cyrillic alias
Ravelry lists ("Джинс"), shop vs Ravelry brand names (DROPS = Garnstudio).
Input: LinkerInput(text). Output: LinkerOutput(yarn_id | None, candidates, status, score).
Model calls: none (string matching). Tool calls: none.

Method:
1. normalise (case, accents, hyphens, punctuation; parenthetical descriptors dropped from yarn names);
2. detect the brand with fuzzy matching on brand names and aliases → restrict candidates;
3. score each candidate name: exact > all mention words contained in the name (fewest extra words wins,
   plain variants such as "Solids"/"Classic" preferred) > fuzzy ratio; colour numbers are tried both
   with and without;
4. decide: no match below THRESHOLD; "ambiguous" when the best candidates are equally good but different
   yarns (same name in two brands and no brand given).
"""

from __future__ import annotations

import csv
import difflib
import re
import unicodedata
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from knit_copilot.config import ROOT

THRESHOLD = 0.78
BRAND_THRESHOLD = 0.8
BASE_VARIANT_WORDS = {"solids", "solid", "classic", "uni", "unicolor", "plain"}
BRAND_ALIASES = {"DROPS": ["drops", "garnstudio", "garn studio"], "YarnArt": ["yarnart", "yarn art"],
                 "Madame Tricote": ["madame tricote", "madame tricote paris", "oren bayan"],
                 "Lana Grossa": ["lana grossa"], "Himalaya": ["himalaya"], "Alize": ["alize", "alizé"],
                 "Nako": ["nako"], "Gazzal": ["gazzal"], "Kartopu": ["kartopu"], "Etrofil": ["etrofil"],
                 "Vizell": ["vizell"]}
FILLER = {"yarn", "by", "from", "the", "my", "i", "am", "using", "use", "some", "a", "of", "in", "with"}


class LinkerInput(BaseModel):
    text: str


class Candidate(BaseModel):
    yarn_id: int
    brand: str
    name: str
    score: float


class LinkerOutput(BaseModel):
    status: Literal["match", "ambiguous", "none"]
    yarn_id: int | None = None
    candidates: list[Candidate] = []
    brand: str | None = None


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode() if text.isascii() is False \
        and not re.search(r"[А-Яа-яЇїІіЄєҐґ]", text) else text
    text = text.lower().replace("’", "'").replace("-", " ").replace("&", " and ")
    text = re.sub(r"[^\w\s/']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache
def display_name(brand: str, name: str) -> str:
    """'DROPS' + 'DROPS Karisma' → 'DROPS Karisma'; 'YarnArt' + 'Jeans' → 'YarnArt Jeans'."""
    return name if name.lower().startswith(brand.lower()) else f"{brand} {name}"


def yarns() -> list[dict]:
    rows = list(csv.DictReader(open(ROOT / "data" / "yarns.csv", encoding="utf-8")))
    for r in rows:
        name = re.sub(r"\(.*?\)", " ", r["name"])                        # drop "(Acrylic Blend)" etc.
        name = re.sub(rf"^{re.escape(r['brand'])}\s+", "", name, flags=re.I)   # "DROPS Karisma" → "Karisma"
        keys = {norm(name)}
        keys |= {norm(a) for a in r["aliases"].split("|") if a}
        r["_keys"] = sorted(k for k in keys if k)
    return rows


def _detect_brand(words: list[str]) -> tuple[str | None, list[str]]:
    """Find a brand in the first/last words (1–3 word spans, fuzzy); return brand and the remaining words."""
    best = (0.0, None, (0, 0))
    for size in (3, 2, 1):
        for start in range(0, len(words) - size + 1):
            span = " ".join(words[start:start + size])
            for brand, aliases in BRAND_ALIASES.items():
                for a in aliases:
                    r = difflib.SequenceMatcher(None, span, a).ratio()
                    if r > best[0]:
                        best = (r, brand, (start, start + size))
    if best[0] >= BRAND_THRESHOLD:
        s, e = best[2]
        rest = words[:s] + words[e:]
        # the brand may be named twice ("Garnstudio DROPS Air"): drop other aliases of the same brand
        alias_words = {w for a in BRAND_ALIASES[best[1]] for w in a.split()}
        return best[1], [w for w in rest if w not in alias_words]
    return None, words


def _score(mention: str, key: str) -> float:
    if not mention:
        return 0.0
    if mention == key:
        return 1.0
    m, k = mention.split(), key.split()
    if set(m) <= set(k):                                   # all typed words are in the name
        extra = [w for w in k if w not in m]
        bonus = 0.04 if extra and all(w in BASE_VARIANT_WORDS for w in extra) else 0.0
        return min(0.97, 0.95 - 0.03 * len(extra) + bonus)
    return difflib.SequenceMatcher(None, mention, key).ratio() * 0.95


def run(inp: LinkerInput) -> LinkerOutput:
    brand, rest = _detect_brand(norm(inp.text).split())       # brand first: "Yarn Art" contains "yarn"
    rest = [w for w in rest if w not in FILLER]
    variants = [" ".join(rest)]
    if rest and rest[-1].isdigit():                       # colour number: "jeans 33"
        variants.append(" ".join(rest[:-1]))
    pool = [y for y in yarns() if brand is None or y["brand"] == brand]
    scored = []
    for y in pool:
        s = max(_score(v, k) for v in variants for k in y["_keys"])
        scored.append(Candidate(yarn_id=int(y["yarn_id"]), brand=y["brand"], name=y["name"], score=round(s, 3)))
    scored.sort(key=lambda c: -c.score)
    top = [c for c in scored if c.score >= THRESHOLD]
    if not top:
        return LinkerOutput(status="none", candidates=scored[:3], brand=brand)
    best = top[0].score
    tied = [c for c in top if best - c.score < 0.01]
    if len(tied) > 1 and len({c.brand for c in tied}) > 1:
        return LinkerOutput(status="ambiguous", candidates=tied, brand=brand)
    return LinkerOutput(status="match", yarn_id=top[0].yarn_id, candidates=top[:3], brand=brand)

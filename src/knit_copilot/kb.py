"""Knowledge-base loader: abbreviations, yarn weights and fibres from data/kb/*.yaml.

Purpose: single source of truth for stitch arithmetic, chart symbols, definitions (UC6) and yarn rules.
Input: YAML files. Output: validated Pydantic objects and an alias index for exact lookup.
"""

import re
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel

from knit_copilot.config import ROOT

KB_DIR = ROOT / "data" / "kb"


class Abbreviation(BaseModel):
    id: str
    name: str
    aliases: list[str]
    uk_term: str | None = None
    consumes: int | None
    produces: int | None
    category: Literal["basic", "slip", "increase", "decrease", "cable", "other", "marker", "term"]
    lean: Literal["left", "right", "centre"] | None = None
    chart_symbol: str | None = None
    chart_symbol_ws: str | None = None
    description: str
    reference: str

    @property
    def is_stitch_op(self) -> bool:
        return self.consumes is not None


def normalise(text: str) -> str:
    """Lower-case, unify spacing and punctuation so 'K2 Tog', 'k2tog.' and 'k2-tog' compare equal."""
    text = text.lower().replace("&", "").replace("-", " ").strip(" .,;:")
    text = re.sub(r"\s+", " ", text)
    return text


def _compact(text: str) -> str:
    return normalise(text).replace(" ", "")


@lru_cache
def abbreviations() -> dict[str, Abbreviation]:
    raw = yaml.safe_load((KB_DIR / "abbreviations.yaml").read_text(encoding="utf-8"))
    items = [Abbreviation.model_validate(r) for r in raw]
    ids = [a.id for a in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate abbreviation ids: {sorted(i for i in ids if ids.count(i) > 1)}")
    return {a.id: a for a in items}


@lru_cache
def alias_index() -> dict[str, str]:
    """normalised alias (and its space-free form) -> abbreviation id. Raises on ambiguous aliases."""
    index: dict[str, str] = {}
    for a in abbreviations().values():
        for alias in {a.id, *a.aliases}:
            for key in {normalise(alias), _compact(alias)}:
                if index.get(key, a.id) != a.id:
                    raise ValueError(f"Alias {alias!r} maps to both {index[key]!r} and {a.id!r}")
                index[key] = a.id
    return index


def lookup(text: str) -> Abbreviation | None:
    """Exact lookup by id or alias, tolerant to case, spacing and punctuation. None if unknown."""
    idx = alias_index()
    key = idx.get(normalise(text)) or idx.get(_compact(text))
    return abbreviations()[key] if key else None


def stitch_op(op: str) -> Abbreviation:
    """The abbreviation for an IR op; raises KeyError for unknown ops or vocabulary terms."""
    a = lookup(op)
    if a is None or not a.is_stitch_op:
        raise KeyError(f"Unknown stitch operation: {op!r}")
    return a


@lru_cache
def yarn_weights() -> dict:
    return yaml.safe_load((KB_DIR / "yarn_weights.yaml").read_text(encoding="utf-8"))


@lru_cache
def fibres() -> dict:
    return yaml.safe_load((KB_DIR / "fibres.yaml").read_text(encoding="utf-8"))

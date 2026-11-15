"""Pattern IR: the structured representation every pattern feature works on.

Purpose: one schema shared by the parser (output), simulator, gauge adjuster, charts, tracker and explainer.
Schema description and examples: docs/CONVENTIONS.md § Pattern IR. All measurements are metric.

Multi-size values ("CO 40 (46, 52)") are stored as {"S": 40, "M": 46, "L": 52}; `resolve()` picks one size.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

SizedInt = Union[int, dict[str, int]]


def resolve(value: SizedInt | None, size: str | None) -> int | None:
    """Return the value for `size` from a plain int or a {size: int} mapping."""
    if value is None or isinstance(value, int):
        return value
    if size is None:
        if len(value) == 1:
            return next(iter(value.values()))
        raise ValueError(f"Size required, value is per size: {value}")
    if size not in value:
        raise KeyError(f"Size {size!r} not in {sorted(value)}")
    return value[size]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- stitch-level ----------

class Op(_Strict):
    """One stitch operation, e.g. k2tog, or k worked n times."""
    op: str                                   # abbreviation id or alias from the KB / pattern glossary
    n: SizedInt = 1


class Until(_Strict):
    """Repeat until `remaining` stitches are left on the left needle (0 = to the end of the row)."""
    remaining: SizedInt = 0


class Repeat(_Strict):
    """A bracketed or starred repeat: `*yo, k2tog, k3; rep from * to last 2 sts`."""
    repeat: list[Item]
    times: SizedInt | None = None
    until: Until | None = None

    @model_validator(mode="after")
    def _one_stop_rule(self) -> Repeat:
        if (self.times is None) == (self.until is None):
            raise ValueError("Repeat needs exactly one of `times` or `until`")
        return self


Item = Union[Op, Repeat]


# ---------- row-level ----------

class Row(_Strict):
    label: str                                # "Row 1", "Rnd 3", "Rows 2 and 4"
    side: Literal["RS", "WS", "round"]
    ops: list[Item]
    stated_count: SizedInt | None = None      # count printed in the pattern, if any


class RowsStep(_Strict):
    type: Literal["rows"] = "rows"
    rows: list[Row]


class RepeatRowsStep(_Strict):
    """Repeat earlier rows a number of times or until the piece reaches a length."""
    type: Literal["repeat_rows"] = "repeat_rows"
    rows_ref: list[str]                       # labels of rows already defined in this piece
    times: SizedInt | None = None
    until_length_cm: float | dict[str, float] | None = None
    until_count: SizedInt | None = None       # "repeat until 44 sts on the needle / 4 sts remain"
    measured_from: Literal["cast_on", "previous_step"] = "cast_on"

    @model_validator(mode="after")
    def _one_stop_rule(self) -> RepeatRowsStep:
        if sum(v is not None for v in (self.times, self.until_length_cm, self.until_count)) != 1:
            raise ValueError("repeat_rows needs exactly one of `times`, `until_length_cm` or `until_count`")
        return self


class BindOffStep(_Strict):
    type: Literal["bind_off"] = "bind_off"
    method: str = "standard"                  # standard, loose, in pattern, ...


Step = Annotated[Union[RowsStep, RepeatRowsStep, BindOffStep], Field(discriminator="type")]


class Piece(_Strict):
    name: str = "body"
    cast_on: SizedInt
    steps: list[Step]


# ---------- pattern-level ----------

class Gauge(_Strict):
    sts_per_10cm: float
    rows_per_10cm: float | None = None
    needle_mm: float | None = None
    stitch_pattern: str | None = "stockinette"


class Source(_Strict):
    kind: Literal["synthetic", "ravelry", "handwritten"] = "synthetic"
    url: str | None = None
    designer: str | None = None


class Pattern(_Strict):
    title: str
    source: Source = Source()
    construction: Literal["flat", "round"]
    gauge: Gauge | None = None
    sizes: list[str] = []
    glossary: dict[str, str] = {}              # pattern-specific abbreviations
    pieces: list[Piece]

    def rows_by_label(self, piece: int = 0) -> dict[str, Row]:
        return {r.label: r for s in self.pieces[piece].steps if isinstance(s, RowsStep) for r in s.rows}


Repeat.model_rebuild()

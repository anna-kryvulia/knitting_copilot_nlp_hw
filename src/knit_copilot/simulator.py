"""Stitch simulator: executes a Pattern IR row by row and computes every stitch count.

Purpose: the code that verifies numbers. Used for gold labels (generator), the parser eval (counts after
simulation), charts, the row tracker, gauge-adjustment checks and the validator.
Input: Pattern, chosen size, piece index, row gauge for "work until X cm" steps.
Output: SimulationResult with one RowState per worked row (expanded ops, start/end counts) and any errors.
Model calls: none. Stitch arithmetic comes only from the abbreviation KB.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from knit_copilot import kb
from knit_copilot.ir import BindOffStep, Item, Op, Pattern, Repeat, RepeatRowsStep, Row, RowsStep, resolve


class SimulationError(Exception):
    def __init__(self, row_label: str, message: str):
        super().__init__(f"{row_label}: {message}")
        self.row_label = row_label
        self.message = message


class RowState(BaseModel):
    number: int                      # 1-based row/round number within the piece
    label: str                       # label from the pattern ("Row 3"), or "Bind off"
    side: str                        # RS | WS | round
    step: int                        # index of the step in the piece
    repeat: int | None = None        # iteration of a repeat_rows step (1-based)
    start_count: int
    end_count: int
    ops: list[str]                   # expanded stitch operations in working order, one per op instance
    stated_count: int | None = None
    markers: list[int] = []          # marker positions on the needle when the row starts
    rec: list = []                   # actual repeat counts (see _run), for display and charts


class SimulationResult(BaseModel):
    piece: str
    size: str | None
    cast_on: int
    rows: list[RowState]
    errors: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def final_count(self) -> int:
        return self.rows[-1].end_count if self.rows else self.cast_on

    def count_mismatches(self) -> list[RowState]:
        """Rows whose stated count differs from the computed count (input for the validator)."""
        return [r for r in self.rows if r.stated_count is not None and r.stated_count != r.end_count]


# ---------- row expansion ----------

def _static_consumption(items: list[Item], size: str | None) -> int:
    """Stitches one pass over `items` uses; ValueError if it depends on the position (nested 'until')."""
    total = 0
    for it in items:
        if isinstance(it, Op):
            total += kb.stitch_op(it.op).consumes * resolve(it.n, size)
        elif it.times is not None:
            total += resolve(it.times, size) * _static_consumption(it.repeat, size)
        else:
            raise ValueError("A repeat with 'until' cannot be nested inside another repeat")
    return total


class _Row:
    """Working state of one row: stitches left, position, markers on both needles, expanded ops.

    Markers are positions between stitches. `markers` = on the left needle, in row-start coordinates
    (number of stitches worked when the marker is reached); `out_markers` = on the right needle, in
    produced-stitch coordinates. Knitting past a marker moves it across implicitly; `sm` does so
    explicitly, `pm` places one, `rm` removes one. In the round, the end of the round counts as the
    beginning-of-round marker.
    """

    def __init__(self, start: int, size: str | None, label: str, markers: list[int], in_round: bool):
        self.start, self.left, self.consumed, self.produced = start, start, 0, 0
        self.size, self.label, self.in_round = size, label, in_round
        self.markers = sorted(markers)
        self.out_markers: list[int] = []
        self.ops: list[str] = []

    def error(self, msg: str) -> SimulationError:
        return SimulationError(self.label, msg)

    def _at_marker(self) -> bool:
        return bool(self.markers) and self.markers[0] == self.consumed

    def pass_markers(self) -> None:
        while self._at_marker():
            self.markers.pop(0)
            self.out_markers.append(self.produced)

    def next_marker(self) -> int:
        for m in self.markers:
            if m >= self.consumed:
                return m
        if self.in_round:
            return self.start
        raise self.error("'to marker' but there is no marker ahead")

    def op(self, op_id: str) -> None:
        a = kb.stitch_op(op_id)
        if a.id == "pm":
            self.out_markers.append(self.produced)
        elif a.id in ("sm", "rm"):
            if self._at_marker():
                m = self.markers.pop(0)
                if a.id == "sm":
                    self.out_markers.append(self.produced)
            elif not (self.in_round and self.consumed == self.start):     # end of round = BOR marker
                raise self.error(f"{a.id}: there is no marker here (after {self.consumed} sts)")
        else:
            if a.consumes > 0:          # an increase made right at a marker (k3, M1R, sm) stays before it
                self.pass_markers()
            if a.consumes > self.left:
                raise self.error(f"{a.id} needs {a.consumes} st(s) but only {self.left} left")
            self.left -= a.consumes
            self.consumed += a.consumes
            self.produced += a.produces
        self.ops.append(a.id)


def _run(items: list[Item], row: _Row) -> list:
    """Work `items`; return a record parallel to `items` (None for an op; for a repeat
    {"times": n, "iters": [record per iteration]}) used by display and charts to show real repeat counts."""
    rec: list = []
    for it in items:
        if isinstance(it, Op):
            for _ in range(resolve(it.n, row.size)):
                row.op(it.op)
            rec.append(None)
            continue
        iters = []
        if it.times is not None:
            for _ in range(resolve(it.times, row.size)):
                iters.append(_run(it.repeat, row))
            rec.append({"times": len(iters), "iters": iters})
            continue
        target = resolve(it.until.remaining, row.size)
        stop = row.next_marker() if it.until.marker else None

        def room() -> int:                       # stitches that may still be worked by this repeat
            return (stop - row.consumed if stop is not None else row.left) - target
        try:
            block = _static_consumption(it.repeat, row.size)
        except ValueError:
            block = None                         # block size depends on position (nested 'until')
        if block == 0:
            raise row.error("repeat consumes no stitches, cannot repeat 'until'")
        while room() > 0 if block is None else room() >= block:
            before = row.consumed
            iters.append(_run(it.repeat, row))
            if row.consumed == before:
                raise row.error("repeat makes no progress")
        if room() != 0:
            where = f"the last {target}" if stop is None else f"{target} before the marker"
            raise row.error(f"repeat does not fit: {room()} st(s) left over before {where}"
                            + (f" (block uses {block})" if block else ""))
        rec.append({"times": len(iters), "iters": iters})
    return rec


def work_row(row: Row, start_count: int, size: str | None = None, markers: list[int] | None = None,
             in_round: bool = False) -> tuple[_Row, list]:
    """Work one row; returns the row state (ops, produced count, markers) and the repeat record."""
    r = _Row(start_count, size, row.label, markers or [], in_round or row.side == "round")
    rec = _run(row.ops, r)
    r.pass_markers()
    if r.left != 0:
        raise SimulationError(row.label, f"row ends with {r.left} unworked st(s)")
    return r, rec


def expand_row(row: Row, start_count: int, size: str | None = None) -> tuple[list[str], int]:
    """Expanded op ids and the end count for one row. Raises SimulationError if the row doesn't fit."""
    r, _ = work_row(row, start_count, size)
    return r.ops, r.produced


def _next_markers(r: _Row) -> list[int]:
    """Markers for the next row: same positions in the round, mirrored when the work is turned."""
    inner = [m for m in r.out_markers if 0 < m < r.produced]
    return sorted(set(inner if r.in_round else [r.produced - m for m in inner]))


# ---------- piece simulation ----------

def simulate(pattern: Pattern, size: str | None = None, piece: int = 0,
             rows_per_10cm: float | None = None, max_rows: int = 5000) -> SimulationResult:
    """Simulate one piece. `rows_per_10cm` overrides the pattern gauge for 'until length' steps."""
    p = pattern.pieces[piece]
    if size is None and pattern.sizes:
        size = pattern.sizes[0]
    count = resolve(p.cast_on, size)
    rows_gauge = rows_per_10cm or (pattern.gauge.rows_per_10cm if pattern.gauge else None)
    by_label = pattern.rows_by_label(piece)
    result = SimulationResult(piece=p.name, size=size, cast_on=count, rows=[])
    markers: list[int] = []
    in_round = pattern.construction == "round"

    def work(row: Row, step: int, repeat: int | None) -> None:
        nonlocal count, markers
        r, rec = work_row(row, count, size, markers, in_round)
        result.rows.append(RowState(number=len(result.rows) + 1, label=row.label, side=row.side, step=step,
                                    repeat=repeat, start_count=count, end_count=r.produced, ops=r.ops,
                                    # a printed count describes the first time the row is worked
                                    stated_count=resolve(row.stated_count, size) if repeat is None else None,
                                    markers=markers, rec=rec))
        count, markers = r.produced, _next_markers(r)

    try:
        for i, step in enumerate(p.steps):
            if isinstance(step, RowsStep):
                for row in step.rows:
                    work(row, i, None)
            elif isinstance(step, RepeatRowsStep):
                missing = [lbl for lbl in step.rows_ref if lbl not in by_label]
                if missing:
                    raise SimulationError(f"step {i + 1}", f"repeat refers to undefined rows {missing}")
                block = [by_label[lbl] for lbl in step.rows_ref]
                if step.times is not None:
                    for r in range(resolve(step.times, size)):
                        for row in block:
                            work(row, i, r + 1)
                elif step.until_count is not None:
                    target, r = resolve(step.until_count, size), 0
                    while count != target:                           # whole repeats only
                        before, r = count, r + 1
                        for row in block:
                            work(row, i, r)
                        if abs(count - target) >= abs(before - target) or len(result.rows) > max_rows:
                            raise SimulationError(f"step {i + 1}", f"repeat never reaches {target} sts "
                                                                   f"(now {count})")
                else:
                    if not rows_gauge:
                        raise SimulationError(f"step {i + 1}", "row gauge needed to work 'until length'")
                    length = step.until_length_cm
                    length = length if isinstance(length, (int, float)) else length[size]
                    needed = math.ceil(length * rows_gauge / 10)
                    done_before = 0 if step.measured_from == "cast_on" else len(result.rows)
                    r = 0
                    while len(result.rows) - done_before < needed:   # whole repeats only
                        r += 1
                        for row in block:
                            work(row, i, r)
                        if len(result.rows) > max_rows:
                            raise SimulationError(f"step {i + 1}", "too many rows")
            elif isinstance(step, BindOffStep):
                result.rows.append(RowState(number=len(result.rows) + 1, label="Bind off", side="", step=i,
                                            start_count=count, end_count=0, ops=["bo"] * count))
                count = 0
    except (SimulationError, KeyError, ValueError) as e:
        result.errors.append(str(e))
    return result

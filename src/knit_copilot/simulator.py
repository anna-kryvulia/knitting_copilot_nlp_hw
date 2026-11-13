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
    total = 0
    for it in items:
        if isinstance(it, Op):
            total += kb.stitch_op(it.op).consumes * resolve(it.n, size)
        elif it.times is not None:
            total += resolve(it.times, size) * _static_consumption(it.repeat, size)
        else:
            raise ValueError("A repeat with 'until' cannot be nested inside another repeat")
    return total


def _run(items: list[Item], left: int, size: str | None, out: list[str], label: str) -> int:
    """Work `items` with `left` stitches on the left needle; append op ids to `out`; return stitches left."""
    for it in items:
        if isinstance(it, Op):
            a = kb.stitch_op(it.op)
            for _ in range(resolve(it.n, size)):
                if a.consumes > left:
                    raise SimulationError(label, f"{a.id} needs {a.consumes} st(s) but only {left} left")
                left -= a.consumes
                out.append(a.id)
        elif isinstance(it, Repeat):
            if it.times is not None:
                for _ in range(resolve(it.times, size)):
                    left = _run(it.repeat, left, size, out, label)
            else:
                target = resolve(it.until.remaining, size)
                block = _static_consumption(it.repeat, size)
                if block == 0:
                    raise SimulationError(label, "repeat consumes no stitches, cannot repeat 'until'")
                while left - target >= block:
                    left = _run(it.repeat, left, size, out, label)
                if left != target:
                    raise SimulationError(label, f"repeat does not fit: {left - target} st(s) left over "
                                                 f"before the last {target} (block uses {block})")
    return left


def expand_row(row: Row, start_count: int, size: str | None = None) -> tuple[list[str], int]:
    """Expanded op ids and the end count for one row. Raises SimulationError if the row doesn't fit."""
    out: list[str] = []
    left = _run(row.ops, start_count, size, out, row.label)
    if left != 0:
        raise SimulationError(row.label, f"row ends with {left} unworked st(s)")
    produced = sum(kb.stitch_op(o).produces for o in out)
    return out, produced


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

    def work(row: Row, step: int, repeat: int | None) -> None:
        nonlocal count
        ops, end = expand_row(row, count, size)
        result.rows.append(RowState(number=len(result.rows) + 1, label=row.label, side=row.side, step=step,
                                    repeat=repeat, start_count=count, end_count=end, ops=ops,
                                    stated_count=resolve(row.stated_count, size)))
        count = end

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

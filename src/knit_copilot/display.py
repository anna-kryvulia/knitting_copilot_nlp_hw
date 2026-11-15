"""Human-readable descriptions of simulated rows (used by the UI, and later the explainer and tracker).

Purpose: show a row the way a knitter reads it ("k2, (yo, k2tog, k3) ×6, k2"), with every repeat count
computed by code from the stitch count, and group long runs of repeated rows.
Input: Pattern IR + SimulationResult. Output: strings / table rows. Model calls: none.
"""

from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel

from knit_copilot import kb
from knit_copilot.ir import Item, Op, Pattern, Row, resolve
from knit_copilot.simulator import RowState, SimulationResult, _static_consumption

BASIC = {"k", "p"}


def _op_text(op: str, n: int) -> str:
    if op in BASIC:
        return f"{op}{n}"
    return op if n == 1 else f"{op} ×{n}"


def _describe(items: list[Item], left: int, size: str | None) -> tuple[str, int]:
    parts = []
    for it in items:
        if isinstance(it, Op):
            n = resolve(it.n, size)
            parts.append(_op_text(kb.stitch_op(it.op).id, n))
            left -= kb.stitch_op(it.op).consumes * n
            continue
        block = _static_consumption(it.repeat, size)
        times = resolve(it.times, size) if it.times is not None else \
            (left - resolve(it.until.remaining, size)) // block if block else 0
        left -= block * times
        single = len(it.repeat) == 1 and isinstance(it.repeat[0], Op)
        if single:                                   # "k to end" → k88, "(k2tog) 3 times" → k2tog ×3
            op = kb.stitch_op(it.repeat[0].op).id
            parts.append(_op_text(op, times * resolve(it.repeat[0].n, size)))
        else:
            inner, _ = _describe(it.repeat, block, size)
            parts.append(f"({inner}) ×{times}")
    return ", ".join(parts), left


def describe_row(row: Row, start_count: int, size: str | None = None) -> str:
    """'K2, *yo, k2tog, k3; rep from * to last 2 sts, k2' with 34 sts → 'k2, (yo, k2tog, k3) ×6, k2'."""
    text, _ = _describe(row.ops, start_count, size)
    return text


class RowLine(BaseModel):
    rows: str           # "Row 5" or "Rows 5–580"
    instruction: str    # "Row 1" or "Rows 1–4 × 144"
    side: str
    stitches: str       # "88 → 88"
    stated: str
    worked_as: str


def _span(word: str, first: int, last: int) -> str:
    return f"{word} {first}" if first == last else f"{word}s {first}–{last}"


def _label_range(labels: list[str]) -> str:
    """['Row 1', 'Row 2', 'Row 3', 'Row 4'] → 'Rows 1–4'; ['Rnd 1'] → 'Rnd 1'; other labels joined with commas."""
    if len(labels) == 1:
        return labels[0]

    nums = [re.fullmatch(r"(Row|Rnd) (\d+)", lb) for lb in labels]
    if all(nums) and len({m.group(1) for m in nums}) == 1:
        return f"{nums[0].group(1)}s {nums[0].group(2)}–{nums[-1].group(2)}"
    return ", ".join(labels)


def row_lines(pattern: Pattern, sim: SimulationResult, grouped: bool = True) -> list[RowLine]:
    """Table lines for the UI. Grouped: every repeat_rows step becomes one line."""
    by_label = pattern.rows_by_label()
    word = "Rnd" if pattern.construction == "round" else "Row"
    totals = Counter(r.label for r in sim.rows)
    seen: Counter = Counter()

    def single(r: RowState, show_times: bool) -> RowLine:
        seen[r.label] += 1
        ir_row = by_label.get(r.label)
        how = describe_row(ir_row, r.start_count, sim.size) if ir_row else f"bind off {r.start_count} sts"
        times = f" (time {seen[r.label]} of {totals[r.label]})" if show_times and totals[r.label] > 1 else ""
        return RowLine(rows=f"{word} {r.number}", instruction=r.label + times, side=r.side,
                       stitches=f"{r.start_count} → {r.end_count}",
                       stated="" if r.stated_count is None else str(r.stated_count), worked_as=how)

    if not grouped:
        return [single(r, show_times=True) for r in sim.rows]

    lines: list[RowLine] = []
    i = 0
    while i < len(sim.rows):
        r = sim.rows[i]
        if r.repeat is None:
            lines.append(single(r, show_times=False))
            i += 1
            continue
        j = i
        while j < len(sim.rows) and sim.rows[j].step == r.step:
            j += 1
        block = sim.rows[i:j]
        labels = list(dict.fromkeys(x.label for x in block))
        reps = block[-1].repeat
        name = labels[0] if len(labels) == 1 else _label_range(labels)
        how = "; ".join(f"{lb}: {describe_row(by_label[lb], next(x.start_count for x in block if x.label == lb), sim.size)}"
                        for lb in labels if lb in by_label)
        for x in block:
            seen[x.label] += 1
        lines.append(RowLine(rows=_span(word, block[0].number, block[-1].number),
                             instruction=f"{name} × {reps} more", side="",
                             stitches=f"{block[0].start_count} → {block[-1].end_count}", stated="", worked_as=how))
        i = j
    return lines

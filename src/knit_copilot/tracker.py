"""Row tracker (UC5): where am I, what is this row, how many stitches should I have. Pure code.

Purpose: follow the locked working pattern row by row.
Input: a Project in the knitting stage. Output: RowView for the current row; next/prev/goto move the position.
Model calls: none.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from knit_copilot.display import describe_row
from knit_copilot.project import Project
from knit_copilot.simulator import SimulationResult, simulate


class RowView(BaseModel):
    index: int                  # 0-based position in the worked rows
    number: int                 # row/round number in the piece (1-based)
    total: int
    label: str
    side: str
    instruction: str
    start_count: int
    end_count: int
    stated_count: int | None
    time_of: str                # "time 3 of 14" when the row is repeated, else ""
    rows_left: int
    percent: int


def _sim(p: Project) -> SimulationResult:
    if p.stage != "knitting" or p.working is None:
        raise ValueError("Generate the working pattern first.")
    w = p.working.pattern
    return simulate(w, None, rows_per_10cm=w.gauge.rows_per_10cm if w.gauge else None)


def view(p: Project) -> RowView:
    sim = _sim(p)
    i = max(0, min(p.row_index, len(sim.rows) - 1))
    r = sim.rows[i]
    by_label = p.working.pattern.rows_by_label()
    totals = Counter(x.label for x in sim.rows)
    nth = sum(1 for x in sim.rows[: i + 1] if x.label == r.label)
    how = describe_row(by_label[r.label], r.start_count, None, r.rec) if r.label in by_label \
        else f"bind off all {r.start_count} sts"
    return RowView(index=i, number=r.number, total=len(sim.rows), label=r.label, side=r.side, instruction=how,
                   start_count=r.start_count, end_count=r.end_count, stated_count=r.stated_count,
                   time_of=f"time {nth} of {totals[r.label]}" if totals[r.label] > 1 else "",
                   rows_left=len(sim.rows) - i - 1, percent=round(100 * i / max(1, len(sim.rows) - 1)))


def goto(p: Project, index: int) -> RowView:
    total = len(_sim(p).rows)
    p.row_index = max(0, min(index, total - 1))
    return view(p)


def next_row(p: Project, n: int = 1) -> RowView:
    return goto(p, p.row_index + n)


def prev_row(p: Project, n: int = 1) -> RowView:
    return goto(p, p.row_index - n)

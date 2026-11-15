"""Gauge adjustment (UC2): adapt a pattern to the knitter's gauge so the finished size stays the same.

Purpose: all the maths of UC2, in code. The LLM rewriter (components/rewriter.py) only rewrites the text.
Input: Pattern IR, chosen size, knitter gauge (stitches and optionally rows per 10 cm).
Output: Adjustment (adjusted single-size IR with the knitter's gauge, list of changes, finished dimensions
before/after, and whether the chosen stitch count is the closest one that keeps every repeat intact).
Model calls: none.

Rules (business rule BR8: repeats stay intact):
- Width: target stitch count = original × knitter_sts / pattern_sts. The cast-on is set to the valid count
  closest to the target, where "valid" = the whole piece simulates without errors (every "rep to end / to
  last n sts" fits). Single fixed-count repeats in a row ("(p2, k6) ×2") are re-solved for the new count;
  "repeat until N sts" targets are scaled by the same factor.
- Length: "until X cm" stays X cm (the simulator converts it to rows with the knitter's row gauge);
  fixed repeat counts of row blocks are scaled by knitter_rows / pattern_rows (total passes, rounded).
- Stitch-level details (edge stitches, motif sizes) never change.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from knit_copilot import kb
from knit_copilot.ir import Gauge, Op, Pattern, Repeat, RepeatRowsStep, RowsStep, resolve
from knit_copilot.simulator import _static_consumption, simulate

SEARCH_SHARE = 0.3          # search valid counts within ±30 % of the target


class KnitterGauge(BaseModel):
    sts_per_10cm: float
    rows_per_10cm: float | None = None
    needle_mm: float | None = None


class Change(BaseModel):
    what: str
    old: float | int | str
    new: float | int | str


class Dimensions(BaseModel):
    width_cm: float
    length_cm: float | None
    max_stitches: int
    rows: int


class Adjustment(BaseModel):
    pattern: Pattern                  # adjusted, single size, knitter's gauge
    size: str | None
    changes: list[Change]
    before: Dimensions
    after: Dimensions
    target_stitches: float
    chosen_stitches: int
    closest_valid: bool               # no valid count is closer to the target
    notes: list[str] = []
    ok: bool = True


def flatten_size(pattern: Pattern, size: str | None) -> Pattern:
    """Copy of the pattern with every per-size value resolved for `size` (sizes = [])."""
    if not pattern.sizes:
        return pattern.model_copy(deep=True)
    size = size or pattern.sizes[0]
    keys = set(pattern.sizes)

    def walk(x):
        if isinstance(x, dict):
            if set(x) == keys and all(isinstance(v, (int, float)) for v in x.values()):
                return x[size]
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    data = walk(pattern.model_dump(mode="json"))
    data["sizes"] = []
    data["title"] = f"{pattern.title} (size {size})"
    return Pattern.model_validate(data)


def dimensions(pattern: Pattern, sts_per_10cm: float, rows_per_10cm: float | None) -> Dimensions:
    sim = simulate(pattern, None, rows_per_10cm=rows_per_10cm)
    widest = max([sim.cast_on] + [r.end_count for r in sim.rows if r.label != "Bind off"])
    worked = len([r for r in sim.rows if r.label != "Bind off"])
    return Dimensions(width_cm=round(widest / sts_per_10cm * 10, 1),
                      length_cm=round(worked / rows_per_10cm * 10, 1) if rows_per_10cm else None,
                      max_stitches=widest, rows=worked)


def _resolve_times_repeat(row_ops: list, count: int) -> list | None:
    """If the row has exactly one top-level fixed-count repeat, recompute its count for `count` stitches."""
    reps = [i for i, it in enumerate(row_ops) if isinstance(it, Repeat) and it.times is not None]
    if len(reps) != 1 or any(isinstance(it, Repeat) and it.until is not None for it in row_ops):
        return None
    i = reps[0]
    fixed = _static_consumption([it for j, it in enumerate(row_ops) if j != i], None)
    block = _static_consumption(row_ops[i].repeat, None)
    if block == 0 or (count - fixed) % block or (count - fixed) // block < 1:
        return []                                             # cannot fit: candidate invalid
    new = [it.model_copy(deep=True) for it in row_ops]
    new[i].times = (count - fixed) // block
    return new


def _candidate(base: Pattern, cast_on: int, fs: float, fr: float | None) -> Pattern | None:
    p = base.model_copy(deep=True)
    piece = p.pieces[0]
    orig_cast_on = piece.cast_on
    piece.cast_on = cast_on
    for step in piece.steps:
        if isinstance(step, RowsStep):
            for row in step.rows:
                new = _resolve_times_repeat(row.ops, cast_on)
                if new == []:
                    return None
                if new:
                    row.ops = new
        elif isinstance(step, RepeatRowsStep):
            if step.until_count is not None:
                # "decrease back to the cast-on count" (a corner, a point) follows the new cast-on;
                # other targets are widths and scale with the gauge
                step.until_count = cast_on if step.until_count == orig_cast_on else max(1, round(step.until_count * fs))
            elif step.times is not None and fr is not None:
                step.times = max(0, round((step.times + 1) * fr) - 1)
    return p


def adjust(pattern: Pattern, size: str | None, knitter: KnitterGauge) -> Adjustment:
    if pattern.gauge is None:
        raise ValueError("the pattern has no gauge, so it cannot be adjusted")
    pg = pattern.gauge
    base = flatten_size(pattern, size)
    fs = knitter.sts_per_10cm / pg.sts_per_10cm
    fr = knitter.rows_per_10cm / pg.rows_per_10cm if knitter.rows_per_10cm and pg.rows_per_10cm else None
    notes = []
    if fr is None:
        notes.append("Row gauge not given: lengths are worked to the same measurements, row counts of fixed "
                     "repeats are kept as written.")
    before = dimensions(base, pg.sts_per_10cm, pg.rows_per_10cm)
    orig = resolve(base.pieces[0].cast_on, None)
    target = orig * fs

    span = max(4, math.ceil(target * SEARCH_SHARE))
    order = sorted(range(max(1, math.floor(target) - span), math.ceil(target) + span + 1),
                   key=lambda c: (abs(c - target), c))
    chosen, adjusted = None, None
    for c in order:
        cand = _candidate(base, c, fs, fr)
        if cand is None:
            continue
        cand.gauge = Gauge(sts_per_10cm=knitter.sts_per_10cm, rows_per_10cm=knitter.rows_per_10cm or pg.rows_per_10cm,
                           needle_mm=knitter.needle_mm or pg.needle_mm, stitch_pattern=pg.stitch_pattern)
        sim = simulate(cand, None)
        if sim.ok and all(r.end_count > 0 for r in sim.rows if r.label != "Bind off"):
            chosen, adjusted = c, cand
            break
    if adjusted is None:
        return Adjustment(pattern=base, size=size, changes=[], before=before, after=before, target_stitches=target,
                          chosen_stitches=orig, closest_valid=False, ok=False,
                          notes=notes + ["No stitch count near the target keeps every repeat intact."])

    after = dimensions(adjusted, knitter.sts_per_10cm, adjusted.gauge.rows_per_10cm)
    width_change = after.width_cm - before.width_cm
    if abs(width_change) > 1.0:
        motif = max((_static_consumption(it.repeat, None) for st in adjusted.pieces[0].steps if isinstance(st, RowsStep)
                     for r in st.rows for it in r.ops if isinstance(it, Repeat)), default=1)
        notes.append(f"The stitch pattern repeats every {motif} stitches, so the width can only change in steps of "
                     f"{motif / knitter.sts_per_10cm * 10:.1f} cm at your gauge: the closest fit is "
                     f"{after.width_cm:g} cm instead of {before.width_cm:g} cm ({width_change:+.1f} cm). "
                     f"To match exactly, change needle size to get closer to the pattern gauge.")
    changes = [Change(what="cast on (stitches)", old=orig, new=chosen)]
    for s0, s1 in zip(base.pieces[0].steps, adjusted.pieces[0].steps):
        if isinstance(s0, RepeatRowsStep):
            ref = ", ".join(s0.rows_ref)
            if s0.until_count is not None and s0.until_count != s1.until_count:
                changes.append(Change(what=f"repeat {ref} until … stitches", old=s0.until_count, new=s1.until_count))
            if s0.times is not None and s0.times != s1.times:
                changes.append(Change(what=f"repeat {ref} … more times", old=s0.times, new=s1.times))
        elif isinstance(s0, RowsStep):
            for r0, r1 in zip(s0.rows, s1.rows):
                if r0.ops != r1.ops:
                    changes.append(Change(what=f"{r0.label}: repeat count", old=_times(r0.ops), new=_times(r1.ops)))
    changes.append(Change(what="widest point (stitches)", old=before.max_stitches, new=after.max_stitches))
    changes.append(Change(what="rows worked", old=before.rows, new=after.rows))
    return Adjustment(pattern=adjusted, size=size, changes=changes, before=before, after=after,
                      target_stitches=round(target, 2), chosen_stitches=chosen,
                      closest_valid=True, notes=notes)


def _times(ops) -> int | None:
    return next((it.times for it in ops if isinstance(it, Repeat) and it.times is not None), None)


def motifs(pattern: Pattern) -> list[str]:
    """Every repeat block as text (stitch-level motifs) — must be identical before and after adjustment."""
    out = []

    def walk(items):
        for it in items:
            if isinstance(it, Repeat):
                out.append(",".join(kb.stitch_op(x.op).id + str(x.n) if isinstance(x, Op) else "R" for x in it.repeat))
                walk(it.repeat)
    for step in pattern.pieces[0].steps:
        if isinstance(step, RowsStep):
            for r in step.rows:
                walk(r.ops)
    return out

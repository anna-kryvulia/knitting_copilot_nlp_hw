"""Fact sheet for a pattern: every number and definition the explainer is allowed to use.

Purpose: keep numbers in code (AGENTS.md §4). The explainer LLM only rewrites these facts in plain English;
the check in components/explainer.py rejects any number or citation that is not in the fact sheet.
Input: Pattern IR, size, optional row gauge. Output: FactSheet (text for the prompt + allowed numbers/ids).
Model calls: none.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from knit_copilot import kb
from knit_copilot.display import _label_range, describe_row
from knit_copilot.ir import BindOffStep, Pattern, RepeatRowsStep, RowsStep, resolve
from knit_copilot.simulator import simulate


class StepFacts(BaseModel):
    step: int
    title: str                 # "Rows 1–4", "Repeat Rows 1–4", "Bind off"
    lines: list[str]           # fact lines for the prompt
    ops: list[str]             # KB ids used in this step


class FactSheet(BaseModel):
    overview: list[str]
    steps: list[StepFacts]
    abbreviations: dict[str, str]          # id -> "name: description"
    numbers: set[float]                    # every number that may appear in an explanation
    ok: bool
    errors: list[str] = []

    def as_text(self) -> str:
        out = ["OVERVIEW"] + [f"- {x}" for x in self.overview]
        for s in self.steps:
            out += ["", f"STEP {s.step}: {s.title}"] + [f"- {x}" for x in s.lines]
        out += ["", "ABBREVIATIONS USED (cite as [id])"] + [f"- [{k}] {v}" for k, v in self.abbreviations.items()]
        return "\n".join(out)


def _ops_in(items) -> list[str]:
    ids = []
    for it in items:
        if hasattr(it, "op"):
            ids.append(kb.stitch_op(it.op).id)
        else:
            ids += _ops_in(it.repeat)
    return ids


def _nums(text: str) -> set[float]:
    return {float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)}


def build(pattern: Pattern, size: str | None = None, rows_per_10cm: float | None = None) -> FactSheet:
    if size is None and pattern.sizes:
        size = pattern.sizes[0]
    sim = simulate(pattern, size, rows_per_10cm=rows_per_10cm)
    word = "round" if pattern.construction == "round" else "row"
    piece = pattern.pieces[0]
    overview = [
        f"Knitted {'in the round' if pattern.construction == 'round' else 'flat, back and forth in rows'}.",
        f"Cast on {sim.cast_on} stitches." + (f" (size {size}; sizes: {', '.join(pattern.sizes)})" if pattern.sizes else ""),
        f"In total {len(sim.rows)} {word}s are worked, including the bind-off.",
    ]
    if pattern.gauge:
        g = pattern.gauge
        overview.append(f"Pattern gauge: {g.sts_per_10cm:g} stitches"
                        + (f" and {g.rows_per_10cm:g} {word}s" if g.rows_per_10cm else "")
                        + f" per 10 cm in {g.stitch_pattern}" + (f", on {g.needle_mm:g} mm needles." if g.needle_mm else "."))
    if sim.errors:
        overview.append(f"WARNING: the stitch counts do not work out: {sim.errors[0]}")

    by_label = pattern.rows_by_label()
    first_start = {}
    for r in sim.rows:
        first_start.setdefault(r.label, r)
    steps: list[StepFacts] = []
    used: list[str] = []
    for i, step in enumerate(piece.steps):
        worked = [r for r in sim.rows if r.step == i]
        if isinstance(step, RowsStep):
            lines, ops = [], []
            for row in step.rows:
                r = first_start.get(row.label)
                if r is None:
                    continue
                how = describe_row(row, r.start_count, size, r.rec)
                side = {"RS": "right side", "WS": "wrong side"}.get(r.side, "")
                change = r.end_count - r.start_count
                delta = "no change" if change == 0 else (f"{change:+d} stitches")
                line = f"{row.label}{f' ({side})' if side else ''}: work {how}. Stitches {r.start_count} → {r.end_count} ({delta})."
                if r.stated_count is not None:
                    line += f" The pattern states {r.stated_count} stitches" + (
                        " — matches." if r.stated_count == r.end_count else f" — but the computed count is {r.end_count}.")
                lines.append(line)
                ops += _ops_in(row.ops)
            title = _label_range([r.label for r in step.rows])
        elif isinstance(step, RepeatRowsStep):
            reps = worked[-1].repeat if worked else 0
            ref = _label_range(step.rows_ref)
            if step.times is not None:
                rule = f"repeat {ref} {resolve(step.times, size)} more times"
            elif step.until_count is not None:
                rule = f"repeat {ref} until there are {resolve(step.until_count, size)} stitches"
            else:
                length = step.until_length_cm if isinstance(step.until_length_cm, (int, float)) else step.until_length_cm[size]
                rule = f"repeat {ref} until the piece measures {length:g} cm"
            lines = [f"Rule: {rule}.",
                     f"With the gauge used, that means {reps} more repeats = {len(worked)} {word}s "
                     f"({word}s {worked[0].number}–{worked[-1].number} of the piece)." if worked else "Not worked.",
                     f"Stitches {worked[0].start_count} → {worked[-1].end_count}." if worked else ""]
            lines = [x for x in lines if x]
            ops = [o for lb in step.rows_ref if lb in by_label for o in _ops_in(by_label[lb].ops)]
            title = f"Repeat {ref}"
        elif isinstance(step, BindOffStep):
            n = worked[0].start_count if worked else 0
            how = "Break the yarn and draw it through the remaining stitches." if step.method == "gather" else \
                f"Bind off all {n} stitches ({step.method})."
            lines, ops, title = [how], ([] if step.method == "gather" else ["bo"]), "Finish"
        else:
            continue
        steps.append(StepFacts(step=len(steps) + 1, title=title, lines=lines, ops=list(dict.fromkeys(ops))))
        used += ops

    abbrs = {}
    for op in dict.fromkeys(used):
        a = kb.abbreviations()[op]
        abbrs[op] = f"{a.name}: {a.description}"
    sheet = FactSheet(overview=overview, steps=steps, abbreviations=abbrs, numbers=set(), ok=sim.ok, errors=sim.errors)
    # numbers allowed in explanations: everything in the fact text (incl. definitions, e.g. "2" in k2tog)
    sheet.numbers = _nums(sheet.as_text()) | {1, 2, 3, 10}
    return sheet

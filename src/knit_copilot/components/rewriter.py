"""Rewriter (UC2): write the gauge-adjusted pattern in the style of the original text, verified by code.

Purpose: the knitter gets their own version of the pattern, not just a list of numbers.
Input: original text, the original IR and the Adjustment from gauge.py. Output: RewriterOutput(text, method,
verified, problems). Model calls: yes (prompts/rewriter.md), up to 1 + MAX_REPAIRS. Tool calls: parser (hybrid).

1. Code builds the EDIT list from the adjusted IR (new cast-on, stated counts, repeat counts, gauge, one size).
2. The LLM applies the edits to the original text.
3. Verification: the new text is parsed (hybrid parser) and simulated at the knitter's gauge; every row must
   have the same stitches and counts as the adjusted IR (AGENTS.md: never show an LLM-written pattern
   that does not re-parse and simulate to the expected counts). One repair with the concrete mismatch.
4. Fallback: a code-rendered version of the adjusted IR (terse notation), also verified.
"""

from __future__ import annotations

import random
import time

from pydantic import BaseModel

from knit_copilot import llm
from knit_copilot.components import parser
from knit_copilot.data.generator import render
from knit_copilot.gauge import Adjustment, flatten_size
from knit_copilot.ir import Pattern, Repeat, RepeatRowsStep, RowsStep, resolve
from knit_copilot.simulator import simulate

MAX_REPAIRS = 1


class RewriterOutput(BaseModel):
    text: str
    method: str                 # llm | llm+repair | code_render
    verified: bool
    problems: list[str] = []
    attempts: int = 0


def edits(original: Pattern, adj: Adjustment) -> list[str]:
    base = flatten_size(original, adj.size)
    new = adj.pattern
    sim = simulate(new, None)
    first = {}
    for r in sim.rows:
        first.setdefault(r.label, r)
    out = []
    if original.sizes:
        out.append(f"The knitter makes size {adj.size}: wherever several sizes are given, keep only that size's "
                   f"value (and drop the 'Sizes' line or reduce it to {adj.size}).")
    g = new.gauge
    out.append(f"Gauge line: {g.sts_per_10cm:g} sts" + (f" and {g.rows_per_10cm:g} rows" if g.rows_per_10cm else "")
               + " = 10 cm" + (f"; needles {g.needle_mm:g} mm" if g.needle_mm else "") + ".")
    out.append(f"Cast on: {base.pieces[0].cast_on} → {new.pieces[0].cast_on} stitches.")
    for s0, s1 in zip(base.pieces[0].steps, new.pieces[0].steps):
        if isinstance(s0, RowsStep):
            for r0, r1 in zip(s0.rows, s1.rows):
                t0 = [it.times for it in r0.ops if isinstance(it, Repeat) and it.times is not None]
                t1 = [it.times for it in r1.ops if isinstance(it, Repeat) and it.times is not None]
                if t0 != t1:
                    out.append(f"{r0.label}: the repeated group is now worked {t1[0]} times in total (was {t0[0]}).")
                if r0.stated_count is not None and r1.label in first:
                    old, newc = resolve(r0.stated_count, None), first[r1.label].end_count
                    if old != newc:
                        out.append(f"{r0.label}: stated stitch count {old} → {newc}.")
        elif isinstance(s0, RepeatRowsStep):
            ref = ", ".join(s0.rows_ref)
            if s0.times is not None and s0.times != s1.times:
                out.append(f"Repeat of {ref}: worked {s1.times} more times (was {s0.times} more times), "
                           f"i.e. {s1.times + 1} times in total.")
            if s0.until_count is not None and s0.until_count != s1.until_count:
                out.append(f"Repeat of {ref}: until {s1.until_count} stitches (was {s0.until_count}).")
    return out


def _same(text: str, expected: Pattern) -> list[str]:
    """Parse `text` and compare its simulation with the expected IR row by row."""
    res = parser.run(parser.ParserInput(text=text, mode="hybrid", time_budget_s=60))
    if not res.ok:
        return ["the new text could not be parsed: " + "; ".join(res.warnings[:2])]
    rows_gauge = expected.gauge.rows_per_10cm if expected.gauge else None
    got = simulate(res.pattern, None, rows_per_10cm=rows_gauge)
    want = simulate(expected, None)
    if not got.ok:
        return ["the new text does not work out: " + got.errors[0]]
    if len(got.rows) != len(want.rows):
        return [f"the new text gives {len(got.rows)} rows, expected {len(want.rows)}"]
    for g, w in zip(got.rows, want.rows):
        if g.ops != w.ops or g.end_count != w.end_count:
            return [f"{w.label} (row {w.number}): text gives {g.end_count} sts, expected {w.end_count}"]
    return []


def code_render(adj: Adjustment) -> str:
    text, _ = render(adj.pattern, "terse", random.Random(0))
    return text


def run(original_text: str, original: Pattern, adj: Adjustment, use_llm: bool = True,
        time_budget_s: float = 90) -> RewriterOutput:
    attempts, problems = 0, []
    if use_llm:
        deadline = time.monotonic() + time_budget_s
        feedback = ""
        edit_text = "\n".join(f"- {e}" for e in edits(original, adj))
        for i in range(1 + MAX_REPAIRS):
            attempts += 1
            try:
                msgs = llm.render("rewriter", text=original_text, edits=edit_text, feedback=feedback)
                text = (llm.chat(msgs, max_tokens=6000, deadline=deadline)["content"] or "").strip().strip('"')
            except (RuntimeError, ValueError) as e:
                problems = [f"llm: {e}"]
                break
            problems = _same(text, adj.pattern)
            if not problems:
                return RewriterOutput(text=text, method="llm" if i == 0 else "llm+repair", verified=True,
                                      attempts=attempts)
            feedback = "\nYOUR PREVIOUS VERSION WAS WRONG: " + problems[0] + ". Apply the edits exactly."
    text = code_render(adj)
    return RewriterOutput(text=text, method="code_render", verified=not _same(text, adj.pattern),
                          problems=problems, attempts=attempts)

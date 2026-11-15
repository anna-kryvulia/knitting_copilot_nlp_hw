"""Project workflow: setup (editable) → "Generate working pattern" (locked version) → knitting.

Purpose: business rules BR1–BR3 of docs/01_business_understanding.md, in plain code. The setup agent's tool calls
and the UI form both call these functions; the LLM never changes project state any other way.
Input: tool arguments as the user stated them (units converted here, never by the LLM).
Output: ToolResult messages; the Project object is updated in place (save it with db.save).
Model calls: none (set_pattern uses the parser, which may call the LLM in hybrid mode).
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from knit_copilot import units
from knit_copilot.gauge import Adjustment, KnitterGauge, adjust
from knit_copilot.ir import Pattern

Stage = Literal["setup", "knitting"]


class YarnChoice(BaseModel):
    text: str | None = None          # as the user wrote it
    yarn_id: int | None = None       # linked row of data/yarns.csv
    label: str | None = None         # "YarnArt Jeans"
    fibre: str | None = None
    weight: str | None = None


class Project(BaseModel):
    id: str
    name: str
    stage: Stage = "setup"
    version: int = 1
    yarn: YarnChoice | None = None
    needle_mm: float | None = None
    gauge_sts_10cm: float | None = None
    gauge_rows_10cm: float | None = None
    pattern_text: str | None = None
    pattern: Pattern | None = None
    size: str | None = None
    working: Adjustment | None = None        # the locked, gauge-adjusted pattern
    row_index: int = 0                       # tracker position (0-based index of worked rows)
    history: list[str] = []                  # short log of versions


class ToolResult(BaseModel):
    ok: bool
    message: str
    data: dict = {}


class ProjectLocked(Exception):
    pass


def new_project(name: str = "My project") -> Project:
    return Project(id=uuid.uuid4().hex[:12], name=name)


# ---------- guards ----------

def _editable(p: Project) -> ToolResult | None:
    if p.stage != "setup":
        return ToolResult(ok=False, message=f"The project is locked (version {p.version} is being knitted). "
                                            f"To change it, start over from setup — progress will be reset.")
    return None


def missing(p: Project) -> list[str]:
    """Fields still needed before the working pattern can be generated (yarn is optional)."""
    out = []
    if p.pattern is None:
        out.append("pattern")
    if p.pattern is not None and p.pattern.sizes and p.size not in p.pattern.sizes:
        out.append("size")
    if p.gauge_sts_10cm is None:
        out.append("gauge")
    if p.needle_mm is None:
        out.append("needles")
    return out


# ---------- tools (also used by the UI form) ----------

def set_yarn(p: Project, name: str | None = None, fibre: str | None = None, weight: str | None = None) -> ToolResult:
    if (err := _editable(p)):
        return err
    from knit_copilot.components import yarn_linker
    if name:
        link = yarn_linker.run(yarn_linker.LinkerInput(text=name))
        if link.status == "match":
            c = link.candidates[0]
            p.yarn = YarnChoice(text=name, yarn_id=link.yarn_id, label=f"{c.brand} {c.name}")
            return ToolResult(ok=True, message=f"Yarn set to {c.brand} {c.name}.", data={"yarn_id": link.yarn_id})
        if link.status == "ambiguous":
            options = [f"{c.brand} {c.name}" for c in link.candidates]
            return ToolResult(ok=False, message=f"Several yarns are called that: {', '.join(options)}. Which one?",
                              data={"candidates": options})
        p.yarn = YarnChoice(text=name, fibre=fibre, weight=weight)
        return ToolResult(ok=True, message=f"'{name}' is not in the yarn table; stored as written"
                                           + (f" ({fibre}, {weight})" if fibre or weight else "")
                                           + ". Tell me its fibre and weight for advice.", data={"linked": False})
    if fibre or weight:
        p.yarn = YarnChoice(fibre=fibre, weight=weight, label=" ".join(x for x in (fibre, weight) if x))
        return ToolResult(ok=True, message=f"Yarn set to {p.yarn.label} (no specific yarn).")
    return ToolResult(ok=False, message="Give a yarn name, or its fibre and weight.")


def set_needles(p: Project, size: float, system: Literal["mm", "us"] = "mm") -> ToolResult:
    if (err := _editable(p)):
        return err
    try:
        mm = float(size) if system == "mm" else units.us_needle_to_mm(size)
    except KeyError:
        return ToolResult(ok=False, message=f"Unknown US needle size {size}.")
    if not 1.0 <= mm <= 30:
        return ToolResult(ok=False, message=f"{mm} mm is not a knitting needle size.")
    p.needle_mm = mm
    return ToolResult(ok=True, message=f"Needles set to {mm:g} mm.", data={"needle_mm": mm})


def set_gauge(p: Project, stitches: float, rows: float | None = None, over: float = 10,
              unit: Literal["cm", "in"] = "cm") -> ToolResult:
    if (err := _editable(p)):
        return err
    if stitches <= 0 or over <= 0:
        return ToolResult(ok=False, message="Gauge needs a positive number of stitches and a width.")
    p.gauge_sts_10cm = units.gauge_to_per_10cm(stitches, over, unit)
    p.gauge_rows_10cm = units.gauge_to_per_10cm(rows, over, unit) if rows else None
    msg = f"Gauge set to {p.gauge_sts_10cm:g} sts" + (f" × {p.gauge_rows_10cm:g} rows" if p.gauge_rows_10cm else "") + " per 10 cm."
    return ToolResult(ok=True, message=msg, data={"sts": p.gauge_sts_10cm, "rows": p.gauge_rows_10cm})


def set_pattern(p: Project, text: str, mode: Literal["hybrid", "llm"] = "hybrid") -> ToolResult:
    if (err := _editable(p)):
        return err
    from knit_copilot.components import parser
    out = parser.run(parser.ParserInput(text=text, mode=mode))
    if not out.ok:
        return ToolResult(ok=False, message="I could not read this pattern: " + "; ".join(out.warnings[:2]))
    p.pattern_text, p.pattern = text, out.pattern
    if p.size not in (out.pattern.sizes or [None]):
        p.size = None
    msg = f"Pattern read ({out.method}): {out.pattern.title}."
    if out.pattern.sizes:
        msg += f" Sizes: {', '.join(out.pattern.sizes)}."
    return ToolResult(ok=True, message=msg, data={"sizes": out.pattern.sizes, "warnings": out.warnings})


def select_size(p: Project, size: str) -> ToolResult:
    if (err := _editable(p)):
        return err
    sizes = p.pattern.sizes if p.pattern else []
    if not sizes:
        return ToolResult(ok=False, message="Load a pattern with sizes first.")
    match = next((s for s in sizes if s.lower() == size.lower()), None)
    if match is None:
        return ToolResult(ok=False, message=f"Size {size!r} is not in this pattern ({', '.join(sizes)}).")
    p.size = match
    return ToolResult(ok=True, message=f"Size {match} selected.")


def get_project_status(p: Project) -> ToolResult:
    need = missing(p)
    status = {"stage": p.stage, "version": p.version, "missing": need,
              "yarn": p.yarn.label if p.yarn else None, "needle_mm": p.needle_mm,
              "gauge_sts_10cm": p.gauge_sts_10cm, "gauge_rows_10cm": p.gauge_rows_10cm,
              "pattern": p.pattern.title if p.pattern else None, "size": p.size}
    if p.stage == "knitting":
        msg = f"Knitting version {p.version}, at row {p.row_index + 1}."
    elif need:
        msg = "Still needed before generating the working pattern: " + ", ".join(need) + "."
    else:
        msg = "Everything is set — you can generate the working pattern."
    return ToolResult(ok=True, message=msg, data=status)


def generate_working_pattern(p: Project) -> ToolResult:
    if (err := _editable(p)):
        return err
    need = missing(p)
    if need:
        return ToolResult(ok=False, message="Missing before I can generate: " + ", ".join(need) + ".")
    a = adjust(p.pattern, p.size, KnitterGauge(sts_per_10cm=p.gauge_sts_10cm, rows_per_10cm=p.gauge_rows_10cm,
                                                 needle_mm=p.needle_mm))
    if not a.ok:
        return ToolResult(ok=False, message="Could not adjust the pattern: " + " ".join(a.notes))
    p.working, p.stage, p.row_index = a, "knitting", 0
    p.history.append(f"v{p.version}: generated for {p.gauge_sts_10cm:g} sts/10 cm, cast on {a.chosen_stitches}")
    return ToolResult(ok=True, message=f"Working pattern v{p.version} ready: cast on {a.chosen_stitches} sts, "
                                       f"{a.after.rows} rows. The project is now locked.",
                      data={"cast_on": a.chosen_stitches, "notes": a.notes})


def start_over(p: Project) -> ToolResult:
    if p.stage == "setup":
        return ToolResult(ok=True, message="The project is already in setup; nothing to reset.")
    lost = p.row_index
    p.history.append(f"v{p.version}: started over at row {lost + 1}")
    p.version += 1
    p.stage, p.working, p.row_index = "setup", None, 0
    return ToolResult(ok=True, message=f"Started version {p.version}: setup is editable again "
                                       f"(progress at row {lost + 1} was reset).")


TOOLS = {"set_yarn": set_yarn, "set_needles": set_needles, "set_gauge": set_gauge, "select_size": select_size,
         "get_project_status": get_project_status, "generate_working_pattern": generate_working_pattern,
         "start_over": start_over}

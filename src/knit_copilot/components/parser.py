"""Pattern parser component: written pattern text → Pattern IR, verified by the simulator.

Purpose: the core NLP step (semantic parsing) behind UC1, UC2, UC4, UC5 and UC7.
Input: ParserInput(text, mode). Output: ParserOutput(pattern | None, warnings, method, attempts).
Modes:
  llm      LLM only: code first normalises imperial units in the text, the LLM writes the IR, the simulator
           checks it; on an error the error is sent back once for repair.
  hybrid   grammar parser first (no model call); the LLM is used only when the grammar fails or the result
           does not simulate.
Model calls: yes (prompts/parser.md) in `llm`, and in `hybrid` only as a fallback. Tool calls: none.
"""

import re
import time
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from knit_copilot import kb, llm, units
from knit_copilot.config import settings
from knit_copilot.ir import Pattern
from knit_copilot.parser_grammar import MULTI, NUM, parse as grammar_parse
from knit_copilot.simulator import simulate

MAX_REPAIRS = 1


class ParserInput(BaseModel):
    text: str
    mode: Literal["llm", "hybrid"] = "hybrid"
    size: str | None = None
    model: str | None = None        # force one model without fallback (model comparison)
    time_budget_s: float | None = None   # default PARSE_TIME_BUDGET_S


class ParserOutput(BaseModel):
    pattern: Pattern | None
    warnings: list[str] = []
    method: str = ""            # grammar | llm | llm+repair | failed
    attempts: int = 0           # LLM calls made
    # last IR that was valid JSON but did not simulate (never used by the app; the evaluation scores it
    # to see how much of a reading was right, e.g. when only an out-of-scope section fails)
    unverified: Pattern | None = None

    @property
    def ok(self) -> bool:
        return self.pattern is not None


# ---------- code-side unit normalisation (the LLM never converts numbers) ----------

def _convert_multi(text: str, fn) -> str:
    vals = re.findall(NUM, text)
    conv = [str(fn(float(v))) for v in vals]
    return conv[0] if len(conv) == 1 else f"{conv[0]} ({', '.join(conv[1:])})"


def normalise_units(text: str) -> str:
    """Imperial → metric in the pattern text: lengths in inches, gauge per 4 in, US needle sizes."""
    def gauge(m: re.Match) -> str:
        sts = units.gauge_per_4in_to_10cm(float(m.group(1)))
        rows = f" and {units.gauge_per_4in_to_10cm(float(m.group(2)))} rows" if m.group(2) else ""
        return f"{sts} sts{rows} = 10 cm"
    text = re.sub(rf"({NUM}) sts(?: and ({NUM}) rows)?\s*=\s*4\s*(?:in|inches|\")", gauge, text, flags=re.I)
    text = re.sub(r"US\s*(\d+(?:\.\d+)?)", lambda m: f"{units.us_needle_to_mm(m.group(1))} mm", text)
    text = re.sub(rf"({MULTI})\s*(?:in|inches|\")(?=[\s.,;)]|$)",
                  lambda m: _convert_multi(m.group(1), units.inch_to_cm) + " cm", text)
    return text


@lru_cache
def _ops_listing() -> str:
    lines = []
    for a in kb.abbreviations().values():
        if a.is_stitch_op:
            lines.append(f"{a.id}: {', '.join(a.aliases[:4])}")
    return "\n".join(lines)


def _llm_parse(text: str, feedback: str = "", model: str | None = None, deadline: float | None = None) -> Pattern:
    messages = llm.render("parser", ops=_ops_listing(), text=text, feedback=feedback)
    return llm.chat_json(messages, schema=Pattern, model=model, fallback=model is None, deadline=deadline)


NO_ROW_GAUGE = "the pattern gives no row gauge: 'work until it measures' steps use your own row gauge"


def _check(pattern: Pattern, size: str | None) -> list[str]:
    """Simulation errors for every size. A missing row gauge is missing information, not a reading error:
    such patterns are verified with a typical row gauge (1.4 × the stitch gauge) and get a warning instead."""
    sizes = [size] if size else (pattern.sizes or [None])
    rows_g = None
    if pattern.gauge is None or not pattern.gauge.rows_per_10cm:
        rows_g = round(1.4 * pattern.gauge.sts_per_10cm, 1) if pattern.gauge else 28.0
    errors = []
    for s in sizes:
        errors += simulate(pattern, s, rows_per_10cm=rows_g).errors
    return errors


def _notes(pattern: Pattern) -> list[str]:
    from knit_copilot.ir import RepeatRowsStep
    uses_length = any(isinstance(st, RepeatRowsStep) and st.until_length_cm for pc in pattern.pieces for st in pc.steps)
    return [NO_ROW_GAUGE] if uses_length and not (pattern.gauge and pattern.gauge.rows_per_10cm) else []


def run(inp: ParserInput) -> ParserOutput:
    warnings: list[str] = []
    if inp.mode == "hybrid":
        g = grammar_parse(inp.text)
        if g.ok and not g.warnings and not _check(g.pattern, inp.size):
            return ParserOutput(pattern=g.pattern, warnings=_notes(g.pattern), method="grammar")
        warnings += [f"grammar: {w}" for w in g.warnings] or ["grammar: result does not simulate"]

    text = normalise_units(inp.text)
    feedback, attempts, last = "", 0, None
    deadline = time.monotonic() + (inp.time_budget_s or settings.parse_budget_s)
    for attempt in range(1 + MAX_REPAIRS):
        attempts += 1
        try:
            pattern = _llm_parse(text, feedback, inp.model, deadline)
        except llm.LLMConfigError as e:          # no API key: retrying cannot help
            warnings.append(f"llm: {e}")
            break
        except llm.LLMTimeout:
            warnings.append(f"llm: stopped after {inp.time_budget_s or settings.parse_budget_s:.0f} s "
                            f"(free models busy or slow); try again later or use hybrid mode")
            break
        except (ValueError, RuntimeError) as e:
            warnings.append(f"llm: {e}")
            feedback = f"\nYour previous answer was not valid IR JSON ({e}). Return the corrected JSON."
            continue
        errors = _check(pattern, inp.size)
        if not errors:
            return ParserOutput(pattern=pattern, warnings=warnings + _notes(pattern),
                                method="llm" if attempt == 0 else "llm+repair", attempts=attempts)
        last = pattern
        warnings.append(f"llm: simulation error: {errors[0]}")
        feedback = (f"\nYour previous IR does not simulate: {errors[0]}. Check repeat stop rules, op counts and "
                    f"which rows are repeated, then return the corrected JSON.")
    return ParserOutput(pattern=None, warnings=warnings, method="failed", attempts=attempts, unverified=last)

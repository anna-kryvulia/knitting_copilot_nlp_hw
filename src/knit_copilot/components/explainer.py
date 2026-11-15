"""Explainer component (UC1): Pattern IR → plain-English explanation grounded in a code-built fact sheet.

Purpose: explain a pattern (or one part of it) to a beginner, citing KB abbreviations.
Input: ExplainerInput(pattern, size, focus). Output: ExplainerOutput(text, citations, violations, attempts).
Model calls: yes (prompts/explainer.md), up to 1 + MAX_REPAIRS. Tool calls: none.

Grounding check (code): every standalone number in the answer must appear in the fact sheet, and every
[citation] must be an abbreviation the pattern uses. Violations are sent back once for repair; any that
remain are returned so the UI can show a warning.
"""

import re
import time

from pydantic import BaseModel

from knit_copilot import facts as factsheet
from knit_copilot import kb, llm
from knit_copilot.ir import Pattern

MAX_REPAIRS = 1
# "[k2tog]" or, as models sometimes write it, "[k2tog: knit two together]"
CITATION = re.compile(r"\[([a-z0-9_]+)(?::[^\]]*)?\]")
# tokens like k2tog, p40, c6b, 2/2: numbers inside abbreviations are not checked as quantities
ABBREV_TOKEN = re.compile(r"\b[a-z]+\d+[a-z0-9]*\b|\b\d+/\d+\b|\[[a-z0-9_]+(?::[^\]]*)?\]", re.I)


class ExplainerInput(BaseModel):
    pattern: Pattern
    size: str | None = None
    focus: str | None = None               # e.g. "Row 3" or a user question about one part
    rows_per_10cm: float | None = None     # knitter's row gauge, if known
    time_budget_s: float = 90


class ExplainerOutput(BaseModel):
    text: str
    citations: list[str] = []
    violations: list[str] = []
    attempts: int = 0
    facts: str = ""

    @property
    def grounded(self) -> bool:
        return not self.violations


ANY_BRACKET = re.compile(r"\[([^\]\n]{1,80})\]")


def check(text: str, sheet: factsheet.FactSheet) -> list[str]:
    """Numbers not in the fact sheet, citations not used by the pattern, and citations that use a name
    instead of an id ("[yarn over: …]" instead of "[yo]")."""
    problems = []
    names = {kb.abbreviations()[i].name.lower(): i for i in sheet.abbreviations}
    for inner in ANY_BRACKET.findall(text):
        head = inner.split(":")[0].strip().lower()
        if CITATION.fullmatch(f"[{inner}]") is None and head in names:
            problems.append(f"cite abbreviations by id: use [{names[head]}] instead of [{head}]")
    cited = CITATION.findall(text)
    for c in dict.fromkeys(cited):
        if c not in sheet.abbreviations:
            problems.append(f"citation [{c}] is not an abbreviation used in this pattern")
    plain = ABBREV_TOKEN.sub(" ", text)
    for n in dict.fromkeys(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", plain)):
        if float(n) not in sheet.numbers:
            problems.append(f"number {n} is not in the fact sheet")
    return problems


def run(inp: ExplainerInput) -> ExplainerOutput:
    sheet = factsheet.build(inp.pattern, inp.size, inp.rows_per_10cm)
    focus_rule = ("- The user asks about one part only: explain that part in detail and skip the per-step sections "
                  "for the rest (keep the overview to one sentence).") if inp.focus else ""
    focus = f"\nUSER QUESTION / FOCUS: {inp.focus}" if inp.focus else ""
    deadline = time.monotonic() + inp.time_budget_s
    feedback, text, problems, attempts = "", "", [], 0
    for _ in range(1 + MAX_REPAIRS):
        attempts += 1
        messages = llm.render("explainer", facts=sheet.as_text(), focus=focus, feedback=feedback,
                              focus_rule=focus_rule)
        out = llm.chat(messages, max_tokens=6000, temperature=0.2, deadline=deadline)
        text = (out["content"] or "").strip()
        problems = check(text, sheet)
        if not problems:
            break
        feedback = ("\nYOUR PREVIOUS ANSWER HAD PROBLEMS — fix them and answer again:\n- "
                    + "\n- ".join(problems[:10]))
    return ExplainerOutput(text=text, citations=list(dict.fromkeys(CITATION.findall(text))), violations=problems,
                           attempts=attempts, facts=sheet.as_text())

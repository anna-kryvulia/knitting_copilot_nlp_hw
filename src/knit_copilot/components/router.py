"""Router: classify a chat message into one of the intents of docs/CONVENTIONS.md.

Purpose: decide which component answers (setup agent, explainer, yarn advisor, KB, charts, tracker …).
Input: RouterInput(text, stage, has_pattern, mode). Output: RouterOutput(intent, confidence, method).
Modes:
  rules   high-precision patterns only (no model call); returns "unknown" when no rule fires
  llm     the LLM classifies every message (prompts/router.md)
  hybrid  rules first, the LLM only when no rule fires (default)
Model calls: in llm mode always, in hybrid mode only for messages no rule covers.

The rules were written from the intent definitions, not fitted to the eval messages.
"""

from __future__ import annotations

import re
import time
from typing import Literal

from pydantic import BaseModel

from knit_copilot import kb, llm

INTENTS = ["setup", "adjust_pattern", "explain", "yarn_advice", "abbreviation_lookup", "knitting_question",
           "chart", "tracker", "validate", "out_of_scope", "smalltalk"]
Intent = Literal["setup", "adjust_pattern", "explain", "yarn_advice", "abbreviation_lookup", "knitting_question",
                 "chart", "tracker", "validate", "out_of_scope", "smalltalk", "unknown"]


class RouterInput(BaseModel):
    text: str
    stage: str = "setup"
    has_pattern: bool = False
    mode: Literal["rules", "llm", "hybrid"] = "hybrid"


class RouterOutput(BaseModel):
    intent: Intent
    confidence: float
    method: str            # rule:<name> | llm | none


class _LLMIntent(BaseModel):
    intent: Literal["setup", "adjust_pattern", "explain", "yarn_advice", "abbreviation_lookup", "knitting_question",
                    "chart", "tracker", "validate", "out_of_scope", "smalltalk"]
    confidence: float = 0.5


# (name, intent, pattern) — ordered: the first match wins
RULES: list[tuple[str, str, re.Pattern]] = [
    ("greeting", "smalltalk", re.compile(r"^\s*(hi|hello|hey|thanks?|thank you|bye|good (morning|evening|night)|ok(ay)?)\b[\s!.,]*"
                                         r"(that helped( a lot)?|so much)?[\s!.]*$", re.I)),
    ("crochet", "out_of_scope", re.compile(r"\b(crochet|sew(ing)?|zipper|fair ?isle|colou?rwork|intarsia|short rows?)\b", re.I)),
    ("chart", "chart", re.compile(r"\b(chart|diagram|grid)\b", re.I)),
    ("validate", "validate", re.compile(r"\b(mistake|errat|proofread|validate)\w*\b.*\b(pattern|round|row)\b|"
                                        r"\b(validate|proofread)\b", re.I)),
    ("tracker", "tracker", re.compile(r"^\s*(next|previous|prev) (row|round|rnd)\s*$|\bwhere (was|am) i\b|"
                                      r"\b(finished|done with|mark) (row|round|rnd) ?\d+|\brows? (are )?left\b|"
                                      r"\bwhich repeat am i\b", re.I)),
    ("adjust", "adjust_pattern", re.compile(r"\b(recalculate|resize|adjust|rewrite|generate)\b.*\b(gauge|tension|pattern|"
                                            r"swatch|yarn|version)\b", re.I)),
    ("numbers", "setup", re.compile(r"\b\d+(\.\d+)?\s*(mm|sts?|stitches)\b.*$|\bUS \d+\b|\bsize (xs|s|m|l|xl|\w+/\w+)\b",
                                    re.I)),
]
WHAT_IS = re.compile(r"^\s*(what('s| is| does)?( the meaning of| a)?|meaning of|define)\s+(?P<term>[\w/&\- ]{1,20}?)"
                     r"(\s+mean)?\s*\??\s*$", re.I)


def _rules(text: str) -> RouterOutput | None:
    t = text.strip()
    a = kb.lookup(t.strip(" ?!."))
    if a is not None and len(t) <= 20:                                 # "ssk", "m1l?", "wyib"
        return RouterOutput(intent="abbreviation_lookup", confidence=0.95, method="rule:bare_abbreviation")
    m = WHAT_IS.match(t)
    if m and kb.lookup(m.group("term")):
        return RouterOutput(intent="abbreviation_lookup", confidence=0.95, method="rule:what_is")
    notation = re.search(r"\b(rep|k\d+|p\d+|k2tog|ssk|yo|psso)\b|\*", t, re.I)   # a pasted instruction
    for name, intent, pat in RULES:
        if name == "numbers" and notation:
            continue
        if pat.search(t):
            return RouterOutput(intent=intent, confidence=0.9, method=f"rule:{name}")
    return None


def run(inp: RouterInput) -> RouterOutput:
    if inp.mode != "llm":
        hit = _rules(inp.text)
        if hit or inp.mode == "rules":
            return hit or RouterOutput(intent="unknown", confidence=0.0, method="none")
    msgs = llm.render("router", text=inp.text, stage=inp.stage, has_pattern="yes" if inp.has_pattern else "no")
    out = llm.chat_json(msgs, schema=_LLMIntent, deadline=time.monotonic() + 45)
    return RouterOutput(intent=out.intent, confidence=out.confidence, method="llm")

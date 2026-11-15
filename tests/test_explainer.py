import json

from knit_copilot import facts
from knit_copilot.components import explainer
from knit_copilot.ir import Pattern
from knit_copilot.parser_grammar import parse

HAT = """Hat
CO 88 sts.
Join to work in the round.
Rnd 1: *k2, p2; rep from * to end.
Repeat Rnd 1 3 more times.
Rnd 2: *k6, k2tog; rep from * to end. (77 sts)
BO all sts.
"""


def _sheet():
    return facts.build(parse(HAT).pattern)


def test_fact_sheet_has_counts_repeats_and_definitions():
    text = _sheet().as_text()
    assert "Cast on 88 stitches" in text and "(k2, p2) ×22" in text and "88 → 77 (-11 stitches)" in text
    assert "3 more repeats" in text and "[k2tog] knit two together" in text


def test_check_flags_invented_numbers_and_citations():
    sheet = _sheet()
    assert explainer.check("Cast on 88 stitches, then work (k2, p2) ×22 [k] [p].", sheet) == []
    problems = explainer.check("You will need 250 m of yarn [ssk].", sheet)
    assert any("250" in p for p in problems) and any("[ssk]" in p for p in problems)


def test_repair_loop(monkeypatch):
    answers = iter(["Knit 999 rounds [k].", "## Overview\nCast on 88 stitches [k]."])
    monkeypatch.setattr(explainer.llm, "chat", lambda *a, **k: {"content": next(answers)})
    out = explainer.run(explainer.ExplainerInput(pattern=parse(HAT).pattern))
    assert out.grounded and out.attempts == 2 and out.citations == ["k"]


def test_citation_with_inline_definition():
    sheet = _sheet()
    text = "Work [k2tog: knit two together] and [k: knit]."
    assert explainer.check(text, sheet) == [] and explainer.CITATION.findall(text) == ["k2tog", "k"]


def test_citation_by_name_is_flagged():
    problems = explainer.check("Then [knit two together: work two as one].", _sheet())
    assert problems == ["cite abbreviations by id: use [k2tog] instead of [knit two together]"]

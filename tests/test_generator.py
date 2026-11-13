import json
import random
import re

import pytest

from knit_copilot.data.generator import STYLES, make_cases, render
from knit_copilot.data.templates import TEMPLATES
from knit_copilot.ir import Pattern
from knit_copilot.simulator import simulate


@pytest.mark.parametrize("template", sorted(TEMPLATES))
@pytest.mark.parametrize("style", STYLES)
def test_every_template_renders_in_every_style(template, style):
    rng = random.Random(1)
    text, gold = render(TEMPLATES[template](rng), style, rng)
    assert "Row" in text or "Rnd" in text
    for size in gold.sizes or [None]:
        sim = simulate(gold, size)
        assert sim.ok and not sim.count_mismatches()
    imperial_length = re.search(r"\d+(\.\d+)? in\b", text)
    if style == "imperial":
        assert imperial_length and " cm" not in text
    else:
        assert not imperial_length and "US " not in text


def test_cases_are_reproducible_and_gold_is_consistent():
    a, b = make_cases(18, seed=3), make_cases(18, seed=3)
    assert json.dumps(a) == json.dumps(b)
    for c in a:
        gold = Pattern.model_validate(c["expected"]["ir"])
        sim = simulate(gold, c["expected"]["size"])
        assert len(sim.rows) == c["expected"]["total_rows"]
        assert sim.final_count == c["expected"]["final_count"]
    assert {c["split"] for c in a} == {"dev", "test"}

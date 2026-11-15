from knit_copilot.display import describe_row, row_lines
from knit_copilot.ir import Pattern, Row
from knit_copilot.parser_grammar import parse
from knit_copilot.simulator import simulate


def _row(ops):
    return Row.model_validate({"label": "Row 1", "side": "RS", "ops": ops})


def test_describe_star_repeat_with_computed_count():
    row = _row([{"op": "k", "n": 2},
                {"repeat": [{"op": "yo"}, {"op": "k2tog"}, {"op": "k", "n": 3}], "until": {"remaining": 2}},
                {"op": "k", "n": 2}])
    assert describe_row(row, 34) == "k2, (yo, k2tog, k3) ×6, k2"


def test_describe_to_end_and_nested_repeats():
    assert describe_row(_row([{"repeat": [{"op": "k"}], "until": {"remaining": 0}}]), 88) == "k88"
    fan = _row([{"op": "k"}, {"repeat": [{"repeat": [{"op": "k2tog"}], "times": 3},
                                         {"repeat": [{"op": "yo"}, {"op": "k"}], "times": 6},
                                         {"repeat": [{"op": "k2tog"}], "times": 3}], "until": {"remaining": 1}},
                {"op": "k"}])
    assert describe_row(fan, 38) == "k1, (k2tog ×3, (yo, k1) ×6, k2tog ×3) ×2, k1"


HAT = """Hat
CO 88 sts.
Join to work in the round.
Rnd 1: *k2, p2; rep from * to end.
Repeat Rnd 1 3 more times.
Rnd 2: K to end.
BO all sts.
"""


def test_grouped_lines_and_time_counter():
    p = parse(HAT).pattern
    sim = simulate(p)
    grouped = row_lines(p, sim)
    assert [g.rows for g in grouped] == ["Rnd 1", "Rnds 2–4", "Rnd 5", "Rnd 6"]
    assert grouped[1].instruction == "Rnd 1 × 3 more" and grouped[1].worked_as == "Rnd 1: (k2, p2) ×22"
    flat = row_lines(p, sim, grouped=False)
    assert flat[0].instruction == "Rnd 1 (time 1 of 4)" and flat[3].instruction == "Rnd 1 (time 4 of 4)"
    assert flat[-1].worked_as == "bind off 88 sts"
    assert grouped[0].instruction == "Rnd 1"          # no "time 1 of 4" in the grouped view


def test_label_range_single_and_many():
    from knit_copilot.display import _label_range
    assert _label_range(["Rnd 1"]) == "Rnd 1" and _label_range(["Row 1", "Row 2", "Row 3"]) == "Rows 1–3"

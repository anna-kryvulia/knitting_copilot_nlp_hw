from knit_copilot.ir import Pattern, Row
from knit_copilot.simulator import expand_row, simulate


def _pattern(cast_on, steps, sizes=None, construction="flat", rows_gauge=30):
    return Pattern.model_validate({
        "title": "t", "construction": construction, "sizes": sizes or [],
        "gauge": {"sts_per_10cm": 22, "rows_per_10cm": rows_gauge},
        "pieces": [{"cast_on": cast_on, "steps": steps}]})


LACE_ROW = {"label": "Row 1", "side": "RS", "ops": [
    {"op": "k", "n": 2},
    {"repeat": [{"op": "yo"}, {"op": "k2tog"}, {"op": "k", "n": 3}], "until": {"remaining": 2}},
    {"op": "k", "n": 2}]}


def test_lace_row_keeps_count():
    ops, end = expand_row(Row.model_validate(LACE_ROW), 34)    # 2 + 6 x 5 + 2
    assert end == 34
    assert ops[:4] == ["k", "k", "yo", "k2tog"] and ops.count("yo") == 6


def test_repeat_that_does_not_fit_is_reported():
    res = simulate(_pattern(33, [{"type": "rows", "rows": [LACE_ROW]}]))
    assert not res.ok and "does not fit" in res.errors[0]


def test_decreases_and_stated_count_mismatch():
    row = {"label": "Rnd 1", "side": "round", "stated_count": 40,
           "ops": [{"repeat": [{"op": "k", "n": 6}, {"op": "k2tog"}], "until": {"remaining": 0}}]}
    res = simulate(_pattern(48, [{"type": "rows", "rows": [row]}], construction="round"))
    assert res.ok and res.final_count == 42
    assert [r.label for r in res.count_mismatches()] == ["Rnd 1"]


def test_repeat_rows_until_length_and_bind_off():
    rows = [{"label": "Row 1", "side": "RS", "ops": [{"op": "k", "n": 20}]},
            {"label": "Row 2", "side": "WS", "ops": [{"op": "p", "n": 20}]}]
    res = simulate(_pattern(20, [{"type": "rows", "rows": rows},
                                 {"type": "repeat_rows", "rows_ref": ["Row 1", "Row 2"], "until_length_cm": 10},
                                 {"type": "bind_off"}]))
    assert res.ok
    assert len(res.rows) == 31          # 30 rows for 10 cm at 30 rows/10 cm, whole repeats -> 30, + bind off
    assert res.rows[-1].label == "Bind off" and res.final_count == 0


def test_knitter_row_gauge_changes_row_count():
    rows = [{"label": "Row 1", "side": "RS", "ops": [{"op": "k", "n": 10}]}]
    p = _pattern(10, [{"type": "rows", "rows": rows},
                      {"type": "repeat_rows", "rows_ref": ["Row 1"], "until_length_cm": 10}])
    assert len(simulate(p).rows) == 30
    assert len(simulate(p, rows_per_10cm=20).rows) == 20


def test_multi_size_values():
    rows = [{"label": "Row 1", "side": "RS", "ops": [
        {"op": "k", "n": {"S": 2, "L": 4}}, {"op": "kfb"}, {"op": "k", "n": {"S": 7, "L": 11}}]}]
    p = _pattern({"S": 10, "L": 16}, [{"type": "rows", "rows": rows}], sizes=["S", "L"])
    assert simulate(p, "S").final_count == 11
    assert simulate(p, "L").final_count == 17


def test_row_with_unworked_stitches_and_unknown_op():
    short = {"label": "Row 1", "side": "RS", "ops": [{"op": "k", "n": 8}]}
    assert "unworked" in simulate(_pattern(10, [{"type": "rows", "rows": [short]}])).errors[0]
    bad = {"label": "Row 1", "side": "RS", "ops": [{"op": "zz9", "n": 10}]}
    assert "Unknown stitch operation" in simulate(_pattern(10, [{"type": "rows", "rows": [bad]}])).errors[0]


def test_cable_and_markers_keep_count():
    row = {"label": "Row 1", "side": "RS", "ops": [
        {"op": "p", "n": 2}, {"op": "pm"}, {"op": "c6b"}, {"op": "sm"}, {"op": "p", "n": 2}]}
    res = simulate(_pattern(10, [{"type": "rows", "rows": [row]}]))
    assert res.ok and res.final_count == 10


def test_repeat_rows_until_count_bias_dishcloth():
    inc = {"label": "Inc row", "side": "RS", "ops": [
        {"op": "k", "n": 2}, {"op": "yo"}, {"repeat": [{"op": "k"}], "until": {"remaining": 0}}]}
    dec = {"label": "Dec row", "side": "RS", "ops": [
        {"op": "k", "n": 1}, {"op": "k2tog"}, {"op": "yo"}, {"op": "k2tog"},
        {"repeat": [{"op": "k"}], "until": {"remaining": 0}}]}
    p = _pattern(4, [{"type": "rows", "rows": [inc]},
                     {"type": "repeat_rows", "rows_ref": ["Inc row"], "until_count": 10},
                     {"type": "rows", "rows": [dec]},
                     {"type": "repeat_rows", "rows_ref": ["Dec row"], "until_count": 4},
                     {"type": "bind_off"}])
    res = simulate(p)
    assert res.ok, res.errors
    assert [r.end_count for r in res.rows[:6]] == [5, 6, 7, 8, 9, 10]
    assert res.rows[-2].end_count == 4


def test_repeat_rows_until_count_that_moves_away_is_an_error():
    inc = {"label": "Row 1", "side": "RS", "ops": [{"op": "kfb"}, {"repeat": [{"op": "k"}], "until": {"remaining": 0}}]}
    p = _pattern(10, [{"type": "rows", "rows": [inc]},
                      {"type": "repeat_rows", "rows_ref": ["Row 1"], "until_count": 4}])
    assert "never reaches" in simulate(p).errors[0]

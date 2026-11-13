import pytest
from pydantic import ValidationError

from knit_copilot import units
from knit_copilot.ir import Op, Pattern, Repeat, resolve


@pytest.mark.parametrize("value,expected", [("US 7", 4.5), ("7", 4.5), (10.5, 6.5), ("us 10.50", 6.5), ("1.5", 2.5)])
def test_us_needle_to_mm(value, expected):
    assert units.us_needle_to_mm(value) == expected


def test_unknown_needle_size():
    with pytest.raises(KeyError):
        units.us_needle_to_mm("US 12")


def test_lengths_and_gauge():
    assert units.inch_to_cm(5.5) == 14.0
    assert units.yards_to_m(175) == 160
    assert units.gauge_per_4in_to_10cm(24) == 23.6
    assert units.gauge_to_per_10cm(24, 4) == 23.6
    assert units.gauge_to_per_10cm(22, 10, unit="cm") == 22.0
    assert units.fraction_to_float("5 ½") == 5.5


def test_resolve_sized_values():
    assert resolve(40, None) == 40
    assert resolve({"S": 40, "M": 46}, "M") == 46
    assert resolve({"one": 30}, None) == 30
    with pytest.raises(ValueError):
        resolve({"S": 40, "M": 46}, None)


def test_repeat_needs_exactly_one_stop_rule():
    with pytest.raises(ValidationError):
        Repeat(repeat=[Op(op="k")])
    with pytest.raises(ValidationError):
        Repeat(repeat=[Op(op="k")], times=2, until={"remaining": 0})


def test_pattern_parses_conventions_example():
    p = Pattern.model_validate({
        "title": "Simple Lace Scarf", "construction": "flat",
        "gauge": {"sts_per_10cm": 22, "rows_per_10cm": 30, "needle_mm": 4.0},
        "pieces": [{"cast_on": 32, "steps": [
            {"type": "rows", "rows": [
                {"label": "Row 1", "side": "RS", "ops": [
                    {"op": "k", "n": 2},
                    {"repeat": [{"op": "yo"}, {"op": "k2tog"}, {"op": "k", "n": 3}], "until": {"remaining": 2}},
                    {"op": "k", "n": 2}], "stated_count": 32},
                {"label": "Row 2", "side": "WS", "ops": [{"op": "p", "n": 32}]}]},
            {"type": "repeat_rows", "rows_ref": ["Row 1", "Row 2"], "until_length_cm": 150},
            {"type": "bind_off"}]}]})
    assert isinstance(p.pieces[0].steps[0].rows[0].ops[1], Repeat)
    assert set(p.rows_by_label()) == {"Row 1", "Row 2"}

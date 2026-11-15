import json

from knit_copilot.components import parser
from knit_copilot.ir import Pattern
from knit_copilot.parser_grammar import parse, parse_items
from knit_copilot.simulator import simulate

SIMPLE = """Test Scarf
CO 26 sts.
Row 1 (RS): K2, *p2, k2; rep from * to end.
Row 2 (WS): P2, *k2, p2; rep from * to end.
Repeat Rows 1 and 2 3 more times.
BO all sts in pattern.
"""


def test_grammar_parses_simple_pattern():
    r = parse(SIMPLE)
    assert r.ok and not r.warnings
    sim = simulate(r.pattern)
    assert sim.ok and len(sim.rows) == 2 + 6 + 1


def test_grammar_items_variants():
    assert parse_items("(k2tog) 3 times", []) == [{"repeat": [{"op": "k2tog"}], "times": 3}]
    assert parse_items("K2, *yo, k2tog, k3; rep from * 2 more times", [])[1]["times"] == 3
    assert parse_items("Knit 2 together to the end of the round", []) == [{"repeat": [{"op": "k2tog"}], "until": {"remaining": 0}}]
    assert parse_items("k2 (3, 4)", ["S", "M", "L"]) == [{"op": "k", "n": {"S": 2, "M": 3, "L": 4}}]
    assert parse_items("yfwd, skpo", []) == [{"op": "yo"}, {"op": "skp"}]


def test_grammar_reports_unknown_abbreviation():
    r = parse("X\nCO 10 sts.\nRow 1 (RS): k5, zz9, k5.\n")
    assert any("zz9" in w for w in r.warnings)


def test_normalise_units_is_done_by_code():
    t = parser.normalise_units("Needles: US 7\nGauge: 20 sts and 28 rows = 4 in.\nuntil piece measures 15 (16, 17) in from")
    assert "4.5 mm" in t and "19.7 sts and 27.6 rows = 10 cm" in t and "38.1 (40.6, 43.2) cm" in t


def test_hybrid_uses_grammar_without_model_call(monkeypatch):
    monkeypatch.setattr(parser, "_llm_parse", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    out = parser.run(parser.ParserInput(text=SIMPLE, mode="hybrid"))
    assert out.ok and out.method == "grammar" and out.attempts == 0


def test_llm_repair_loop_sends_simulator_error_back(monkeypatch):
    good = parse(SIMPLE).pattern
    bad = Pattern.model_validate(json.loads(good.model_dump_json()) | {})
    bad.pieces[0].cast_on = 24            # does not fit the 2x2 rib -> simulation error
    calls = []

    def fake(text, feedback="", model=None, deadline=None):
        calls.append(feedback)
        return bad if len(calls) == 1 else good
    monkeypatch.setattr(parser, "_llm_parse", fake)
    out = parser.run(parser.ParserInput(text=SIMPLE, mode="llm"))
    assert out.ok and out.method == "llm+repair" and out.attempts == 2
    assert "does not simulate" in calls[1]


def test_time_budget_stops_llm_parsing(monkeypatch):
    from knit_copilot import llm

    def slow(*a, **k):
        raise llm.LLMTimeout("budget")
    monkeypatch.setattr(parser, "_llm_parse", slow)
    out = parser.run(parser.ParserInput(text=SIMPLE, mode="llm", time_budget_s=5))
    assert not out.ok and out.attempts == 1 and "stopped after 5 s" in out.warnings[0]


def test_chat_deadline_is_enforced(monkeypatch):
    import time as _t

    from knit_copilot import llm

    class SlowCompletions:
        def create(self, **kw):
            _t.sleep(3)

    class FakeClient:
        chat = type("C", (), {"completions": SlowCompletions()})()
    monkeypatch.setattr(llm, "client", lambda: FakeClient())
    t0 = _t.monotonic()
    try:
        llm.chat([{"role": "user", "content": "x"}], use_cache=False, fallback=False, deadline=_t.monotonic() + 1.5)
    except (llm.LLMTimeout, RuntimeError):
        pass
    assert _t.monotonic() - t0 < 2.5


def test_grammar_marker_stops_and_named_rows():
    assert parse_items("k to 2 sts before m", []) == [{"repeat": [{"op": "k"}], "until": {"remaining": 2, "marker": True}}]
    assert parse_items("knit to the marker, slip marker", []) == [
        {"repeat": [{"op": "k"}], "until": {"remaining": 0, "marker": True}}, {"op": "sm"}]
    star = parse_items("*k to 2 sts before m, k2tog, sm; rep from * to end", [])[0]
    assert star["until"] == {"remaining": 0} and star["repeat"][0]["until"]["marker"] is True
    text = """Hat
CO 24 sts.
Join to work in the round.
Set-up rnd: *k8, pm; rep from * 1 more time, k8.
Dec rnd: *k to 2 sts before m, k2tog, sm; rep from * to end. (21 sts)
Knit rnd: K to end.
Repeat Dec rnd and Knit rnd until 12 sts remain.
BO all sts.
"""
    r = parse(text)
    assert r.ok and not r.warnings and r.pattern.construction == "round"
    sim = simulate(r.pattern)
    assert sim.ok and [x.end_count for x in sim.rows if x.label == "Dec rnd"][-1] == 12


def test_grammar_warns_instead_of_skipping_unknown_named_rows():
    r = parse("X\nCO 10 sts.\nFancy bit: k5, zz9, k5.\n")
    assert r.warnings

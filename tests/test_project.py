"""Business rules BR1–BR3 (project stages) and the row tracker."""
from knit_copilot import db, project, tracker

HAT = """Hat
Sizes: S (M)
Needles: 4 mm
Gauge: 21 sts and 28 rows = 10 cm in stockinette.
CO 88 (96) sts.
Join to work in the round.
Rnd 1: *k2, p2; rep from * to end.
Repeat Rnd 1 3 more times.
Rnd 2: *k6, k2tog; rep from * to end.
BO all sts.
"""


def _ready():
    p = project.new_project("hat")
    assert project.set_pattern(p, HAT).ok
    return p


def test_generate_needs_pattern_size_gauge_needles():
    p = _ready()
    assert set(project.missing(p)) == {"size", "gauge", "needles"}
    assert not project.generate_working_pattern(p).ok
    assert project.select_size(p, "m").ok and p.size == "M"
    assert project.set_gauge(p, 18, 24, over=4, unit="in").ok and p.gauge_sts_10cm == 17.7   # code converts
    assert project.set_needles(p, 8, "us").ok and p.needle_mm == 5.0
    assert project.missing(p) == [] and project.generate_working_pattern(p).ok and p.stage == "knitting"


def test_locked_project_refuses_changes_until_start_over():
    p = _ready()
    project.select_size(p, "S"); project.set_gauge(p, 21, 28); project.set_needles(p, 4)
    project.generate_working_pattern(p)
    r = project.set_needles(p, 5)
    assert not r.ok and "locked" in r.message and p.needle_mm == 4.0
    p.row_index = 3
    assert project.start_over(p).ok and p.stage == "setup" and p.version == 2 and p.row_index == 0
    assert project.set_needles(p, 5).ok


def test_yarn_linking_and_ambiguity():
    p = project.new_project()
    assert project.set_yarn(p, "gazal baby wool").ok and p.yarn.yarn_id
    r = project.set_yarn(p, "Jeans")
    assert not r.ok and len(r.data["candidates"]) == 2


def test_tracker_moves_and_reports_counts():
    p = _ready()
    project.select_size(p, "S"); project.set_gauge(p, 21, 28); project.set_needles(p, 4)
    project.generate_working_pattern(p)
    v = tracker.view(p)
    assert v.index == 0 and v.label == "Rnd 1" and v.time_of == "time 1 of 4" and v.end_count == 88
    v = tracker.next_row(p, 4)
    assert v.label == "Rnd 2" and v.end_count == 77 and v.instruction == "(k6, k2tog) ×11"
    assert tracker.next_row(p, 99).label == "Bind off" and tracker.prev_row(p).label == "Rnd 2"


def test_db_roundtrip(tmp_path):
    p = _ready()
    db.save(p, tmp_path / "t.db")
    q = db.load(p.id, tmp_path / "t.db")
    assert q.pattern.title == p.pattern.title and db.list_projects(tmp_path / "t.db")[0][0] == p.id


def test_setup_agent_executes_tool_calls(monkeypatch):
    import json as _json
    from knit_copilot.components import setup_agent
    answers = iter([
        {"content": "", "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "set_needles", "arguments": _json.dumps({"size": 8, "system": "us"})}},
            {"id": "2", "type": "function", "function": {"name": "set_gauge", "arguments": _json.dumps({"stitches": 18, "over": 4, "unit": "in"})}}]},
        {"content": "Done: 5 mm needles and 17.7 sts per 10 cm.", "tool_calls": None}])
    monkeypatch.setattr(setup_agent.llm, "chat", lambda *a, **k: next(answers))
    p = _ready()
    out = setup_agent.run(setup_agent.SetupInput(turns=["US 8 needles, 18 sts over 4 inches"], project=p))
    assert [c.tool for c in out.calls] == ["set_needles", "set_gauge"] and all(c.ok for c in out.calls)
    assert p.needle_mm == 5.0 and p.gauge_sts_10cm == 17.7 and out.reply.startswith("Done")

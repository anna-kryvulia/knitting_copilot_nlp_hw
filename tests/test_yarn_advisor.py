from knit_copilot.components import yarn_advisor as ya
from knit_copilot.components import yarn_linker as yl


def _row(brand, name):
    return next(y for y in yl.yarns() if y["brand"] == brand and y["name"] == name)


def test_facts_from_label_and_fibre_adjustment():
    f = ya.yarn_facts(_row("YarnArt", "Jeans"))
    assert f.cyc_category == 2 and f.needle_mm == (3.5, 3.5) and f.suggested_needle_mm == 3.25
    assert "fibre:cotton" in f.citations and not f.warn_gauge


def test_flagged_gauge_warns_and_fibre_only_uses_cyc():
    assert ya.yarn_facts(_row("Nako", "Pirlanta")).warn_gauge
    f = ya.yarn_facts(None, "wool", "Worsted")
    assert f.needle_mm == (4.5, 5.5) and f.gauge_sts_10cm == (16, 20) and "yarn:" not in " ".join(f.citations)


def test_check_and_ambiguous_yarn(monkeypatch):
    f = ya.yarn_facts(_row("YarnArt", "Jeans"))
    assert ya.check("Use 3.5 mm needles [fibre:cotton] [yarn:9876].", f) == []
    assert ya.check("Use 7 mm needles [fibre:wool].", f)
    assert ya.run(ya.AdvisorInput(yarn_text="Baby Wool")).status == "ambiguous"


def test_swatch_warning_is_added_by_code_when_the_model_forgets(monkeypatch):
    from knit_copilot.components import yarn_advisor as Y
    monkeypatch.setattr(Y.llm, "chat", lambda *a, **k: {"content": "It is machine washable [yarn:107059]."})
    out = Y.run(Y.AdvisorInput(yarn_id=107059, question="How do I wash it?"))
    assert "swatch" in out.answer.lower()

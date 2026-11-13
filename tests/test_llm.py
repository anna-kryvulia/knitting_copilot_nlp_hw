from pydantic import BaseModel

from knit_copilot.llm import _extract_json, load_prompt


class Intent(BaseModel):
    intent: str


def test_extract_json_from_fenced_block():
    assert _extract_json('Sure!\n```json\n{"intent": "balance"}\n```') == {"intent": "balance"}


def test_extract_json_with_leading_prose():
    assert Intent.model_validate(_extract_json('Here it is: {"intent": "leave_request"}')).intent == "leave_request"


def test_load_prompt_sections(tmp_path, monkeypatch):
    import dataclasses

    from knit_copilot import llm
    (tmp_path / "demo.md").write_text("# demo\n## System\nBe brief.\n## User template\nQ: {q}\n")
    monkeypatch.setattr(llm, "settings", dataclasses.replace(llm.settings, prompts_dir=tmp_path))
    p = load_prompt("demo")
    assert p["system"] == "Be brief." and p["user template"] == "Q: {q}"


def test_render_real_prompts():
    from knit_copilot import llm
    from knit_copilot.components import parser
    msgs = llm.render("parser", ops=parser._ops_listing(), text="CO 10 sts.", feedback="")
    assert '{"type": "rows"' in msgs[0]["content"] and "CO 10 sts." in msgs[1]["content"]
    msgs = llm.render("explainer", facts="F", focus="", feedback="", focus_rule="- RULE")
    assert "- RULE" in msgs[0]["content"] and "{focus_rule}" not in msgs[0]["content"]

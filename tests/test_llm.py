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

"""Setup agent: fills the project from chat through LLM tool calls (docs/CONVENTIONS.md § Setup tools).

Purpose: "I'm using YarnArt Jeans on 3.5 mm needles, my swatch is 24 sts per 10 cm" → set_yarn, set_needles,
set_gauge. The LLM only chooses tools and copies the user's numbers/units; project.py converts and validates.
Input: SetupInput(turns, project). Output: SetupOutput(reply, calls made, tool results).
Model calls: yes (prompts/setup_agent.md), up to MAX_ROUNDS per user turn. Tool calls: project.TOOLS.
"""

from __future__ import annotations

import json
import time

from pydantic import BaseModel

from knit_copilot import llm, project
from knit_copilot.project import Project

MAX_ROUNDS = 3

TOOL_SPECS = [
    {"type": "function", "function": {"name": "set_yarn", "description": "Set the project's yarn: a yarn name as the user wrote it, or fibre and weight when no name is given.",
     "parameters": {"type": "object", "properties": {
         "name": {"type": ["string", "null"], "description": "Yarn name as written, e.g. 'YarnArt Jeans'"},
         "fibre": {"type": ["string", "null"], "description": "Main fibre, e.g. 'merino', 'cotton'"},
         "weight": {"type": ["string", "null"], "description": "Weight, e.g. 'DK', 'Sport', 'Aran'"}}}}},
    {"type": "function", "function": {"name": "set_needles", "description": "Set the needle size exactly as stated.",
     "parameters": {"type": "object", "properties": {
         "size": {"type": "number"}, "system": {"type": "string", "enum": ["mm", "us"]}},
         "required": ["size", "system"]}}},
    {"type": "function", "function": {"name": "set_gauge", "description": "Set the knitter's gauge exactly as stated (stitches and optional rows over a width).",
     "parameters": {"type": "object", "properties": {
         "stitches": {"type": "number"}, "rows": {"type": ["number", "null"]},
         "over": {"type": "number", "description": "width the stitches were counted over"},
         "unit": {"type": "string", "enum": ["cm", "in"]}}, "required": ["stitches", "over", "unit"]}}},
    {"type": "function", "function": {"name": "select_size", "description": "Choose one of the pattern's sizes.",
     "parameters": {"type": "object", "properties": {"size": {"type": "string"}}, "required": ["size"]}}},
    {"type": "function", "function": {"name": "get_project_status", "description": "What is set, what is missing, which stage.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "generate_working_pattern", "description": "Adjust the pattern to the knitter's gauge and lock the project.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "start_over", "description": "Unlock a locked project as a new version (resets progress).",
     "parameters": {"type": "object", "properties": {}}}},
]


class Call(BaseModel):
    tool: str
    args: dict
    ok: bool
    message: str


class SetupInput(BaseModel):
    turns: list[str]
    project: Project
    time_budget_s: float = 90

    model_config = {"arbitrary_types_allowed": True}


class SetupOutput(BaseModel):
    reply: str
    calls: list[Call]


def status_text(p: Project) -> str:
    s = project.get_project_status(p).data
    sizes = ", ".join(p.pattern.sizes) if p.pattern and p.pattern.sizes else "none"
    return (f"PROJECT STATUS: stage={s['stage']}, yarn={s['yarn']}, needles_mm={s['needle_mm']}, "
            f"gauge_sts_10cm={s['gauge_sts_10cm']}, pattern={s['pattern']}, pattern sizes: {sizes}, "
            f"chosen size={s['size']}, missing={s['missing']}")


def _execute(p: Project, name: str, args: dict) -> project.ToolResult:
    fn = project.TOOLS.get(name)
    if fn is None:
        return project.ToolResult(ok=False, message=f"Unknown tool {name}.")
    args = {k: v for k, v in args.items() if v is not None}
    try:
        return fn(p, **args)
    except TypeError as e:                     # wrong argument names from the model
        return project.ToolResult(ok=False, message=f"Bad arguments for {name}: {e}")


def run(inp: SetupInput) -> SetupOutput:
    p = inp.project
    system = llm.load_prompt("setup_agent")["system"]
    messages: list[dict] = [{"role": "system", "content": system}]
    calls: list[Call] = []
    reply = ""
    deadline = time.monotonic() + inp.time_budget_s
    for turn in inp.turns:
        messages.append({"role": "user", "content": f"{status_text(p)}\n\nUser: {turn}"})
        for _ in range(MAX_ROUNDS):
            out = llm.chat(messages, tools=TOOL_SPECS, max_tokens=1500, deadline=deadline)
            tool_calls = out.get("tool_calls") or []
            messages.append({"role": "assistant", "content": out.get("content") or "",
                             **({"tool_calls": tool_calls} if tool_calls else {})})
            if not tool_calls:
                reply = (out.get("content") or "").strip()
                break
            for tc in tool_calls:
                fn = tc["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                res = _execute(p, fn["name"], args)
                calls.append(Call(tool=fn["name"], args=args, ok=res.ok, message=res.message))
                messages.append({"role": "tool", "tool_call_id": tc.get("id") or fn["name"],
                                 "content": json.dumps({"ok": res.ok, "message": res.message})})
    return SetupOutput(reply=reply, calls=calls)

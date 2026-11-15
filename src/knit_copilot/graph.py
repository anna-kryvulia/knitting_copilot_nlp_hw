"""LangGraph wiring: one chat turn → router → one specialised node → reply. The only module importing langgraph.

Nodes (each is a thin adapter around a component; components have no LangGraph imports):
  route     components.router (hybrid: rules, then LLM)
  setup     components.setup_agent (LLM tool calls → project.py)
  adjust    project.generate_working_pattern (gauge.py, code)
  explain   components.explainer (fact sheet by code + LLM wording + grounding check)
  yarn      components.yarn_linker + components.yarn_advisor
  lookup    retrieval.search (KB, no LLM) — abbreviation_lookup and knitting_question
  chart     charts.build (code); the UI shows the image
  tracker   tracker.py (code)
  validate  simulator count check (code)
  other     smalltalk / out_of_scope (fixed replies)
State per conversation is kept by the checkpointer (thread_id = project id); the project itself lives in SQLite.
Every node writes a trace record (tracing.py).
"""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from knit_copilot import charts, db, kb, project, tracker
from knit_copilot.components import explainer, router, setup_agent, yarn_advisor, yarn_linker
from knit_copilot.retrieval import search as kbsearch
from knit_copilot.simulator import simulate
from knit_copilot.tracing import trace


class ChatState(TypedDict, total=False):
    project_id: str
    text: str
    intent: str
    route_method: str
    reply: str
    show: str                  # "chart" | "tracker" | "" — what the UI should open
    history: list[dict]


def _load(state: ChatState) -> project.Project:
    p = db.load(state["project_id"])
    if p is None:
        raise ValueError(f"unknown project {state['project_id']}")
    return p


def _pattern(p: project.Project):
    return (p.working.pattern, None) if p.stage == "knitting" and p.working else (p.pattern, p.size)


def _done(state: ChatState, reply: str, show: str = "") -> ChatState:
    hist = list(state.get("history", [])) + [{"role": "user", "content": state["text"]},
                                             {"role": "assistant", "content": reply, "intent": state.get("intent")}]
    return {"reply": reply, "show": show, "history": hist[-40:]}


# ---------- nodes ----------

def route(state: ChatState) -> ChatState:
    p = _load(state)
    with trace(state["project_id"], "route", state["text"]) as t:
        out = router.run(router.RouterInput(text=state["text"], stage=p.stage, has_pattern=p.pattern is not None))
        intent = out.intent if out.intent != "unknown" else "knitting_question"
        t.output = {"intent": intent, "method": out.method}
    return {"intent": intent, "route_method": out.method}


def setup(state: ChatState) -> ChatState:
    p = _load(state)
    with trace(state["project_id"], "setup", state["text"]) as t:
        out = setup_agent.run(setup_agent.SetupInput(turns=[state["text"]], project=p))
        db.save(p)
        t.output = [c.model_dump() for c in out.calls]
    reply = out.reply or "; ".join(c.message for c in out.calls) or "Noted."
    return _done(state, reply)


def adjust(state: ChatState) -> ChatState:
    p = _load(state)
    with trace(state["project_id"], "adjust", state["text"]) as t:
        res = project.generate_working_pattern(p)
        db.save(p)
        t.output = res.model_dump()
    extra = "" if not res.ok else " " + " ".join((p.working.notes if p.working else []))
    return _done(state, res.message + extra, show="tracker" if res.ok else "")


def explain(state: ChatState) -> ChatState:
    p = _load(state)
    pat, size = _pattern(p)
    if pat is None:
        return _done(state, "Paste a pattern first (Pattern tab), then I can explain it.")
    with trace(state["project_id"], "explain", state["text"]) as t:
        out = explainer.run(explainer.ExplainerInput(pattern=pat, size=size, focus=state["text"]))
        t.output = {"violations": out.violations, "attempts": out.attempts}
    warn = f"\n\n_Some details could not be verified: {'; '.join(out.violations[:2])}_" if out.violations else ""
    return _done(state, out.text + warn)


def yarn(state: ChatState) -> ChatState:
    p = _load(state)
    with trace(state["project_id"], "yarn", state["text"]) as t:
        # a yarn named in the message wins; otherwise the project's yarn; otherwise fibre-only questions
        words = re.sub(r"(?i)\b(what|which|is|it|the|for|a|an|good|needles?|gauge|size|should|i|use|can|wash|"
                       r"does|do|usually|give|machine|soft|enough|baby|blanket|weight|yarn)\b|[?.,!]", " ", state["text"])
        link = yarn_linker.run(yarn_linker.LinkerInput(text=words))
        inp = yarn_advisor.AdvisorInput(question=state["text"])
        if link.status == "match":
            inp.yarn_id = link.yarn_id
        elif p.yarn and p.yarn.yarn_id:
            inp.yarn_id = p.yarn.yarn_id
        elif p.yarn and (p.yarn.fibre or p.yarn.weight):
            inp.fibre, inp.weight = p.yarn.fibre, p.yarn.weight or "DK"
        else:
            fib = next((f for f in kb.fibres() if re.search(rf"\b{f}\b", state["text"], re.I)), None)
            if fib is None:
                return _done(state, "Which yarn is it? Tell me its name (e.g. YarnArt Jeans) or its fibre and weight.")
            inp.fibre, inp.weight = fib, "DK"
        out = yarn_advisor.run(inp)
        t.output = out.status
    if out.status != "answered":
        return _done(state, "Which one do you mean: " + ", ".join(out.candidates) + "?")
    return _done(state, out.answer)


def lookup(state: ChatState) -> ChatState:
    with trace(state["project_id"], "lookup", state["text"]) as t:
        q = re.sub(r"(?i)^\s*(what('s| is| does)?|meaning of|define)\s+|\s+mean\s*\??$|\?$", "", state["text"]).strip()
        hits = kbsearch.search(q or state["text"])
        t.output = [h.model_dump() for h in hits[:3]]
    if not hits:
        return _done(state, "I don't have that in my knitting knowledge base.")
    abbrs = kb.abbreviations()
    lines = []
    for h in hits[: (1 if hits[0].method in ("exact", "fuzzy") else 3)]:
        a = abbrs[h.id]
        lines.append(f"**{a.id}** — {a.name}: {a.description} _(source: {a.reference})_")
    prefix = f"Did you mean **{hits[0].id}**? " if hits[0].method == "fuzzy" else ""
    return _done(state, prefix + "\n\n".join(lines))


def chart(state: ChatState) -> ChatState:
    p = _load(state)
    pat, size = _pattern(p)
    if pat is None:
        return _done(state, "Paste a pattern first, then I can draw its chart.")
    with trace(state["project_id"], "chart", state["text"]) as t:
        ch = charts.build(pat, size)
        t.output = {"rows": [r.label for r in ch.rows], "motif": ch.motif_mode}
    return _done(state, f"Here is the chart of {', '.join(r.label for r in ch.rows[:4])}"
                        + ("…" if len(ch.rows) > 4 else "") + (" (one repeat, red box)." if ch.motif_mode else "."),
                 show="chart")


def track(state: ChatState) -> ChatState:
    p = _load(state)
    if p.stage != "knitting":
        return _done(state, "The tracker starts once the working pattern is generated.")
    text = state["text"].lower()
    with trace(state["project_id"], "tracker", state["text"]) as t:
        if m := re.search(r"(?:finished|done with|completed|mark)\s+(?:row|round|rnd)\s*(\d+)", text):
            v = tracker.goto(p, int(m.group(1)))          # row N finished → next row is index N
        elif m := re.search(r"(?:go to|at)\s+(?:row|round|rnd)\s*(\d+)", text):
            v = tracker.goto(p, int(m.group(1)) - 1)
        elif m := re.search(r"(?:ripped|frogged|went) back (\d+)", text):
            v = tracker.prev_row(p, int(m.group(1)))
        elif re.search(r"\b(next|done|finished)\b", text):
            v = tracker.next_row(p)
        else:
            v = tracker.view(p)
        db.save(p)
        t.output = v.model_dump()
    reply = (f"**{'Round' if v.side == 'round' else 'Row'} {v.number} of {v.total}** — {v.label}"
             + (f" ({v.time_of})" if v.time_of else "") + f": {v.instruction}. "
             f"Stitches {v.start_count} → {v.end_count}; {v.rows_left} row{'' if v.rows_left == 1 else 's'} left.")
    return _done(state, reply, show="tracker")


def validate(state: ChatState) -> ChatState:
    p = _load(state)
    pat, size = _pattern(p)
    if pat is None:
        return _done(state, "Paste a pattern first, then I can check it.")
    with trace(state["project_id"], "validate", state["text"]) as t:
        sim = simulate(pat, size)
        mism = sim.count_mismatches()
        t.output = {"errors": sim.errors, "mismatches": [(r.label, r.stated_count, r.end_count) for r in mism]}
    if sim.errors:
        return _done(state, "The stitch counts do not work out: " + sim.errors[0])
    if mism:
        return _done(state, "Stated counts that differ from what the instructions give: "
                     + "; ".join(f"{r.label} says {r.stated_count}, the instructions give {r.end_count}" for r in mism))
    stated = sum(1 for r in sim.rows if r.stated_count is not None)
    return _done(state, "Every row works out" + (f" and all {stated} stated stitch counts match." if stated
                                                  else " (the pattern states no stitch counts to check)."))


def other(state: ChatState) -> ChatState:
    if state.get("intent") == "smalltalk":
        return _done(state, "Happy knitting! Ask me about your pattern, yarn, gauge or what a stitch means.")
    return _done(state, "That's outside what I can help with — I cover written knitting patterns (flat or in the "
                        "round), yarn and gauge, charts and row tracking. Crochet, colourwork, short rows and sewing "
                        "are not supported.")


ROUTES = {"setup": "setup", "adjust_pattern": "adjust", "explain": "explain", "yarn_advice": "yarn",
          "abbreviation_lookup": "lookup", "knitting_question": "lookup", "chart": "chart", "tracker": "tracker",
          "validate": "validate", "out_of_scope": "other", "smalltalk": "other"}


def build_graph():
    g = StateGraph(ChatState)
    g.add_node("route", route)
    for name, fn in [("setup", setup), ("adjust", adjust), ("explain", explain), ("yarn", yarn), ("lookup", lookup),
                     ("chart", chart), ("tracker", track), ("validate", validate), ("other", other)]:
        g.add_node(name, fn)
        g.add_edge(name, END)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: ROUTES.get(s["intent"], "lookup"),
                            {n: n for n in set(ROUTES.values())})
    return g.compile(checkpointer=InMemorySaver())


_GRAPH = None


def chat(project_id: str, text: str) -> ChatState:
    """One chat turn for a project; conversation history is kept per project (thread)."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH.invoke({"project_id": project_id, "text": text},
                         config={"configurable": {"thread_id": project_id}})


def mermaid() -> str:
    return build_graph().get_graph().draw_mermaid()

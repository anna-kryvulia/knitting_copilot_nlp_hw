"""Setup agent evaluation on data/eval/setup_cases.jsonl (30 dialogues).

Per dialogue the agent starts from a fresh project (with a pattern offering the case's sizes; for `locked` cases
the project is already generated) and gets the user turns. Metrics:
  tool_sequence     the called tools (names, in order) equal the expected ones
  args_accuracy     share of expected calls whose arguments match (numbers equal, strings case-insensitive,
                    missing optional args = null)
  state_match       project fields after the dialogue equal the expected state (computed by code from the gold calls)
  no_tool_correct   messages that need no tool get none
Run: python -m eval.eval_setup_agent --split dev
"""

import argparse

import random

from eval.common import load_cases, write_results
from knit_copilot import project
from knit_copilot.components import setup_agent
from knit_copilot.config import settings
from knit_copilot.data.templates import ribbed_hat
from knit_copilot.ir import Pattern


def fresh(case: dict) -> project.Project:
    p = project.new_project("eval")
    base = ribbed_hat(random.Random(0))
    sizes = case["input"]["sizes"] or []
    if sizes:                                   # same hat, relabelled with the case's sizes
        data = base.model_dump(mode="json")
        old = data["sizes"]
        def relabel(x):
            if isinstance(x, dict):
                if set(x) == set(old):
                    vals = list(x.values())
                    return {s: vals[min(i, len(vals) - 1)] for i, s in enumerate(sizes)}
                return {k: relabel(v) for k, v in x.items()}
            if isinstance(x, list):
                return [relabel(v) for v in x]
            return x
        data = relabel(data)
        data["sizes"] = sizes
        base = Pattern.model_validate(data)
    p.pattern, p.pattern_text = base, "(eval pattern)"
    if case["input"]["stage"] == "locked":
        p.size = base.sizes[0] if base.sizes else None
        project.set_gauge(p, 21, 28)
        project.set_needles(p, 4)
        project.generate_working_pattern(p)
    return p


def norm(v):
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, (int, float)):
        return float(v)
    return v


def args_match(want: dict, got: dict) -> bool:
    keys = set(want) | {k for k, v in got.items() if v is not None}
    return all(norm(want.get(k)) == norm(got.get(k)) for k in keys)


def state_of(p: project.Project) -> dict:
    """Project fields in the shape of the gold `expected.state`; the yarn as its name, or its fibre."""
    s = {}
    if p.yarn:
        s["yarn"] = norm(p.yarn.text or p.yarn.fibre)
    for key in ("needle_mm", "gauge_sts_10cm", "gauge_rows_10cm", "size"):
        if getattr(p, key) is not None:
            s[key] = getattr(p, key)
    return s


def gold_state(exp: dict) -> dict:
    s = {k: v for k, v in exp.items() if k != "yarn"}
    if "yarn" in exp:
        s["yarn"] = norm(exp["yarn"].get("name") or exp["yarn"].get("fibre"))
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    rows, failures = [], []
    for c in load_cases("setup_cases.jsonl", args.split):
        p = fresh(c)
        before = state_of(p)
        try:
            out = setup_agent.run(setup_agent.SetupInput(turns=c["input"]["turns"], project=p))
        except (RuntimeError, ValueError) as e:
            failures.append({"id": c["id"], "why": f"error: {str(e)[:120]}"})
            rows.append({"error": True, "tags": c["tags"]})
            print(c["id"], "ERROR", str(e)[:100])
            continue
        want = c["expected"]["calls"]
        got = [{"tool": x.tool, "args": x.args} for x in out.calls]
        seq_ok = [w["tool"] for w in want] == [g["tool"] for g in got]
        arg_hits = sum(1 for w, g in zip(want, got) if w["tool"] == g["tool"] and args_match(w["args"], g["args"]))
        after = state_of(p)
        if c["input"]["stage"] == "locked" or not c["expected"]["state_change"]:
            state_ok = after == before                          # nothing may change
        else:
            want_state = gold_state(c["expected"]["state"])
            if c["expected"].get("linker") == "ambiguous":     # the right outcome is to ask, not to set a yarn
                want_state.pop("yarn", None)
                state_ok = "yarn" not in after and all(after.get(k) == v for k, v in want_state.items())
            else:
                state_ok = all(after.get(k) == v for k, v in want_state.items())
        r = {"id": c["id"], "tags": c["tags"], "seq_ok": seq_ok, "arg_hits": arg_hits, "arg_total": len(want),
             "state_ok": state_ok, "no_tool": not want, "calls": got, "reply": out.reply}
        rows.append(r)
        if not (seq_ok and arg_hits == len(want) and state_ok):
            failures.append({"id": c["id"], "turns": c["input"]["turns"], "want": want, "got": got, "state": after})
        print(f"{c['id']} seq={seq_ok} args={arg_hits}/{len(want)} state={state_ok} {c['tags']}")
    ok = [r for r in rows if not r.get("error")]
    n = max(1, len(ok))
    no_tool = [r for r in ok if r["no_tool"]]
    metrics = {"overall": {
        "n": len(rows), "answered": round(len(ok) / max(1, len(rows)), 3),
        "tool_sequence": round(sum(r["seq_ok"] for r in ok) / n, 3),
        "args_accuracy": round(sum(r["arg_hits"] for r in ok) / max(1, sum(r["arg_total"] for r in ok)), 3),
        "state_match": round(sum(r["state_ok"] for r in ok) / n, 3),
        "no_tool_correct": round(sum(r["seq_ok"] for r in no_tool) / len(no_tool), 3) if no_tool else None}}
    path = write_results("setup_agent", args.split, args.version, metrics, len(rows), failures,
                         model=settings.llm_model, extra={"cases": rows})
    print(metrics["overall"], "\n->", path)


if __name__ == "__main__":
    main()

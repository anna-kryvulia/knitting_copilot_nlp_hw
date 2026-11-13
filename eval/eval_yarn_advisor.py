"""Yarn advisor evaluation (UC3) on data/eval/yarn_advice_cases.jsonl, isolated from the linker (gold yarn id).

Code metrics:
  facts_correct     code-built facts match gold: CYC category, needle range, gauge range (label or CYC)
  needle_mentioned  the answer states a needle size from the facts (range end or suggested size)
  must_mention      share of required facts in the answer (synonyms allowed, see SYNONYMS)
  warning_recall    answers for flagged label gauges tell the knitter to swatch
  grounded_first / grounded_final  no number outside the facts, no wrong citation (before / after repair)
LLM judge (--judge): 1–5 from JUDGE_MODEL against the facts.

Run: python -m eval.eval_yarn_advisor --split dev [--judge]
"""

import argparse
import re
import time

from pydantic import BaseModel

from eval.common import load_cases, write_results
from knit_copilot import llm
from knit_copilot.components import yarn_advisor as ya
from knit_copilot.components import yarn_linker
from knit_copilot.config import settings

SYNONYMS = {
    "low elasticity": r"low elasticity|not (very )?elastic|little (elasticity|stretch)|no elastic memory|"
                      r"(doesn'?t|does not|won'?t|will not) spring back|less elastic|lacks elasticity|inelastic",
    "hard to unravel": r"hard to (unravel|rip|frog|undo)|difficult to (unravel|rip|frog|undo)|lifeline",
    "machine washable": r"machine[- ]wash",
    "slippery": r"slipp",
    "go down a needle size": r"go(ing)? down|smaller needle|down a (needle )?size|down from",
    "larger needles": r"larger needle|bigger needle|much larger",
    "grow": r"\bgrow|lengthen|stretch(es)? (out )?over time",
    "softens": r"soften",
    "markers": r"marker",
    "halo": r"halo|fuzz",
}


class Judgement(BaseModel):
    score: int
    errors: list[str] = []
    reason: str = ""


def mentions(phrase: str, text: str) -> bool:
    return re.search(SYNONYMS.get(phrase.lower(), re.escape(phrase)), text, flags=re.I) is not None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--judge", action="store_true")
    args = ap.parse_args()
    rows, failures = [], []
    for c in load_cases("yarn_advice_cases.jsonl", args.split):
        g, inp = c["expected"], c["input"]
        row = next(y for y in yarn_linker.yarns() if int(y["yarn_id"]) == g["yarn_id"]) if g["yarn_id"] else None
        f = ya.yarn_facts(row, inp.get("fibre"), inp.get("weight"))
        facts_ok = (f.cyc_category == g["cyc_category"] and list(f.needle_mm) == g["needle_mm"]
                    and list(f.gauge_sts_10cm) == g["gauge_sts_10cm"] and f.warn_gauge == g["warn_gauge"])
        t = time.time()
        try:
            out = ya.run(ya.AdvisorInput(yarn_id=g["yarn_id"], fibre=inp.get("fibre"), weight=inp.get("weight"),
                                         question=inp["question"]))
        except (RuntimeError, ValueError) as e:
            failures.append({"id": c["id"], "why": f"no answer: {str(e)[:150]}"})
            rows.append({"id": c["id"], "error": True, "facts_ok": facts_ok})
            print(c["id"], "ERROR", str(e)[:100])
            continue
        a = out.answer
        needles = {f"{x:g}" for x in (*f.needle_mm, f.suggested_needle_mm)}
        r = {"id": c["id"], "tags": c["tags"], "facts_ok": facts_ok, "seconds": round(time.time() - t, 1),
             "needle_mentioned": any(re.search(rf"(?<![\d.]){re.escape(n)}\s*mm", a) for n in needles),
             "must": [mentions(m, a) for m in g["must_mention"]],
             "missing": [m for m in g["must_mention"] if not mentions(m, a)],
             "warn": g["warn_gauge"], "warned": bool(re.search(r"swatch", a, re.I)),
             "grounded_first": out.attempts == 1 and not out.violations, "grounded_final": not out.violations,
             "violations": out.violations, "answer": a}
        if args.judge:
            try:
                msgs = llm.render("judge_yarn", facts=out.facts, question=inp["question"], answer=a)
                j = llm.chat_json(msgs, schema=Judgement, model=settings.judge_model, fallback=False,
                                  deadline=time.monotonic() + 120)
                r.update(judge_score=j.score, judge_errors=j.errors)
            except (RuntimeError, ValueError) as e:
                r.update(judge_score=None, judge_errors=[f"judge failed: {str(e)[:100]}"])
        rows.append(r)
        if not (facts_ok and r["needle_mentioned"] and not r["missing"] and r["grounded_final"]
                and (r["warned"] or not r["warn"])):
            failures.append({"id": c["id"], "why": "; ".join(
                (["facts wrong"] if not facts_ok else []) + (["no needle size"] if not r["needle_mentioned"] else [])
                + [f"missing: {m}" for m in r["missing"]] + r["violations"][:3]
                + (["no swatch warning"] if r["warn"] and not r["warned"] else []))})
        print(f"{c['id']} facts={facts_ok} needle={r['needle_mentioned']} must={sum(r['must'])}/{len(r['must'])} "
              f"grounded={r['grounded_final']} judge={r.get('judge_score')} {r['seconds']}s")

    ok = [r for r in rows if not r.get("error")]
    n = max(1, len(ok))
    warn_rows = [r for r in ok if r["warn"]]
    scores = [r["judge_score"] for r in ok if r.get("judge_score")]
    metrics = {"overall": {
        "n": len(rows), "answered": round(len(ok) / max(1, len(rows)), 3),
        "facts_correct": round(sum(r["facts_ok"] for r in rows) / max(1, len(rows)), 3),
        "needle_mentioned": round(sum(r["needle_mentioned"] for r in ok) / n, 3),
        "must_mention": round(sum(sum(r["must"]) for r in ok) / max(1, sum(len(r["must"]) for r in ok)), 3),
        "warning_recall": round(sum(r["warned"] for r in warn_rows) / len(warn_rows), 3) if warn_rows else None,
        "grounded_first": round(sum(r["grounded_first"] for r in ok) / n, 3),
        "grounded_final": round(sum(r["grounded_final"] for r in ok) / n, 3),
        "judge_mean": round(sum(scores) / len(scores), 2) if scores else None}}
    path = write_results("yarn_advisor", args.split, args.version, metrics, len(rows), failures,
                         model=settings.llm_model, extra={"cases": rows})
    print(metrics["overall"], "\n->", path)


if __name__ == "__main__":
    main()

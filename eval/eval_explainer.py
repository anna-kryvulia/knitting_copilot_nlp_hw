"""Explainer evaluation (UC1), isolated from the parser: input is the GOLD IR of synthetic patterns.

Cases: the first pattern of each template in the split (data/eval/parse_cases.jsonl) → 9 per split.
Code metrics:
  grounded_first / grounded_final  no number outside the fact sheet and no wrong citation (before / after repair)
  fact_coverage  share of required facts mentioned: cast-on count, every repeat count, the stitch count after
                 every written-out row that changes it, every non-basic abbreviation cited as [id]
  citation_recall  cited ids ∩ used non-basic ids / used non-basic ids
  structure      number of "## Step" sections equals the number of steps
LLM judge (--judge): 1–5 score from JUDGE_MODEL (different family from the app model) with errors listed;
  must be calibrated against human ratings before it is trusted (data/eval/judge_calibration.jsonl).

Run: python -m eval.eval_explainer --split dev [--judge]
     python -m eval.eval_explainer --split ravelry [--judge]   (gold IR of the 10 real patterns; the explanation
     text is not saved, because it restates a copyrighted pattern)
"""

import argparse
import re
import time

from pydantic import BaseModel

from eval.common import load_cases, write_results
from knit_copilot import facts, llm
from knit_copilot.components import explainer
from knit_copilot.config import settings
from knit_copilot.ir import Pattern
from knit_copilot.simulator import simulate

BASIC = {"k", "p", "bo"}


class Judgement(BaseModel):
    score: int
    errors: list[str] = []
    reason: str = ""


def required_facts(pattern: Pattern, size: str | None, sheet: facts.FactSheet) -> list[tuple[str, str]]:
    """(kind, value) pairs a complete explanation must contain."""
    sim = simulate(pattern, size)
    req = [("cast_on", str(sim.cast_on))]
    for line in (ln for s in sheet.steps for ln in s.lines):
        if m := re.search(r"that means (\d+) more repeats", line):
            req.append(("repeat_count", m.group(1)))
    for r in sim.rows:
        if r.end_count != r.start_count and r.label != "Bind off" and r.repeat is None:   # written rows only
            req.append(("changed_count", str(r.end_count)))
    for op in sheet.abbreviations:
        if op not in BASIC:
            req.append(("citation", f"[{op}]"))
    return list(dict.fromkeys(req))


def covered(kind: str, value: str, text: str) -> bool:
    if kind == "citation":                       # "[yo]" or "[yo: yarn over …]"
        return re.search(rf"\[{re.escape(value.strip('[]'))}(?::[^\]]*)?\]", text) is not None
    return re.search(rf"(?<![\d.]){re.escape(value)}(?![\d.])", text) is not None


def pick_cases(split: str) -> list[dict]:
    if split == "ravelry":
        from eval.eval_parser_real import gold_cases
        return [{"id": g["slug"], "tags": [g["coverage"]], "expected": {"ir": g["gold_ir"], "size": g["eval_size"]}}
                for g in gold_cases()]
    seen, out = set(), []
    for c in load_cases("parse_cases.jsonl", split):
        if c["tags"][0] not in seen:
            seen.add(c["tags"][0])
            out.append(c)
    return out


def judge(sheet_text: str, explanation: str) -> Judgement:
    msgs = llm.render("judge_explainer", facts=sheet_text, explanation=explanation)
    return llm.chat_json(msgs, schema=Judgement, model=settings.judge_model, fallback=False,
                         deadline=time.monotonic() + 120)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--judge", action="store_true")
    args = ap.parse_args()

    rows, failures = [], []
    for c in pick_cases(args.split):
        pattern, size = Pattern.model_validate(c["expected"]["ir"]), c["expected"]["size"]
        t = time.time()
        try:
            out = explainer.run(explainer.ExplainerInput(pattern=pattern, size=size))
        except (RuntimeError, ValueError) as e:
            rows.append({"id": c["id"], "error": str(e)[:200]})
            failures.append({"id": c["id"], "why": f"no explanation: {str(e)[:150]}"})
            print(c["id"], "ERROR", str(e)[:120])
            continue
        sheet = facts.build(pattern, size)
        req = required_facts(pattern, size, sheet)
        hit = [covered(k, v, out.text) for k, v in req]
        used = [op for op in sheet.abbreviations if op not in BASIC]
        steps_written = len(re.findall(r"^##\s*Step", out.text, flags=re.M | re.I))
        row = {"id": c["id"], "template": c["tags"][0], "seconds": round(time.time() - t, 1),
               "grounded_first": out.attempts == 1 and out.grounded, "grounded_final": out.grounded,
               "violations": out.violations, "fact_coverage": sum(hit) / len(req),
               "missing": [f"{k}:{v}" for (k, v), h in zip(req, hit) if not h],
               "citation_recall": (len(set(out.citations) & set(used)) / len(used)) if used else 1.0,
               "structure_ok": steps_written == len(sheet.steps),
               "text": out.text if args.split != "ravelry" else f"({len(out.text)} chars, not saved)"}
        if args.judge:
            try:
                j = judge(out.facts, out.text)
                row.update(judge_score=j.score, judge_errors=j.errors, judge_reason=j.reason)
            except (RuntimeError, ValueError) as e:
                row.update(judge_score=None, judge_errors=[f"judge failed: {str(e)[:100]}"])
        rows.append(row)
        if row["violations"] or row["missing"] or not row["structure_ok"]:
            failures.append({"id": c["id"], "why": "; ".join(row["violations"][:3] + row["missing"][:5]
                                                            + ([] if row["structure_ok"] else ["step sections"]))})
        print(f"{c['id']} {row['template']:16} cov={row['fact_coverage']:.2f} grounded={row['grounded_final']} "
              f"cit={row['citation_recall']:.2f} steps_ok={row['structure_ok']} "
              f"judge={row.get('judge_score')} {row['seconds']}s")

    ok = [r for r in rows if "error" not in r]
    n = max(1, len(ok))
    scores = [r["judge_score"] for r in ok if r.get("judge_score")]
    metrics = {"overall": {
        "n": len(rows), "answered": round(len(ok) / max(1, len(rows)), 3),
        "grounded_first": round(sum(r["grounded_first"] for r in ok) / n, 3),
        "grounded_final": round(sum(r["grounded_final"] for r in ok) / n, 3),
        "fact_coverage": round(sum(r["fact_coverage"] for r in ok) / n, 3),
        "citation_recall": round(sum(r["citation_recall"] for r in ok) / n, 3),
        "structure_ok": round(sum(r["structure_ok"] for r in ok) / n, 3),
        "judge_mean": round(sum(scores) / len(scores), 2) if scores else None,
        "median_seconds": sorted(r["seconds"] for r in ok)[len(ok) // 2] if ok else None}}
    path = write_results("explainer", args.split, args.version, metrics, len(rows), failures,
                         model=settings.llm_model, extra={"judge_model": settings.judge_model if scores else None,   # only when the judge actually scored
                                                          "cases": rows})
    print(metrics["overall"], "\n->", path)


if __name__ == "__main__":
    main()

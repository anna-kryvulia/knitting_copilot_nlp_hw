"""Rewriter evaluation (UC2 text): one synthetic pattern per template, adjusted to a looser/tighter gauge.

Metrics:
  verified_llm     the LLM's rewritten text re-parses and simulates exactly to the adjusted IR (with ≤ 1 repair)
  first_try        verified without the repair round
  fallback         the code-rendered version had to be used
  style_similarity difflib ratio between the original text and the output (higher = original style kept);
                   reported next to the same ratio for the code-rendered text as a baseline
Run: python -m eval.eval_rewriter --split dev
"""

import argparse
import difflib
import time

from eval.common import load_cases, write_results
from eval.eval_explainer import pick_cases
from knit_copilot.components import rewriter
from knit_copilot.config import settings
from knit_copilot.gauge import KnitterGauge, adjust
from knit_copilot.ir import Pattern


def ratio(a: str, b: str) -> float:
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    rows, failures = [], []
    for i, c in enumerate(pick_cases(args.split)):
        p = Pattern.model_validate(c["expected"]["ir"])
        f = (1.18, 1.12) if i % 2 == 0 else (0.85, 0.9)
        a = adjust(p, c["expected"]["size"], KnitterGauge(sts_per_10cm=round(p.gauge.sts_per_10cm * f[0], 1),
                                                          rows_per_10cm=round(p.gauge.rows_per_10cm * f[1], 1)))
        t = time.time()
        out = rewriter.run(c["input"]["text"], p, a, use_llm=True)
        code_text = rewriter.code_render(a)
        r = {"id": c["id"], "template": c["tags"][0], "style": c["tags"][1], "method": out.method,
             "verified_llm": out.method.startswith("llm"), "first_try": out.method == "llm",
             "fallback": out.method == "code_render", "final_verified": out.verified,
             "style_similarity": ratio(c["input"]["text"], out.text),
             "code_render_similarity": ratio(c["input"]["text"], code_text),
             "seconds": round(time.time() - t, 1), "problems": out.problems}
        rows.append(r)
        if not r["verified_llm"]:
            failures.append({"id": c["id"], "why": "; ".join(out.problems[:2]) or "fallback"})
        print(f"{c['id']} {r['template']:16} {r['style']:9} {out.method:12} sim={r['style_similarity']} "
              f"(code {r['code_render_similarity']}) {r['seconds']}s {out.problems[:1]}")
    n = max(1, len(rows))
    llm_rows = [r for r in rows if r["verified_llm"]]
    metrics = {"overall": {
        "n": len(rows), "verified_llm": round(len(llm_rows) / n, 3),
        "first_try": round(sum(r["first_try"] for r in rows) / n, 3),
        "fallback": round(sum(r["fallback"] for r in rows) / n, 3),
        "final_verified": round(sum(r["final_verified"] for r in rows) / n, 3),
        "style_similarity_llm": round(sum(r["style_similarity"] for r in llm_rows) / len(llm_rows), 3) if llm_rows else None,
        "style_similarity_code_render": round(sum(r["code_render_similarity"] for r in rows) / n, 3)}}
    path = write_results("rewriter", args.split, args.version, metrics, len(rows), failures,
                         model=settings.llm_model, extra={"cases": rows})
    print(metrics["overall"], "\n->", path)


if __name__ == "__main__":
    main()

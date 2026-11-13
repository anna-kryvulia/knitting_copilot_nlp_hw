"""Parser evaluation: pattern text → IR, scored by simulating parsed and gold IR row by row.

Metrics (docs/01_business_understanding.md §1.8):
- parse_success     parser returned a valid IR that simulates without errors
- total_rows_match  same number of worked rows as gold
- row_count_agreement  share of gold rows whose end stitch count is reproduced (rows aligned by number)
- op_f1             micro F1 over stitch operations per aligned row (multiset overlap)
- exact_match       every row has the same ops and counts
- side_accuracy     RS/WS on numbered flat rows whose text states a side
Comparison is on simulation output, so equivalent notations ("k to end" vs "k44") count as equal.

Run: python -m eval.eval_parser --parser grammar|llm|hybrid --split dev
"""

import argparse
import re
from collections import Counter, defaultdict

from eval.common import app_model, load_cases, write_results
from knit_copilot.ir import Pattern
from knit_copilot.simulator import simulate


def get_parser(name: str):
    if name == "grammar":
        from knit_copilot.parser_grammar import parse
        return lambda text: parse(text)
    from knit_copilot.components import parser as llm_parser
    return lambda text: llm_parser.run(llm_parser.ParserInput(text=text, mode=name))


def score_case(case: dict, parse_fn) -> dict:
    size = case["input"]["size"]
    gold = simulate(Pattern.model_validate(case["expected"]["ir"]), size)
    res = parse_fn(case["input"]["text"])
    out = {"id": case["id"], "tags": case["tags"], "warnings": res.warnings[:3],
           "parse_success": False, "total_rows_match": False, "exact_match": False,
           "rows_gold": len(gold.rows), "rows_matched_count": 0, "op_tp": 0, "op_pred": 0, "op_gold": 0,
           "side_total": 0, "side_correct": 0, "first_diff": None}
    if not res.ok:
        out["op_gold"] = sum(len(r.ops) for r in gold.rows)
        out["first_diff"] = "no IR: " + "; ".join(res.warnings[:2])
        return out
    pred = simulate(res.pattern, size)
    out["parse_success"] = pred.ok
    out["total_rows_match"] = len(pred.rows) == len(gold.rows)
    for i, g in enumerate(gold.rows):
        out["op_gold"] += len(g.ops)
        p = pred.rows[i] if i < len(pred.rows) else None
        if p is None:
            out["first_diff"] = out["first_diff"] or f"row {g.number} ({g.label}) missing"
            continue
        out["op_pred"] += len(p.ops)
        out["op_tp"] += sum((Counter(p.ops) & Counter(g.ops)).values())
        if p.end_count == g.end_count:
            out["rows_matched_count"] += 1
        elif out["first_diff"] is None:
            out["first_diff"] = f"row {g.number} ({g.label}): {p.end_count} sts vs gold {g.end_count}"
        if g.side in ("RS", "WS") and re.fullmatch(r"Row \d+", g.label):
            out["side_total"] += 1
            out["side_correct"] += p.side == g.side
    out["op_pred"] += sum(len(p.ops) for p in pred.rows[len(gold.rows):])
    out["exact_match"] = pred.ok and out["total_rows_match"] and all(
        p.ops == g.ops and p.end_count == g.end_count for p, g in zip(pred.rows, gold.rows))
    if not pred.ok:
        out["first_diff"] = "simulation error: " + pred.errors[0]
    return out


def aggregate(rows: list[dict]) -> dict:
    n = len(rows) or 1
    tp, pp, gg = (sum(r[k] for r in rows) for k in ("op_tp", "op_pred", "op_gold"))
    prec, rec = (tp / pp if pp else 0.0), (tp / gg if gg else 0.0)
    side_t = sum(r["side_total"] for r in rows)
    return {
        "n": len(rows),
        "parse_success": round(sum(r["parse_success"] for r in rows) / n, 3),
        "total_rows_match": round(sum(r["total_rows_match"] for r in rows) / n, 3),
        "row_count_agreement": round(sum(r["rows_matched_count"] for r in rows) / max(1, sum(r["rows_gold"] for r in rows)), 3),
        "op_precision": round(prec, 3), "op_recall": round(rec, 3),
        "op_f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
        "exact_match": round(sum(r["exact_match"] for r in rows) / n, 3),
        "side_accuracy": round(sum(r["side_correct"] for r in rows) / side_t, 3) if side_t else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", default="grammar", choices=["grammar", "llm", "hybrid"])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()

    cases = load_cases("parse_cases.jsonl", args.split)[: args.limit]
    parse_fn = get_parser(args.parser)
    scored = []
    for c in cases:
        scored.append(score_case(c, parse_fn))
        print(f"{c['id']} {'OK ' if scored[-1]['exact_match'] else 'ERR'} {scored[-1]['first_diff'] or ''}"[:140])

    by_style, by_template = defaultdict(list), defaultdict(list)
    for s in scored:
        by_template[s["tags"][0]].append(s)
        by_style[s["tags"][1]].append(s)
        if "typo" in s["tags"]:
            by_style["+typo"].append(s)
    metrics = {"overall": aggregate(scored),
               "by_source": {"synthetic": aggregate([s for s in scored if "ravelry" not in s["tags"]])},
               "by_style": {k: aggregate(v) for k, v in sorted(by_style.items())},
               "by_template": {k: aggregate(v) for k, v in sorted(by_template.items())}}
    failures = [{"id": s["id"], "tags": s["tags"], "why": s["first_diff"], "warnings": s["warnings"]}
                for s in scored if not s["exact_match"]]
    path = write_results(f"parser_{args.parser}", args.split, args.version, metrics, len(scored), failures,
                         model=None if args.parser == "grammar" else app_model())
    o = metrics["overall"]
    print(f"\n{args.parser} on {args.split} (n={o['n']}): parse_success={o['parse_success']} "
          f"row_count_agreement={o['row_count_agreement']} op_f1={o['op_f1']} exact={o['exact_match']} "
          f"side={o['side_accuracy']}\n-> {path}")


if __name__ == "__main__":
    main()

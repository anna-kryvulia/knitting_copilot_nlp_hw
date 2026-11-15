"""Parser evaluation on the real Ravelry patterns (hand-made gold in git-ignored data/private/ravelry/gold/).

Input: the text extracted from each PDF, as the knitter would paste it (title, materials, notes and all).
Gold: the hand-written IR, simulated. Scoring is on simulation output, like the synthetic parser eval.
For `partial` patterns only the annotated section is scored: the first len(gold rows) worked rows.
'Until length' steps are simulated with the gold row gauge when the parsed pattern has none (the row gauge is
a reading decision for one pattern, see REVIEW.md).

Equivalent notations count as equal (v3 scoring): marker ops (pm/sm/rm) are dropped, because markers make no
stitch and a beginning-of-round marker is optional; "slip purlwise" + "with yarn in front/back" equals the single
KB stitch sl_wyif / sl_wyib. Size labels are matched by name, else by position ("S/M" ↔ "S/M Adult").

Metrics per pattern, then averaged / pooled:
  answered             the parser returned an IR (verified, or unverified: valid JSON that did not simulate,
                       never used by the app; scored up to its first simulation error)
  verified             the IR passed the parser's simulation check
  simulates            the IR simulates without errors over the scored rows
  rows_to_divergence   share of gold rows worked identically (ops and count) before the first difference
  row_count_agreement  share of aligned gold rows with the same end stitch count
  op_f1                micro F1 over stitch operations per aligned row
  total_rows_match     same number of scored rows (full patterns: whole piece)
  exact                every scored row identical
Only aggregate numbers and row labels go to results/ (the pattern text and gold IR stay private).
Run: python -m eval.eval_parser_real --parser grammar|llm|hybrid
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from eval.common import app_model, write_results
from eval.eval_parser import get_parser
from knit_copilot.ir import Pattern
from knit_copilot.simulator import simulate

PRIVATE = Path("data/private/ravelry")
MARKERS = {"pm", "sm", "rm"}
MERGE = {("sl_pw", "wyif"): "sl_wyif", ("wyif", "sl_pw"): "sl_wyif",
         ("sl_pw", "wyib"): "sl_wyib", ("wyib", "sl_pw"): "sl_wyib"}


def canon(ops: list[str]) -> list[str]:
    """Ops with equivalent notations unified (see module docstring)."""
    out: list[str] = []
    for o in ops:
        if o in MARKERS:
            continue
        if out and (out[-1], o) in MERGE:
            out[-1] = MERGE[(out[-1], o)]
            continue
        out.append(o)
    return out


def match_size(size: str | None, gold_sizes: list[str], pred_sizes: list[str]) -> str | None:
    if not pred_sizes:
        return None
    if size in pred_sizes:
        return size
    key = (size or "").replace(" ", "").lower()
    by_name = [s for s in pred_sizes if s.replace(" ", "").lower() == key
               or s.replace(" ", "").lower().startswith(key)]
    if len(by_name) == 1:
        return by_name[0]
    if size in gold_sizes and len(gold_sizes) == len(pred_sizes):
        return pred_sizes[gold_sizes.index(size)]
    return pred_sizes[0]


def gold_cases() -> list[dict]:
    return [json.loads(f.read_text()) for f in sorted((PRIVATE / "gold").glob("*.json"))]


def score(g: dict, parse_fn) -> dict:
    gold_pat = Pattern.model_validate(g["gold_ir"])
    size = g["eval_size"]
    gold = simulate(gold_pat, size)
    n = len(gold.rows)
    out = {"slug": g["slug"], "coverage": g["coverage"], "rows_gold": n, "answered": False, "verified": False,
           "simulates": False, "same_prefix": 0, "count_hits": 0, "op_tp": 0, "op_pred": 0,
           "op_gold": sum(len(canon(r.ops)) for r in gold.rows),
           "total_rows_match": False, "exact": False, "first_diff": None, "rows_pred": 0, "warnings": 0}
    res = parse_fn((PRIVATE / f"{g['slug']}.txt").read_text())
    out["warnings"] = len(res.warnings)
    pat = res.pattern or getattr(res, "unverified", None)
    if pat is None:
        out["first_diff"] = "no IR: " + "; ".join(w[:80] for w in res.warnings[-1:])
        return out
    out["answered"], out["verified"] = True, res.ok
    size_p = match_size(size, gold_pat.sizes or [], pat.sizes or [])
    rows_gauge = None if (pat.gauge and pat.gauge.rows_per_10cm) else gold_pat.gauge.rows_per_10cm
    pred = simulate(pat, size_p, rows_per_10cm=rows_gauge)
    scored = pred.rows[:n] if g["coverage"] == "partial" else pred.rows
    out["rows_pred"] = len(pred.rows)
    # a simulation error after the annotated section does not count against a partial pattern
    out["simulates"] = pred.ok or (g["coverage"] == "partial" and len(pred.rows) >= n)
    out["total_rows_match"] = len(scored) == n
    diverged = False
    for i, gr in enumerate(gold.rows):
        pr = scored[i] if i < len(scored) else None
        if pr is None:
            out["first_diff"] = out["first_diff"] or f"row {gr.number} ({gr.label}) missing"
            break
        p_ops, g_ops = canon(pr.ops), canon(gr.ops)
        out["op_pred"] += len(p_ops)
        out["op_tp"] += sum((Counter(p_ops) & Counter(g_ops)).values())
        out["count_hits"] += pr.end_count == gr.end_count
        if not diverged and p_ops == g_ops and pr.end_count == gr.end_count:
            out["same_prefix"] += 1
        elif not diverged:
            diverged = True
            out["first_diff"] = (f"row {gr.number} (gold '{gr.label}', parsed '{pr.label}'): "
                                 f"{pr.start_count}→{pr.end_count} vs gold {gr.start_count}→{gr.end_count}")
    out["op_pred"] += sum(len(canon(r.ops)) for r in scored[n:])
    out["exact"] = out["simulates"] and out["total_rows_match"] and out["same_prefix"] == n
    if not pred.ok and not out["simulates"]:
        out["first_diff"] = (out["first_diff"] or "") + f" | simulation error: {pred.errors[0][:100]}"
    return out


def aggregate(rows: list[dict]) -> dict:
    k = len(rows) or 1
    tp, pp, gg = (sum(r[x] for r in rows) for x in ("op_tp", "op_pred", "op_gold"))
    prec, rec = (tp / pp if pp else 0.0), (tp / gg if gg else 0.0)
    return {"n": len(rows),
            "answered": round(sum(r["answered"] for r in rows) / k, 3),
            "verified": round(sum(r["verified"] for r in rows) / k, 3),
            "simulates": round(sum(r["simulates"] for r in rows) / k, 3),
            "rows_to_divergence": round(sum(r["same_prefix"] / r["rows_gold"] for r in rows) / k, 3),
            "row_count_agreement": round(sum(r["count_hits"] for r in rows) / max(1, sum(r["rows_gold"] for r in rows)), 3),
            "op_f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "total_rows_match": round(sum(r["total_rows_match"] for r in rows) / k, 3),
            "exact": round(sum(r["exact"] for r in rows) / k, 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", default="grammar", choices=["grammar", "llm", "hybrid"])
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    parse_fn = get_parser(args.parser)
    rows = []
    for g in gold_cases():
        r = score(g, parse_fn)
        rows.append(r)
        print(f"{r['slug']:28} {'EXACT' if r['exact'] else '     '} {'V' if r['verified'] else 'u' if r['answered'] else '-'} prefix {r['same_prefix']}/{r['rows_gold']} "
              f"counts {r['count_hits']}/{r['rows_gold']} pred_rows {r['rows_pred']}  {r['first_diff'] or ''}"[:220])
    metrics = {"overall": aggregate(rows),
               "full": aggregate([r for r in rows if r["coverage"] == "full"]),
               "partial": aggregate([r for r in rows if r["coverage"] == "partial"])}
    failures = [{"slug": r["slug"], "why": r["first_diff"]} for r in rows if not r["exact"]]
    model = "grammar" if args.parser == "grammar" else app_model()
    path = write_results(f"parser_{args.parser}", "ravelry", args.version, metrics, len(rows), failures,
                         model=model, extra={"patterns": [{k: v for k, v in r.items()} for r in rows]})
    print(metrics["overall"], "\n->", path)


if __name__ == "__main__":
    main()

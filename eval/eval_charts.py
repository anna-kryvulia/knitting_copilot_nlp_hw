"""Chart evaluation (UC4) on the gold IR of all synthetic patterns of a split.

Every written row of every pattern is charted at full width and read back:
  ops_match        reading the cells in working order gives exactly the simulator's stitch operations
                   (ops that make no stitch — bind off, drop, markers — have no cell)
  width_match      the row's cells span exactly the stitch count after the row
  symbol_match     every cell uses the KB symbol for its side (RS/round vs WS)
  direction_ok     RS rows and rounds start at the right edge, WS rows at the left edge
Default charts (stitch-pattern block, motif mode when wide):
  motif_aligned    in motif mode, rows of constant-count patterns all have the same width
  default_has_work the default chart shows rows with stitch work beyond knit/purl whenever the pattern has any

Run: python -m eval.eval_charts --split dev
"""

import argparse

from eval.common import load_cases, write_results
from knit_copilot import charts, kb
from knit_copilot.ir import Pattern, RowsStep
from knit_copilot.simulator import simulate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    rows_total = ops_ok = width_ok = sym_ok = dir_ok = 0
    pat_rows, failures = [], []
    for c in load_cases("parse_cases.jsonl", args.split):
        p, size = Pattern.model_validate(c["expected"]["ir"]), c["expected"]["size"]
        sim = simulate(p, size)
        first = {}
        for r in sim.rows:
            first.setdefault(r.label, r)
        labels = [r.label for st in p.pieces[0].steps if isinstance(st, RowsStep) for r in st.rows]
        ch = charts.build(p, size, labels=labels, motif=False)
        for row in ch.rows:
            rows_total += 1
            want = [o for o in first[row.label].ops if kb.abbreviations()[o].produces > 0]
            got = [cell.op for cell in row.cells]
            ok_ops = got == want
            ok_w = row.width == first[row.label].end_count
            ok_sym = all(cell.symbol == ((kb.abbreviations()[cell.op].chart_symbol_ws if row.side == "WS"
                                          else kb.abbreviations()[cell.op].chart_symbol) or "") for cell in row.cells)
            disp = row.display()
            ok_dir = not row.cells or (disp[-1] is row.cells[0] if row.side != "WS" else disp[0] is row.cells[0])
            ops_ok += ok_ops
            width_ok += ok_w
            sym_ok += ok_sym
            dir_ok += ok_dir
            if not (ok_ops and ok_w and ok_sym and ok_dir):
                failures.append({"id": c["id"], "row": row.label, "why": f"ops={ok_ops} width={ok_w} "
                                                                       f"symbols={ok_sym} direction={ok_dir}"})
        default = charts.build(p, size)
        constant = len({r.end_count for r in sim.rows if r.label != "Bind off"}) == 1
        has_work = any(kb.abbreviations()[o].id not in ("k", "p", "bo") for r in sim.rows for o in r.ops)
        shows_work = any(cell.op not in ("k", "p") for r in default.rows for cell in r.cells)
        pat_rows.append({"motif": default.motif_mode, "aligned": len({r.width for r in default.rows}) == 1
                         if default.motif_mode and constant else None,
                         "work_ok": shows_work if has_work else None})
    n = max(1, rows_total)
    motif_checks = [r["aligned"] for r in pat_rows if r["aligned"] is not None]
    work_checks = [r["work_ok"] for r in pat_rows if r["work_ok"] is not None]
    metrics = {"overall": {
        "patterns": len(pat_rows), "rows": rows_total,
        "ops_match": round(ops_ok / n, 3), "width_match": round(width_ok / n, 3),
        "symbol_match": round(sym_ok / n, 3), "direction_ok": round(dir_ok / n, 3),
        "motif_mode_patterns": sum(r["motif"] for r in pat_rows),
        "motif_aligned": round(sum(motif_checks) / len(motif_checks), 3) if motif_checks else None,
        "default_has_work": round(sum(work_checks) / len(work_checks), 3) if work_checks else None}}
    path = write_results("charts", args.split, args.version, metrics, rows_total, failures)
    print(metrics["overall"])
    for f in failures[:10]:
        print("  ", f)
    print("->", path)


if __name__ == "__main__":
    main()

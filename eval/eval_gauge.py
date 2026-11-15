"""Gauge adjustment evaluation (UC2), on the gold IR of the synthetic patterns × knitter gauges.

Cases: every pattern of the split with two knitter gauges (one tighter, one looser; fixed seed).
Metrics (targets in docs/01 §1.8):
  success              an adjusted pattern was produced and simulates
  closest_valid        brute force over every stitch count 1 … 2×target: no valid count is closer to the target
                       than the chosen one ("count correctness vs reference calculation")
  motifs_kept          every repeat block (stitch-level motif) is unchanged
  width_error_cm       |finished width after − before| (mean, max, share ≤ 1 cm)
  length_error_cm      |finished length after − before| for patterns with a length (mean, max, share ≤ 1 cm)
  width_error_unavoidable  share of > 1 cm width errors where no valid count could get within 1 cm (motif size)

Run: python -m eval.eval_gauge --split dev
"""

import argparse
import random

from eval.common import load_cases, write_results
from knit_copilot.gauge import KnitterGauge, _candidate, adjust, flatten_size, motifs
from knit_copilot.ir import Gauge, Pattern
from knit_copilot.simulator import simulate

FACTORS = [(0.85, 0.9), (0.9, 0.95), (1.1, 1.05), (1.18, 1.12)]


def valid_counts(base: Pattern, fs: float, fr: float | None, knitter: Gauge, hi: int) -> list[int]:
    out = []
    for c in range(1, hi + 1):
        cand = _candidate(base, c, fs, fr)
        if cand is None:
            continue
        cand.gauge = knitter
        sim = simulate(cand, None)
        if sim.ok and all(r.end_count > 0 for r in sim.rows if r.label != "Bind off"):
            out.append(c)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    rng = random.Random(5)
    rows, failures = [], []
    for c in load_cases("parse_cases.jsonl", args.split):
        p, size = Pattern.model_validate(c["expected"]["ir"]), c["expected"]["size"]
        for fs_, fr_ in rng.sample(FACTORS, 2):
            g = p.gauge
            kg = KnitterGauge(sts_per_10cm=round(g.sts_per_10cm * fs_, 1), rows_per_10cm=round(g.rows_per_10cm * fr_, 1))
            a = adjust(p, size, kg)
            base = flatten_size(p, size)
            fs = kg.sts_per_10cm / g.sts_per_10cm
            fr = kg.rows_per_10cm / g.rows_per_10cm
            knitter = Gauge(sts_per_10cm=kg.sts_per_10cm, rows_per_10cm=kg.rows_per_10cm, stitch_pattern="x")
            target = base.pieces[0].cast_on * fs           # exact, not the rounded value in the report
            valid = valid_counts(base, fs, fr, knitter, int(2 * target) + 4)
            best = min(valid, key=lambda v: (abs(v - target), v)) if valid else None
            close_enough = [v for v in valid if abs(v / kg.sts_per_10cm * 10 - a.before.width_cm) <= 1.0]
            r = {"id": c["id"], "template": c["tags"][0], "factor": (fs_, fr_), "success": a.ok,
                 # ties (two counts equally close) both count as correct
                 "closest_valid": a.ok and best is not None and abs(a.chosen_stitches - target) <= abs(best - target) + 1e-9,
                 "motifs_kept": motifs(base) == motifs(a.pattern),
                 "width_error": abs(a.after.width_cm - a.before.width_cm),
                 "length_error": abs(a.after.length_cm - a.before.length_cm) if a.before.length_cm and a.after.length_cm else None,
                 "unavoidable": not close_enough}
            rows.append(r)
            if not (r["success"] and r["closest_valid"] and r["motifs_kept"]) or r["width_error"] > 1.0:  # noqa: E501
                failures.append({"id": c["id"], "template": r["template"], "factor": r["factor"],
                                 "why": f"chosen {a.chosen_stitches} best {best} target {a.target_stitches} "
                                        f"width {a.before.width_cm}->{a.after.width_cm} unavoidable={r['unavoidable']}"})
    n = max(1, len(rows))
    widths = [r["width_error"] for r in rows]
    lengths = [r["length_error"] for r in rows if r["length_error"] is not None]
    over = [r for r in rows if r["width_error"] > 1.0]
    by_t = {}
    for r in rows:
        by_t.setdefault(r["template"], []).append(r["width_error"])
    metrics = {"overall": {
        "n": len(rows), "success": round(sum(r["success"] for r in rows) / n, 3),
        "closest_valid": round(sum(r["closest_valid"] for r in rows) / n, 3),
        "motifs_kept": round(sum(r["motifs_kept"] for r in rows) / n, 3),
        "width_error_mean_cm": round(sum(widths) / n, 2), "width_error_max_cm": round(max(widths), 2),
        "width_within_1cm": round(sum(w <= 1.0 for w in widths) / n, 3),
        "width_error_unavoidable": round(sum(r["unavoidable"] for r in over) / len(over), 3) if over else None,
        "length_error_mean_cm": round(sum(lengths) / len(lengths), 2) if lengths else None,
        "length_error_max_cm": round(max(lengths), 2) if lengths else None,
        "length_within_1cm": round(sum(x <= 1.0 for x in lengths) / len(lengths), 3) if lengths else None},
        "width_error_mean_by_template": {k: round(sum(v) / len(v), 2) for k, v in sorted(by_t.items())}}
    path = write_results("gauge", args.split, args.version, metrics, len(rows), failures)
    print(metrics["overall"])
    print(metrics["width_error_mean_by_template"])
    for f in failures[:12]:
        print("  ", f["id"], f["template"], f["factor"], f["why"])
    print("->", path)


if __name__ == "__main__":
    main()

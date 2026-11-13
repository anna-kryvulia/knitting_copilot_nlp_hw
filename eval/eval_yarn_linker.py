"""Yarn linker evaluation (UC3) on data/eval/yarn_link_cases.jsonl.

Metrics:
  accuracy          the decision is right: correct yarn / "none" for unknown yarns / "ambiguous" with the
                    right candidate set
  top1_accuracy     on cases with one gold yarn: the linked yarn is correct
  none_precision    of the cases where the linker says "none", how many really are unknown
  none_recall       of the unknown yarns, how many get "none" (a wrong match here would give wrong advice)
  ambiguous_recall  names shared by two brands are flagged as ambiguous (the system should then ask)

Run: python -m eval.eval_yarn_linker --split dev
"""

import argparse
from collections import defaultdict

from eval.common import load_cases, write_results
from knit_copilot.components import yarn_linker


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    cases = load_cases("yarn_link_cases.jsonl", args.split)
    rows, failures = [], []
    for c in cases:
        out = yarn_linker.run(yarn_linker.LinkerInput(text=c["input"]["text"]))
        exp = c["expected"]
        if exp["ambiguous"]:
            kind = "ambiguous"
            ok = out.status == "ambiguous" and sorted(x.yarn_id for x in out.candidates) == exp["ambiguous"]
        elif exp["yarn_id"] is None:
            kind = "none"
            ok = out.status == "none"
        else:
            kind = "match"
            ok = out.status == "match" and out.yarn_id == exp["yarn_id"]
        rows.append({"kind": kind, "ok": ok, "status": out.status, "tags": c["tags"]})
        if not ok:
            failures.append({"id": c["id"], "text": c["input"]["text"], "expected": exp,
                             "why": f"{out.status} {[(x.brand, x.name, x.score) for x in out.candidates[:2]]}"})

    def share(xs):
        return round(sum(xs) / len(xs), 3) if xs else None
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r)
    said_none = [r for r in rows if r["status"] == "none"]
    metrics = {"overall": {
        "n": len(rows), "accuracy": share([r["ok"] for r in rows]),
        "top1_accuracy": share([r["ok"] for r in by_kind["match"]]),
        "none_precision": share([r["kind"] == "none" for r in said_none]),
        "none_recall": share([r["ok"] for r in by_kind["none"]]),
        "ambiguous_recall": share([r["ok"] for r in by_kind["ambiguous"]])},
        "by_tag": {t: share([r["ok"] for r in rows if t in r["tags"]]) for t in sorted({t for r in rows for t in r["tags"]})}}
    path = write_results("yarn_linker", args.split, args.version, metrics, len(rows), failures)
    print(metrics["overall"])
    print(metrics["by_tag"])
    for f in failures:
        print("  FAIL", f["id"], repr(f["text"]), "→", f["why"])
    print("->", path)


if __name__ == "__main__":
    main()

"""Router evaluation on data/eval/intent_cases.jsonl (88 messages, 11 intents).

Metrics: accuracy, macro-F1, per-intent F1, confusion matrix; for rules/hybrid also coverage (share decided by
rules) and rule precision (accuracy of the messages the rules decided).
Run: python -m eval.eval_router --mode rules|llm|hybrid --split dev
"""

import argparse
from collections import Counter, defaultdict

from eval.common import load_cases, write_results
from knit_copilot.components import router
from knit_copilot.config import settings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="hybrid", choices=["rules", "llm", "hybrid"])
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    cases = load_cases("intent_cases.jsonl", args.split)
    gold, pred, methods, failures = [], [], [], []
    for c in cases:
        try:
            out = router.run(router.RouterInput(text=c["input"]["text"], mode=args.mode))
        except (RuntimeError, ValueError) as e:
            out = router.RouterOutput(intent="unknown", confidence=0, method=f"error: {str(e)[:60]}")
        gold.append(c["expected"]["intent"])
        pred.append(out.intent)
        methods.append(out.method)
        if out.intent != c["expected"]["intent"]:
            failures.append({"id": c["id"], "text": c["input"]["text"], "gold": gold[-1], "pred": out.intent,
                             "method": out.method, "tags": c["tags"]})
    labels = router.INTENTS
    f1 = {}
    for lb in labels:
        tp = sum(g == p == lb for g, p in zip(gold, pred))
        fp = sum(p == lb and g != lb for g, p in zip(gold, pred))
        fn = sum(g == lb and p != lb for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1[lb] = round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0
    decided = [(g, p) for g, p, m in zip(gold, pred, methods) if m.startswith("rule")]
    confusion = defaultdict(Counter)
    for g, p in zip(gold, pred):
        confusion[g][p] += 1
    n = max(1, len(gold))
    metrics = {"overall": {
        "n": len(gold), "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / n, 3),
        "macro_f1": round(sum(f1.values()) / len(labels), 3),
        "rule_coverage": round(len(decided) / n, 3),
        "rule_precision": round(sum(g == p for g, p in decided) / len(decided), 3) if decided else None,
        "llm_calls": sum(m == "llm" for m in methods)},
        "per_intent_f1": f1, "confusion": {g: dict(c) for g, c in confusion.items()}}
    path = write_results(f"router_{args.mode}", args.split, args.version, metrics, len(gold), failures,
                         model=None if args.mode == "rules" else settings.llm_model)
    print(metrics["overall"])
    for f in failures:
        print(f"  {f['id']} [{f['method']}] gold={f['gold']:20} pred={f['pred']:20} {f['text']}")
    print("->", path)


if __name__ == "__main__":
    main()

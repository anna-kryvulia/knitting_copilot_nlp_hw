"""KB lookup / retrieval evaluation (UC6) on data/eval/kb_queries.jsonl.

exact cases     accuracy of search() top-1 (exact alias or fuzzy typo match)
question cases  per retrieval method (bm25, dense, hybrid):
                hit@1   top-1 is a relevant entry
                recall@3  |relevant ∩ top-3| / min(3, |relevant|)
                mrr     1 / rank of the first relevant entry (0 if not in top 10)
                lookup_false_positive  question answered by the exact/fuzzy path with a wrong entry

Run: python -m eval.eval_kb --split dev [--version v1]
"""

import argparse

from eval.common import load_cases, write_results
from knit_copilot.retrieval import search as kbsearch

METHODS = ["bm25", "dense", "hybrid"]


def score_question(case: dict, method: str) -> dict:
    relevant = set(case["expected"]["relevant"])
    hits = [h.id for h in kbsearch.retrieve(case["input"]["query"], method, k=10)]
    first = next((i for i, h in enumerate(hits) if h in relevant), None)
    return {"hit1": hits[:1] != [] and hits[0] in relevant,
            "recall3": len(relevant & set(hits[:3])) / min(3, len(relevant)),
            "mrr": 0.0 if first is None else 1 / (first + 1), "top3": hits[:3]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    cases = load_cases("kb_queries.jsonl", args.split)
    exact = [c for c in cases if c["input"]["kind"] == "exact"]
    questions = [c for c in cases if c["input"]["kind"] == "question"]
    failures = []

    ok = 0
    for c in exact:
        hits = kbsearch.search(c["input"]["query"])
        good = bool(hits) and hits[0].id == c["expected"]["primary"]
        ok += good
        if not good:
            failures.append({"id": c["id"], "query": c["input"]["query"], "why": f"got {[h.id for h in hits[:1]]}"})
    metrics = {"exact": {"n": len(exact), "accuracy": round(ok / max(1, len(exact)), 3)}, "questions": {}}

    def wrong_lookup(c: dict) -> bool:          # exact/fuzzy path answered a question with a non-relevant entry
        hit = kbsearch.lookup_exact(c["input"]["query"])
        return hit is not None and hit.id not in c["expected"]["relevant"]
    fp = sum(wrong_lookup(c) for c in questions)
    for m in METHODS:
        rows = [score_question(c, m) for c in questions]
        n = max(1, len(rows))
        metrics["questions"][m] = {"n": len(rows), "hit@1": round(sum(r["hit1"] for r in rows) / n, 3),
                                   "recall@3": round(sum(r["recall3"] for r in rows) / n, 3),
                                   "mrr": round(sum(r["mrr"] for r in rows) / n, 3)}
        if m == "hybrid":
            failures += [{"id": c["id"], "query": c["input"]["query"], "relevant": c["expected"]["relevant"],
                          "why": f"hybrid top3 {r['top3']}"} for c, r in zip(questions, rows) if r["recall3"] == 0]
    metrics["questions"]["lookup_false_positive"] = round(fp / max(1, len(questions)), 3)

    path = write_results("kb_lookup", args.split, args.version, metrics, len(cases), failures,
                         extra={"embedding_model": kbsearch.settings.embedding_model})
    print(f"exact accuracy: {metrics['exact']['accuracy']} (n={len(exact)})")
    for m in METHODS:
        q = metrics["questions"][m]
        print(f"{m:7} hit@1={q['hit@1']}  recall@3={q['recall@3']}  mrr={q['mrr']}  (n={q['n']})")
    print(f"questions caught by exact/fuzzy path: {metrics['questions']['lookup_false_positive']}")
    for f in failures:
        print("  FAIL", f["id"], f["query"], "|", f["why"])
    print(f"-> {path}")


if __name__ == "__main__":
    main()

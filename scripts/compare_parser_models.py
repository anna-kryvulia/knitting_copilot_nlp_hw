"""Phase 4 model selection: run the LLM parser with each candidate free model on the same dev patterns.

Records parse success (valid IR that simulates), exact match vs gold, attempts and latency per model.
Writes results/parser_model_comparison.json. Run: python scripts/compare_parser_models.py [case ids...]
"""

import json
import sys
import time

from eval.common import RESULTS_DIR, load_cases
from eval.eval_parser import score_case
from knit_copilot.components import parser

MODELS = [
    "google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free", "nvidia/nemotron-3.5-super-vl:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free", "thinkingmachines/inkling:free", "thinkingmachines/inkling-small:free",
    "recursive/flint-v1.0:free", "xingchen-agi/xing4.0-29b-a4b:free", "dots-studio/dots-3-note-preview:free",
]


def main() -> None:
    ids = sys.argv[1:] or ["parse-004"]
    cases = [c for c in load_cases("parse_cases.jsonl", "all") if c["id"] in ids]
    results = []
    for model in MODELS:
        for c in cases:
            t = time.time()
            meta = {}

            def run(text, model=model):
                out = parser.run(parser.ParserInput(text=text, mode="llm", model=model))
                meta.update(method=out.method, attempts=out.attempts)
                return out
            s = score_case(c, run)
            row = {"model": model, "case": c["id"], "tags": c["tags"][:2], "seconds": round(time.time() - t, 1),
                   "parse_success": s["parse_success"], "exact_match": s["exact_match"],
                   "row_agreement": round(s["rows_matched_count"] / s["rows_gold"], 3), "why": s["first_diff"], **meta}
            results.append(row)
            print(json.dumps(row), flush=True)
    (RESULTS_DIR / "parser_model_comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

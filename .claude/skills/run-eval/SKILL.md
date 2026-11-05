---
name: run-eval
description: Run one or all Knitting Copilot component evaluations, compare with the previous version, do error analysis on failures, and update docs/05_evaluation.md. Use after any change to a component, prompt, retrieval setting, or eval data.
---

# Run an eval and analyse it

CRISP-DM phase: **5. Evaluation**.

## Steps

1. Decide scope: one component (`python -m eval.eval_<name> --split dev`) or all
   (`python -m eval.run_all --split dev`). Use `--split test` only for the final reported numbers.
2. Run it. If the free model hits rate limits, wait and re-run — the LLM cache makes reruns resume.
3. Compare with the previous `results/<name>_<split>.json` (keep the old one as `results/history/`).
   Show a small table: metric | previous | now | target. Show synthetic and Ravelry numbers separately;
   a big gap between them is a finding to explain (e.g. real patterns use free-form notes, imperial units).
4. **Error analysis** (required when a metric is below target):
   - Read 5–10 failures from `failures`.
   - Group them by cause, e.g. unknown abbreviation / nested repeat parsed wrong / "work until" length missed /
     imperial unit not converted / model ignored the JSON schema / judge too strict / gold label wrong.
   - For each group: count, one example, proposed fix.
5. **For LLM-judge metrics:** check agreement with the human-labelled subset
   (`data/eval/judge_calibration.jsonl`). If agreement < 0.8, fix the judge rubric before trusting the scores.
6. Update `docs/05_evaluation.md`: the metrics table, the iteration row (version, change, effect),
   and the error-analysis notes.
7. Propose **one** next change (one variable at a time). Don't apply it unless asked.
8. Run `crisp-dm-checkpoint`.

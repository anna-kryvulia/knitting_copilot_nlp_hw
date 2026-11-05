---
name: add-component
description: Scaffold a new Knitting Copilot component (module + Pydantic I/O + prompt file + unit test + eval script) following the project conventions. Use when adding or rebuilding any component in src/knit_copilot/components/.
---

# Add a component

CRISP-DM phase: **4. Modeling** (and prepares **5. Evaluation**).

## Inputs to confirm
- Component name (snake_case), purpose, input, output.
- Does it call the LLM? Which tools (if any)?
- Which eval file in `data/eval/` covers it, and which metrics (see table in step 5).

## Steps

1. **Read first:** `AGENTS.md` §2, §4 and §7, `docs/CONVENTIONS.md` "Component contract", and one existing
   component as an example (if any).
2. **Create `src/knit_copilot/components/<name>.py`:**
   - `<Name>Input` and `<Name>Output` Pydantic models.
   - `def run(inp: <Name>Input) -> <Name>Output` with the docstring template
     (Purpose / Input / Output / Model calls / Tool calls).
   - LLM calls only via `knit_copilot.llm.chat_json(llm.render(prompt_name, **vars), schema=...)`.
   - No LangGraph imports.
3. **Create `prompts/<name>.md`** (if it uses the LLM) with the sections System / User template /
   Output schema. The output schema must match `<Name>Output`.
4. **Create `tests/test_<name>.py`:** test the deterministic parts; mock `knit_copilot.llm` for the rest.
5. **Create `eval/eval_<name>.py`:**
   - Loads cases from `data/eval/*.jsonl` filtered by `component` and `--split`.
   - Calls `run()` for each case, computes metrics, writes `results/<name>_<split>.json`
     in the format from `docs/CONVENTIONS.md`, including a `failures` list.
   - Report metrics `overall` and `by_source` (synthetic vs ravelry) where both exist.
   - Suggested metrics:
     | component | metrics |
     |---|---|
     | router | accuracy, macro-F1, confusion matrix |
     | setup_agent | tool-choice accuracy, argument accuracy, final project-state match, turns to complete |
     | kb lookup / retriever | exact-lookup accuracy, Recall@k, MRR (BM25 vs dense vs hybrid) |
     | parser | parse success rate, row exact match, op-level F1, count agreement after simulation (LLM vs grammar) |
     | units | conversion accuracy |
     | simulator / gauge / charts / tracker / project | unit tests vs gold; gauge: count error, finished-size error (cm), repeat preservation; charts: cell accuracy |
     | explainer | fact coverage, faithfulness (no claims contradicting the IR), judge 1–5 calibrated on human labels |
     | yarn_linker | top-1 accuracy, "no match" precision |
     | yarn_advisor | weight-class accuracy, needle size within range, advice correctness (judge) |
     | rewriter | re-parse success, count match after simulation, style similarity to the original |
6. **Register** the eval in `eval/run_all.py`.
7. **Wire** the component into `graph.py` only after its eval runs.
8. Run `pytest -q` and `python -m eval.eval_<name> --split dev`. Report the numbers.
9. Run the `crisp-dm-checkpoint` skill.

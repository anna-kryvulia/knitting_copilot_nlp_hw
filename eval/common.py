"""Shared helpers for eval scripts: load cases, write results in the format of docs/CONVENTIONS.md."""

import datetime as dt
import json
from pathlib import Path

from knit_copilot.config import ROOT, settings

EVAL_DIR = ROOT / "data" / "eval"
RESULTS_DIR = ROOT / "results"


def load_cases(filename: str, split: str | None = None) -> list[dict]:
    cases = [json.loads(line) for line in open(EVAL_DIR / filename, encoding="utf-8")]
    return [c for c in cases if split in (None, "all") or c["split"] == split]


def write_results(component: str, split: str, version: str, metrics: dict, n: int, failures: list[dict],
                  model: str | None = None, extra: dict | None = None) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{component}_{split}.json"
    data = {"component": component, "split": split, "version": version,
            "model": model or "none", "date": dt.date.today().isoformat(),
            "metrics": metrics, "n": n, "failures": failures, **(extra or {})}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def app_model() -> str:
    return settings.llm_model

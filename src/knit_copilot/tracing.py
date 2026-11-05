"""Per-node trace records for debugging, the demo video, and latency metrics.

Each graph node wraps its work in `with trace("node_name", state_summary) as t: ...; t.output = ...`.
Records are appended to .cache/traces/<thread_id>.jsonl and kept in memory for the UI.
"""

import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

from knit_copilot.config import ROOT

TRACE_DIR = ROOT / ".cache" / "traces"
_memory: dict[str, list[dict[str, Any]]] = {}


@dataclass
class TraceRecord:
    thread_id: str
    node: str
    input: Any
    output: Any = None
    error: str | None = None
    latency_s: float = 0.0
    ts: float = field(default_factory=time.time)


@contextmanager
def trace(thread_id: str, node: str, inp: Any) -> Iterator[TraceRecord]:
    rec = TraceRecord(thread_id=thread_id, node=node, input=inp)
    t0 = time.perf_counter()
    try:
        yield rec
    except Exception as e:
        rec.error = f"{type(e).__name__}: {e}"
        raise
    finally:
        rec.latency_s = round(time.perf_counter() - t0, 3)
        d = asdict(rec)
        _memory.setdefault(thread_id, []).append(d)
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        with open(TRACE_DIR / f"{thread_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")


def get_trace(thread_id: str) -> list[dict[str, Any]]:
    return _memory.get(thread_id, [])

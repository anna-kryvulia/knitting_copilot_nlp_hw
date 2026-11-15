"""The only module that calls an LLM.

Purpose: one robust entry point for free OpenRouter models — retry with backoff, fallback to other
models, on-disk response cache, and JSON output validated against a Pydantic schema.
Input: chat messages (+ optional tools / schema). Output: text, a tool-call message, or a validated model.
"""

import concurrent.futures as cf
import hashlib
import json
import logging
import re
import time
from typing import Any, TypeVar

import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from knit_copilot.config import settings
from knit_copilot.tracing import note_llm_call

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_clients: dict[tuple[str, str], OpenAI] = {}


class LLMConfigError(RuntimeError):
    """The LLM is not configured (e.g. no API key); retrying will not help."""


class LLMTimeout(RuntimeError):
    """The caller's time budget ran out before any model answered."""


# Requests run in worker threads so a hard deadline can be enforced: OpenRouter keeps slow connections
# alive with "processing" comments, so the HTTP read timeout alone never fires (a request once hung 22 min).
_pool = cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm")


def _call_summary(out: dict, messages: list[dict], cached: bool) -> dict:
    """Short record of one model call for the trace (no prompt text beyond the last message's start)."""
    last = messages[-1].get("content") or ""
    return {"model": out.get("model"), "cached": cached, "latency_s": 0.0 if cached else out.get("latency_s"),
            "tokens": (out.get("usage") or {}).get("total_tokens"), "last_message": str(last)[:160],
            "tool_calls": [tc["function"]["name"] for tc in out.get("tool_calls") or []],
            "answer": (out.get("content") or "")[:200]}


def client(model: str | None = None) -> OpenAI:
    """OpenAI-compatible client; the judge model uses the judge endpoint (JUDGE_BASE_URL / JUDGE_API_KEY)."""
    judge = model is not None and model == settings.judge_model
    url, key = ((settings.judge_base_url, settings.judge_api_key) if judge
                else (settings.base_url, settings.openrouter_api_key))
    if (url, key) not in _clients:
        if not key:
            raise LLMConfigError("No API key: set LLM_API_KEY (or OPENROUTER_API_KEY) in .env, see .env.example.")
        _clients[(url, key)] = OpenAI(base_url=url, api_key=key, timeout=settings.timeout_s, max_retries=0)
    return _clients[(url, key)]


# ---------- prompts ----------

def load_prompt(name: str) -> dict[str, str]:
    """Read prompts/<name>.md and return its '## <Section>' blocks, keyed by lower-case section name."""
    text = (settings.prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M):
        sections[m.group(1).strip().lower()] = m.group(2).strip()
    return sections


# ---------- cache ----------

def _cache_path(key_obj: dict[str, Any]):
    key = hashlib.sha256(json.dumps(key_obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return settings.cache_dir / f"{key[:2]}/{key}.json"


# ---------- core call ----------

def chat(messages: list[dict[str, Any]], *, model: str | None = None, tools: list[dict] | None = None,
         temperature: float = 0.0, max_tokens: int = 2048, use_cache: bool | None = None,
         fallback: bool = True, deadline: float | None = None) -> dict[str, Any]:
    """Call the chat API and return the assistant message as a dict
    ({"content": str | None, "tool_calls": [...] | None, "model": str}).

    Tries `model` (default LLM_MODEL), then LLM_FALLBACK_MODELS. Server errors and empty/cut-off answers are
    retried with backoff; a rate-limited or timed-out model is retried at most once before moving on.
    `deadline` (time.monotonic() value) is a hard stop for the whole call: raises LLMTimeout.
    """
    models = [model or settings.llm_model]
    if fallback:
        models += [m for m in settings.fallback_models if m != models[0]]
    use_cache = settings.llm_cache if use_cache is None else use_cache
    params = {"temperature": temperature, "max_tokens": max_tokens}
    if tools:
        params["tools"] = tools

    last_err: Exception | None = None
    base_params = params
    for m in models:
        params = dict(base_params)
        if settings.reasoning_effort and m != settings.judge_model:    # app endpoint only
            params["reasoning_effort"] = settings.reasoning_effort
        path = _cache_path({"model": m, "messages": messages, **params})
        if use_cache and path.exists():
            out = json.loads(path.read_text(encoding="utf-8"))
            note_llm_call(_call_summary(out, messages, cached=True))
            return out

        for attempt in range(settings.max_retries):
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining < 1:
                raise LLMTimeout(f"time budget used up (last error: {last_err})")
            per_request = settings.timeout_s if remaining is None else min(settings.timeout_s, remaining)
            try:
                t0 = time.perf_counter()
                future = _pool.submit(client(m).chat.completions.create, model=m, messages=messages, **params)
                try:
                    resp = future.result(timeout=per_request)
                except cf.TimeoutError:
                    raise openai.APITimeoutError(request=None) from None
                choice = resp.choices[0]
                msg = choice.message
                if choice.finish_reason == "length":
                    raise ValueError(f"response cut off at max_tokens={max_tokens}")
                out = {
                    "content": msg.content,
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls] if msg.tool_calls else None,
                    "model": m,
                    "latency_s": round(time.perf_counter() - t0, 3),
                    "usage": resp.usage.model_dump() if resp.usage else None,
                }
                if out["content"] is None and not out["tool_calls"]:
                    raise ValueError("empty response")
                if use_cache:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
                note_llm_call(_call_summary(out, messages, cached=False))
                return out
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                    openai.InternalServerError, ValueError) as e:
                last_err = e
                busy = isinstance(e, (openai.RateLimitError, openai.APITimeoutError))
                if busy and attempt >= 1:          # a busy free model rarely recovers within seconds
                    log.warning("LLM %s still %s, trying next model", m, type(e).__name__)
                    break
                wait = 2 ** attempt
                if deadline is not None:
                    wait = min(wait, max(0.0, deadline - time.monotonic() - 1))
                log.warning("LLM %s failed (%s), attempt %d/%d, retry in %.0fs",
                            m, type(e).__name__, attempt + 1, settings.max_retries, wait)
                time.sleep(wait)
            except openai.APIStatusError as e:  # 4xx other than 429: model unavailable etc. → next model
                last_err = e
                log.warning("LLM %s returned %s, trying next model", m, e.status_code)
                break
    raise RuntimeError(f"All models failed: {models}") from last_err


# ---------- structured output ----------

def _extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start > 0:
        text = text[start:]
    return json.loads(text)


def chat_json(messages: list[dict[str, Any]], schema: type[T], *, model: str | None = None,
              temperature: float = 0.0, max_tokens: int = 12000, fallback: bool = True,
              deadline: float | None = None) -> T:
    """Call the LLM and validate its JSON answer against `schema`. Re-asks once with the error on failure."""
    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    msgs = list(messages)
    msgs[0] = {**msgs[0], "content": f"{msgs[0]['content']}\n\nRespond with ONLY a JSON object matching this "
                                     f"JSON schema, no prose:\n{schema_hint}"}
    for attempt in range(2):
        out = chat(msgs, model=model, temperature=temperature, max_tokens=max_tokens, fallback=fallback,
                   deadline=deadline)
        try:
            return schema.model_validate(_extract_json(out["content"] or ""))
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("Invalid JSON from %s (attempt %d): %s", out["model"], attempt + 1, e)
            msgs = msgs + [{"role": "assistant", "content": out["content"] or ""},
                           {"role": "user", "content": f"That was not valid JSON for the schema: {e}. "
                                                       f"Return only the corrected JSON object."}]
    raise ValueError(f"Model did not return valid {schema.__name__} JSON")


def render(prompt_name: str, **vars: Any) -> list[dict[str, str]]:
    """Build [system, user] messages from prompts/<prompt_name>.md, filling {placeholders} in the user template."""
    p = load_prompt(prompt_name)
    system = p["system"]
    for k, v in vars.items():              # plain replacement: system prompts may contain JSON braces
        system = system.replace("{" + k + "}", str(v))
    return [{"role": "system", "content": system},
            {"role": "user", "content": p["user template"].format(**vars)}]

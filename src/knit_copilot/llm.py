"""The only module that calls an LLM.

Purpose: one robust entry point for free OpenRouter models — retry with backoff, fallback to other
models, on-disk response cache, and JSON output validated against a Pydantic schema.
Input: chat messages (+ optional tools / schema). Output: text, a tool-call message, or a validated model.
"""

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

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
        _client = OpenAI(base_url=settings.base_url, api_key=settings.openrouter_api_key,
                         timeout=settings.timeout_s, max_retries=0)
    return _client


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
         temperature: float = 0.0, max_tokens: int = 2048, use_cache: bool | None = None) -> dict[str, Any]:
    """Call the chat API and return the assistant message as a dict
    ({"content": str | None, "tool_calls": [...] | None, "model": str}).

    Tries `model` (default LLM_MODEL), then LLM_FALLBACK_MODELS, retrying each with exponential backoff
    on rate limits / server errors.
    """
    models = [model or settings.llm_model] + [m for m in settings.fallback_models if m != (model or settings.llm_model)]
    use_cache = settings.llm_cache if use_cache is None else use_cache
    params = {"temperature": temperature, "max_tokens": max_tokens}
    if tools:
        params["tools"] = tools

    last_err: Exception | None = None
    for m in models:
        path = _cache_path({"model": m, "messages": messages, **params})
        if use_cache and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        for attempt in range(settings.max_retries):
            try:
                t0 = time.perf_counter()
                resp = client().chat.completions.create(model=m, messages=messages, **params)
                msg = resp.choices[0].message
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
                return out
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                    openai.InternalServerError, ValueError) as e:
                last_err = e
                wait = 2 ** attempt
                log.warning("LLM %s failed (%s), attempt %d/%d, retry in %ss",
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
              temperature: float = 0.0) -> T:
    """Call the LLM and validate its JSON answer against `schema`. Re-asks once with the error on failure."""
    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    msgs = list(messages)
    msgs[0] = {**msgs[0], "content": f"{msgs[0]['content']}\n\nRespond with ONLY a JSON object matching this "
                                     f"JSON schema, no prose:\n{schema_hint}"}
    for attempt in range(2):
        out = chat(msgs, model=model, temperature=temperature)
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
    return [{"role": "system", "content": p["system"]},
            {"role": "user", "content": p["user template"].format(**vars)}]

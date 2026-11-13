"""Read-only Ravelry API client with an on-disk cache.

Purpose: fetch yarn and pattern metadata for data understanding/preparation. Used only by data scripts,
never by the running app.
Input: search parameters or ids. Output: parsed JSON (dict).
Credentials: RAVELRY_USERNAME / RAVELRY_PASSWORD (read-only Basic Auth) from .env.
Cache: .cache/ravelry/ (git-ignored) so surveys are reproducible and don't re-hit the API.
"""

import hashlib
import json
import logging
import time
from typing import Any

import httpx
from dotenv import dotenv_values

from knit_copilot.config import ROOT

log = logging.getLogger(__name__)
BASE_URL = "https://api.ravelry.com"
CACHE_DIR = ROOT / ".cache" / "ravelry"


def _auth() -> tuple[str, str]:
    env = dotenv_values(ROOT / ".env")
    user, pwd = env.get("RAVELRY_USERNAME"), env.get("RAVELRY_PASSWORD")
    if not user or not pwd:
        raise RuntimeError("RAVELRY_USERNAME / RAVELRY_PASSWORD are not set in .env")
    return user, pwd


def get(path: str, params: dict[str, Any] | None = None, use_cache: bool = True) -> dict[str, Any]:
    """GET {BASE_URL}{path} with params; cached by (path, params)."""
    params = params or {}
    key = hashlib.sha256(json.dumps([path, params], sort_keys=True).encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    for attempt in range(4):
        r = httpx.get(f"{BASE_URL}{path}", params=params, auth=_auth(), timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            wait = 2 ** attempt
            log.warning("Ravelry %s -> %s, retry in %ss", path, r.status_code, wait)
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)  # be polite to the API
        return data
    raise RuntimeError(f"Ravelry request failed after retries: {path}")


def search_yarns(query: str, page_size: int = 100, page: int = 1, **filters: Any) -> dict[str, Any]:
    return get("/yarns/search.json", {"query": query, "page_size": page_size, "page": page, **filters})


def yarns_by_ids(ids: list[int]) -> dict[str, Any]:
    """Full yarn records (fibres, needles, gauge) for up to ~50 ids per call."""
    return get("/yarns.json", {"ids": " ".join(str(i) for i in sorted(ids))})


def search_patterns(page_size: int = 50, page: int = 1, **filters: Any) -> dict[str, Any]:
    return get("/patterns/search.json", {"page_size": page_size, "page": page, **filters})


def patterns_by_ids(ids: list[int]) -> dict[str, Any]:
    return get("/patterns.json", {"ids": " ".join(str(i) for i in sorted(ids))})

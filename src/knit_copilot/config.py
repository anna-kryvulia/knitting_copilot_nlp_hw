"""Settings loaded from .env. The single source of configuration for the app and evals."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _list(name: str) -> list[str]:
    return [m.strip() for m in os.getenv(name, "").split(",") if m.strip()]


@dataclass(frozen=True)
class Settings:
    # any OpenAI-compatible endpoint; OpenRouter by default (LLM_API_KEY falls back to OPENROUTER_API_KEY)
    openrouter_api_key: str = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
    base_url: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    # the judge may live on another provider (it must be a different model family than the app model)
    judge_base_url: str = os.getenv("JUDGE_BASE_URL") or os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    judge_api_key: str = os.getenv("JUDGE_API_KEY") or (
        os.getenv("OPENROUTER_API_KEY", "") if "openrouter.ai" in (os.getenv("JUDGE_BASE_URL") or "")
        else os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY", ""))
    llm_model: str = os.getenv("LLM_MODEL", "nvidia/nemotron-3.5-super-vl:free")
    fallback_models: list[str] = field(default_factory=lambda: _list("LLM_FALLBACK_MODELS"))
    judge_model: str = os.getenv("JUDGE_MODEL", "dots-studio/dots-3-note-preview:free")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    llm_cache: bool = os.getenv("LLM_CACHE", "1") == "1"
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "4"))
    timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "60"))
    # thinking models (e.g. Gemini 3.x): hidden reasoning counts against max_tokens; "low" keeps it short
    reasoning_effort: str = os.getenv("LLM_REASONING_EFFORT", "")
    # free tiers limit requests per minute: wait at least this long between two API requests (0 = no pause)
    min_interval_s: float = float(os.getenv("LLM_MIN_INTERVAL_S", "0"))
    parse_budget_s: float = float(os.getenv("PARSE_TIME_BUDGET_S", "60"))
    db_path: Path = ROOT / os.getenv("DB_PATH", "data/knit.db")
    prompts_dir: Path = ROOT / "prompts"
    cache_dir: Path = ROOT / ".cache" / "llm"


settings = Settings()

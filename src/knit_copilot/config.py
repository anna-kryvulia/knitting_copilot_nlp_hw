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
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = os.getenv("LLM_MODEL", "google/gemma-4-31b-it:free")
    fallback_models: list[str] = field(default_factory=lambda: _list("LLM_FALLBACK_MODELS"))
    judge_model: str = os.getenv("JUDGE_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    llm_cache: bool = os.getenv("LLM_CACHE", "1") == "1"
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "4"))
    timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "60"))
    db_path: Path = ROOT / os.getenv("DB_PATH", "data/knit.db")
    prompts_dir: Path = ROOT / "prompts"
    cache_dir: Path = ROOT / ".cache" / "llm"


settings = Settings()

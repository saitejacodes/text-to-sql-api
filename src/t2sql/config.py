"""Runtime configuration, read from environment variables / .env (prefix T2SQL_)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="T2SQL_", env_file=".env", extra="ignore")

    # LLM provider: any OpenAI-compatible chat-completions endpoint (Ollama, Groq, OpenAI, vLLM).
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5-coder:7b"
    llm_api_key: str = Field(default="ollama", repr=False)
    llm_timeout_s: float = 120.0
    llm_max_concurrency: int = 2
    llm_cache_path: Path = Path(".cache/llm.sqlite")

    # Pipeline
    n_candidates: int = 5  # self-consistency samples (1 = greedy only)
    candidate_temperature: float = 0.7
    max_repair_rounds: int = 2
    use_value_hints: bool = True

    # Sandbox
    query_timeout_s: float = 5.0
    max_rows: int = 1000

    # API: databases the service is allowed to query, name -> sqlite path
    # Comma-separated keys; when set, every /v1 request needs an `X-API-Key` header.
    api_keys: str = Field(default="", repr=False)
    databases_dir: Path = Path("examples")


@lru_cache
def get_settings() -> Settings:
    return Settings()

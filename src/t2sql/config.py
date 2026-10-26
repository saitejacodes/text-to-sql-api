"""Runtime configuration, read from environment variables / .env (prefix T2SQL_)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# OpenAI-compatible chat-completions endpoints, so a provider is one setting, not a new client.
PROVIDER_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="T2SQL_", env_file=".env", extra="ignore")

    # LLM provider: any OpenAI-compatible chat-completions endpoint (Ollama, Groq, OpenAI, vLLM).
    # `llm_provider` picks a known base URL; an explicit `llm_base_url` always wins.
    llm_provider: str = ""
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5-coder:7b"
    llm_api_key: str = Field(default="ollama", repr=False)
    llm_timeout_s: float = 120.0
    llm_max_concurrency: int = 2
    llm_max_retries: int = 6  # lower it for a live demo so a dead provider fails in seconds
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

    # Public web API (/api/*): browser origins allowed by CORS (comma-separated) and the
    # per-IP rate limit on /api/query, in `limits` notation ("10/minute").
    allowed_origins: str = ""
    rate_limit: str = "10/minute"
    git_sha: str = Field("dev", validation_alias=AliasChoices("T2SQL_GIT_SHA", "RENDER_GIT_COMMIT"))

    @model_validator(mode="after")
    def _apply_provider(self) -> Settings:
        provider = self.llm_provider.strip().lower()
        if provider:
            if provider not in PROVIDER_BASE_URLS:
                raise ValueError(
                    f"unknown llm_provider '{provider}'; use one of {sorted(PROVIDER_BASE_URLS)}"
                )
            if "llm_base_url" not in self.model_fields_set:
                self.llm_base_url = PROVIDER_BASE_URLS[provider]
        return self

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

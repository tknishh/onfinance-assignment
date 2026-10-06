from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    gen_provider: Literal["groq", "openai_compat"] = "groq"
    gen_model: str = "openai/gpt-oss-120b"
    fast_model: str = "openai/gpt-oss-20b"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    reasoning_effort: Literal["low", "medium", "high"] = "low"
    gen_max_tokens: int = 4096
    temperature: float = 0.2
    max_concurrency: int = 8
    max_repair_attempts: int = 2
    kroki_url: str = "http://localhost:8000"
    # Empty = disabled (do not send diagrams to a third party). Set to
    # https://kroki.io only when intentional.
    kroki_fallback_url: str = ""
    db_url: str = "sqlite:///data/app.db"
    cache_dir: str = "data/cache"
    judge_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

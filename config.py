"""Application configuration for the product comparison agent backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables with reasonable defaults."""

    model_config = SettingsConfigDict(env_file=(".env",), env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "staging", "production"] = Field(default="development")

    # Grok API configuration
    grok_api_key: str = Field(default="", validation_alias="GROK_API_KEY")
    grok_base_url: str = Field(default="https://api.x.ai/v1", validation_alias="GROK_BASE_URL")
    grok_timeout_seconds: float = Field(default=12.0)
    grok_max_retries: int = Field(default=2)
    grok_connect_timeout_seconds: float = Field(default=4.0)

    # Budget / workflow controls
    max_api_calls_per_comparison: int = Field(default=8)
    workflow_timeout_seconds: float = Field(default=32.0)
    step_timeout_seconds: float = Field(default=15.0)
    extraction_timeout_seconds: float = Field(default=8.0)
    extraction_max_concurrency: int = Field(default=5)

    # Cache configuration
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cache_enabled: bool = Field(default=True)
    metrics_ttl_seconds: int = Field(default=60 * 60 * 24 * 90, ge=0)
    product_ttl_seconds: int = Field(default=60 * 60 * 12, ge=0)
    comparison_ttl_seconds: int = Field(default=60 * 60 * 24, ge=0)

    # Logging / telemetry
    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=False)

    # Feature toggles
    allow_claude_extraction: bool = Field(default=False)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()

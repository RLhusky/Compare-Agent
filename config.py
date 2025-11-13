"""Application configuration for the product comparison agent backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables with reasonable defaults."""

    model_config = SettingsConfigDict(env_file=(".env",), env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "staging", "production"] = Field(default="development")

    # OpenRouter / GLM 4.6 configuration with Cerebras routing
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL")
    glm_model: str = Field(default="z-ai/glm-4.6", validation_alias="GLM_MODEL")
    openrouter_routing: dict[str, Any] | None = Field(
        default=None,
        validation_alias="OPENROUTER_ROUTING",
    )
    glm_timeout_seconds: float = Field(default=8.0, validation_alias="GLM_TIMEOUT_SECONDS")
    glm_max_retries: int = Field(default=0, validation_alias="GLM_MAX_RETRIES")
    glm_connect_timeout_seconds: float = Field(default=2.0)
    glm_reasoning_effort: str = Field(default="low", validation_alias="GLM_REASONING_EFFORT")
    brave_api_key: str = Field(default="", validation_alias="BRAVE_API_KEY")
    brave_max_results: int = Field(default=5, validation_alias="BRAVE_MAX_RESULTS")

    # Legacy aliases for backward compatibility (will use GLM values if not set)
    perplexity_api_key: str = Field(default="", validation_alias="PERPLEXITY_API_KEY")
    perplexity_base_url: str = Field(default="", validation_alias="PERPLEXITY_BASE_URL")
    sonar_model: str = Field(default="", validation_alias="SONAR_MODEL")
    sonar_timeout_seconds: float = Field(default=8.0, validation_alias="SONAR_TIMEOUT_SECONDS")
    sonar_max_retries: int = Field(default=2, validation_alias="SONAR_MAX_RETRIES")

    # Budget / workflow controls
    max_api_calls_per_comparison: int = Field(default=8)
    workflow_timeout_seconds: float = Field(default=30.0)
    step_timeout_seconds: float = Field(default=12.0)
    extraction_timeout_seconds: float = Field(default=10.0)
    extraction_max_concurrency: int = Field(default=20)
    a1_search_budget: int = Field(default=6, validation_alias="A1_SEARCH_BUDGET")
    b_search_budget_per_agent: int = Field(default=1, validation_alias="B_SEARCH_BUDGET_PER_AGENT")
    max_total_searches: int = Field(default=40, validation_alias="MAX_TOTAL_SEARCHES")

    # Cache configuration
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cache_enabled: bool = Field(default=True)
    metrics_ttl_seconds: int = Field(default=60 * 60 * 24 * 90, ge=0)
    product_ttl_seconds: int = Field(default=60 * 60 * 12, ge=0)
    comparison_ttl_seconds: int = Field(default=60 * 60 * 24, ge=0)
    image_search_enabled: bool = Field(default=False, validation_alias="IMAGE_SEARCH_ENABLED")

    # Logging / telemetry
    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=False)

    # Feature toggles
    allow_claude_extraction: bool = Field(default=False)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()

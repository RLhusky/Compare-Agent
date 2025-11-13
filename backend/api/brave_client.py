"""Brave Search API client for web_search tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.logging_config import get_logger
from config import Settings, get_settings

logger = get_logger(__name__)


class BraveClientError(RuntimeError):
    """Base exception for Brave API failures."""


@dataclass
class BraveClient:
    """Async client for the Brave Search REST API."""

    settings: Settings = field(default_factory=get_settings)
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        api_key = self.settings.brave_api_key
        if not api_key:
            logger.error("brave_api_key_missing - search tool calls will fail")
            raise BraveClientError("Brave API key is required but not configured")

        self._client = httpx.AsyncClient(
            base_url="https://api.search.brave.com",
            headers={
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(timeout=6.0, connect=2.0),
        )
        logger.info(
            "brave_client_initialized",
            max_results=self.settings.brave_max_results,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Execute a Brave web search and return simplified result dicts."""

        if not self._client:
            raise BraveClientError("HTTP client not initialized")

        params = {
            "q": query,
            "count": self.settings.brave_max_results,
            "search_lang": "en",
        }

        logger.info("brave_search_request", query=query[:100])

        try:
            response = await self._client.get("/res/v1/web/search", params=params)
        except httpx.TimeoutException as exc:
            logger.warning("brave_search_timeout", error=str(exc))
            raise BraveClientError(f"Brave search timeout: {exc}") from exc
        except httpx.RequestError as exc:
            logger.warning("brave_search_error", error=str(exc))
            raise BraveClientError(f"Brave request error: {exc}") from exc

        if response.status_code >= 400:
            logger.error(
                "brave_search_failed",
                status_code=response.status_code,
                response_text=response.text[:500],
            )
            raise BraveClientError(f"Brave API error: {response.status_code}")

        data = response.json()
        results = data.get("web", {}).get("results", []) or []

        simplified = []
        for item in results:
            simplified.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description") or item.get("snippet", ""),
                }
            )

        logger.info("brave_search_success", result_count=len(simplified))
        return simplified


__all__ = ["BraveClient", "BraveClientError"]

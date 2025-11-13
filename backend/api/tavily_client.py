"""Tavily search API client for web_search tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.logging_config import get_logger
from config import Settings, get_settings

logger = get_logger(__name__)


class TavilyClientError(RuntimeError):
    """Base exception for Tavily API failures."""


@dataclass
class TavilyClient:
    """Async client for Tavily search API."""

    settings: Settings = field(default_factory=get_settings)
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.settings.tavily_api_key:
            logger.error("tavily_api_key_missing - search tool calls will fail")
            raise TavilyClientError("Tavily API key is required but not configured")

        self._client = httpx.AsyncClient(
            base_url="https://api.tavily.com",
            headers={
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout=10.0, connect=4.0),
        )
        logger.info(
            "tavily_client_initialized",
            search_depth=self.settings.tavily_search_depth,
            max_results=self.settings.tavily_max_results,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Execute a web search and return list of result dicts with 'title', 'url', 'content'."""
        if not self._client:
            raise TavilyClientError("HTTP client not initialized")

        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": self.settings.tavily_max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        logger.info("tavily_search_request", query=query[:100])

        try:
            response = await self._client.post("/search", json=payload)

            if response.status_code >= 400:
                logger.error(
                    "tavily_search_failed",
                    status_code=response.status_code,
                    response_text=response.text[:500],
                )
                raise TavilyClientError(f"Tavily API error: {response.status_code}")

            data = response.json()
            results = data.get("results", [])

            logger.info("tavily_search_success", result_count=len(results))

            return [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                }
                for item in results
            ]

        except httpx.TimeoutException as exc:
            logger.warning("tavily_search_timeout", error=str(exc))
            raise TavilyClientError(f"Tavily search timeout: {exc}") from exc
        except httpx.RequestError as exc:
            logger.warning("tavily_search_error", error=str(exc))
            raise TavilyClientError(f"Tavily request error: {exc}") from exc
        except Exception as exc:
            logger.error("tavily_search_unexpected_error", error=str(exc), error_type=type(exc).__name__)
            raise TavilyClientError(f"Unexpected Tavily error: {exc}") from exc


__all__ = ["TavilyClient", "TavilyClientError"]

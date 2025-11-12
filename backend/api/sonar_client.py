"""HTTP client wrapper for Perplexity Sonar API interactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.logging_config import get_logger
from config import Settings, get_settings

logger = get_logger(__name__)


class SonarClientError(RuntimeError):
    """Base exception for Sonar client failures."""


class SonarRateLimitError(SonarClientError):
    """Raised when rate limit responses are received."""


class SonarTimeoutError(SonarClientError):
    """Raised when Sonar API does not respond within budget."""


ErrorMap: dict[int, type[SonarClientError]] = {
    401: SonarClientError,
    403: SonarClientError,
    429: SonarRateLimitError,
}


def _classify_error(status_code: int) -> type[SonarClientError]:
    return ErrorMap.get(status_code, SonarClientError)


def _extract_search_steps(payload: dict[str, Any]) -> int:
    usage = payload.get("usage") or {}
    for key in ("search_steps", "searches", "search_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
    search_meta = usage.get("search") or {}
    if isinstance(search_meta, dict):
        for key in ("steps", "count"):
            value = search_meta.get(key)
            if isinstance(value, int):
                return value
    return 0


@dataclass
class SonarClient:
    """Async client for Perplexity Sonar endpoints."""

    settings: Settings = field(default_factory=get_settings)
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.settings.perplexity_api_key:
            logger.warning("perplexity_api_key_missing")

        timeout = httpx.Timeout(
            timeout=self.settings.sonar_timeout_seconds,
            connect=self.settings.grok_connect_timeout_seconds,
        )
        self._client = httpx.AsyncClient(
            base_url=self.settings.perplexity_base_url,
            headers={
                "Authorization": f"Bearer {self.settings.perplexity_api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._client:
            raise SonarClientError("HTTP client not initialized")

        @retry(
            retry=retry_if_exception_type((httpx.RequestError, SonarRateLimitError)),
            stop=stop_after_attempt(self.settings.sonar_max_retries + 1),
            wait=wait_exponential(multiplier=0.8, min=1, max=6),
        )
        async def send_request() -> dict[str, Any]:
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:  # pragma: no cover - network call
                raise SonarTimeoutError(str(exc)) from exc
            except httpx.RequestError as exc:  # pragma: no cover - network call
                logger.warning("sonar_request_error", error=str(exc))
                raise

            if response.status_code >= 400:
                logger.warning(
                    "sonar_request_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                error_cls = _classify_error(response.status_code)
                if response.status_code == 429:
                    raise SonarRateLimitError(response.text)
                raise error_cls(response.text)

            response_payload = response.json()
            logger.debug(
                "sonar_response_received",
                finish_reason=response_payload.get("choices", [{}])[0].get("finish_reason"),
            )
            return response_payload

        try:
            return await send_request()
        except RetryError as exc:
            raise SonarClientError("Exceeded maximum retry attempts") from exc

    async def call(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_searches: int,
        timeout_seconds: float,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        model: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Execute a Sonar request and return response payload + search count."""

        payload: dict[str, Any] = {
            "model": model or self.settings.sonar_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "search_options": {
                "max_search_steps": max(1, max_searches),
            },
        }

        logger.info(
            "sonar_request",
            model=payload["model"],
            max_searches=max_searches,
            max_tokens=max_tokens,
        )
        response = await self._post(payload)
        return response, _extract_search_steps(response)


__all__ = ["SonarClient", "SonarClientError"]


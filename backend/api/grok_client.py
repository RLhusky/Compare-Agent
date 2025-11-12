"""HTTP client wrapper for Grok 4 Fast API interactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.logging_config import get_logger
from config import Settings, get_settings

logger = get_logger(__name__)


class GrokClientError(RuntimeError):
    """Base exception for Grok client failures."""


class GrokRateLimitError(GrokClientError):
    """Raised when rate limit responses are received."""


class GrokTimeoutError(GrokClientError):
    """Raised when Grok API does not respond within budget."""


class GrokUnauthorizedError(GrokClientError):
    """Raised when credentials are invalid."""


ErrorMap: dict[int, type[GrokClientError]] = {
    401: GrokUnauthorizedError,
    429: GrokRateLimitError,
}


def _classify_error(status_code: int) -> type[GrokClientError]:
    return ErrorMap.get(status_code, GrokClientError)


@dataclass
class GrokClient:
    """Minimal async client for Grok API usage."""

    settings: Settings = field(default_factory=get_settings)
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.settings.grok_api_key:
            logger.warning("grok_api_key_missing")
        timeout = httpx.Timeout(
            timeout=self.settings.grok_timeout_seconds,
            connect=self.settings.grok_connect_timeout_seconds,
        )
        self._client = httpx.AsyncClient(
            base_url=self.settings.grok_base_url,
            headers={
                "Authorization": f"Bearer {self.settings.grok_api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def _post(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._client:
            raise GrokClientError("HTTP client not initialized")

        @retry(
            retry=retry_if_exception_type((httpx.RequestError, GrokRateLimitError)),
            stop=stop_after_attempt(self.settings.grok_max_retries + 1),
            wait=wait_exponential(multiplier=0.8, min=1, max=6),
        )
        async def send_request() -> dict[str, Any]:
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:  # pragma: no cover - network call
                raise GrokTimeoutError(str(exc)) from exc
            except httpx.RequestError as exc:  # pragma: no cover - network call
                logger.warning("grok_request_error", error=str(exc))
                raise

            if response.status_code >= 400:
                logger.warning(
                    "grok_request_failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                error_cls = _classify_error(response.status_code)
                if response.status_code == 429:
                    raise GrokRateLimitError(response.text)
                raise error_cls(response.text)

            response_payload = response.json()
            logger.debug(
                "grok_response_received",
                finish_reason=response_payload.get("choices", [{}])[0].get("finish_reason"),
            )
            return response_payload

        try:
            return await send_request()
        except RetryError as exc:
            raise GrokClientError("Exceeded maximum retry attempts") from exc

    async def chat_completion(
        self,
        *,
        model: Literal["grok-4-fast-reasoning", "grok-4-fast-non-reasoning"],
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> dict[str, Any]:
        """Execute a Grok chat request."""

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        logger.info("grok_request", model=model, has_tools=bool(tools))
        return await self._post(payload=payload)

    async def reasoning_call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        enable_search: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """Convenience wrapper for reasoning mode calls."""

        tools = [{"type": "web_search"}] if enable_search else None
        tool_choice = "auto" if enable_search else None

        return await self.chat_completion(
            model="grok-4-fast-reasoning",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def non_reasoning_call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> dict[str, Any]:
        """Convenience wrapper for non-reasoning mode calls."""

        return await self.chat_completion(
            model="grok-4-fast-non-reasoning",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

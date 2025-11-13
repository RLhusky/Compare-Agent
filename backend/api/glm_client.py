"""HTTP client wrapper for OpenRouter GLM 4.6 with parallel tool execution."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Iterable

import httpx
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.logging_config import get_logger
from config import Settings, get_settings

logger = get_logger(__name__)


class GlmClientError(RuntimeError):
    """Base exception for OpenRouter GLM client failures."""


class GlmRateLimitError(GlmClientError):
    """Raised when rate limit responses are received."""


class GlmTimeoutError(GlmClientError):
    """Raised when OpenRouter API does not respond within budget."""


ErrorMap: dict[int, type[GlmClientError]] = {
    401: GlmClientError,
    403: GlmClientError,
    429: GlmRateLimitError,
}


def _classify_error(status_code: int) -> type[GlmClientError]:
    return ErrorMap.get(status_code, GlmClientError)


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
class GlmClient:
    """Async client for OpenRouter GLM endpoints."""

    settings: Settings = field(default_factory=get_settings)
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)
    _brave_client: Any | None = field(default=None, init=False, repr=False)
    _brave_cache: dict[str, list[dict[str, Any]]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        api_key = self.settings.openrouter_api_key
        base_url = self.settings.openrouter_base_url or "https://openrouter.ai/api/v1"
        timeout_seconds = self.settings.glm_timeout_seconds or 5.0
        connect_timeout = self.settings.glm_connect_timeout_seconds or 4.0

        if not api_key:
            logger.error("openrouter_api_key_missing")
            raise GlmClientError("OpenRouter API key is required but not configured")

        if not base_url.strip():
            logger.error("openrouter_base_url_missing")
            raise GlmClientError("OpenRouter base URL is required but not configured")

        timeout = httpx.Timeout(timeout=timeout_seconds, connect=connect_timeout)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://comparoo.com",
                "X-Title": "Comparoo",
            },
            timeout=timeout,
        )
        logger.info(
            "glm_client_initialized",
            base_url=base_url,
            model=self.settings.glm_model,
            routing_configured=bool(self.settings.openrouter_routing),
            timeout_seconds=timeout_seconds,
            connect_timeout=connect_timeout,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
        if self._brave_client:
            await self._brave_client.close()

    async def _get_brave_client(self):
        if self._brave_client is None:
            from backend.api.brave_client import BraveClient

            self._brave_client = BraveClient(settings=self.settings)
        return self._brave_client

    def _cache_brave_results(self, query: str, results: list[dict[str, Any]]) -> None:
        if query:
            self._brave_cache[query.lower()] = results

    def _get_cached_results(self, query: str) -> list[dict[str, Any]] | None:
        if not query:
            return None
        return self._brave_cache.get(query.lower())

    def _generate_related_queries(self, query: str) -> list[str]:
        if not query:
            return []

        base = query.lower().replace("$", "").replace("usd", "").replace("in stock", "").strip()
        tokens = [token.strip() for token in re.split(r"[,|/]+", base) if token]
        related: list[str] = []
        if "stand mixer" in base:
            for brand in ("kitchenaid", "cuisinart", "hamilton beach", "bosch", "breville", "wolf"):
                related.append(f"{brand} stand mixer under 500 dollars")
        for token in tokens:
            if token and token not in base:
                related.append(token)
        return related[:3]

    async def _prefetch_related_queries(self, brave_client: Any, query: str) -> None:
        related_queries = self._generate_related_queries(query)
        pending = [rq for rq in related_queries if self._get_cached_results(rq) is None]
        if not pending:
            return

        tasks = [asyncio.create_task(brave_client.search(rq)) for rq in pending]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for rq, result in zip(pending, results):
            if isinstance(result, list):
                self._cache_brave_results(rq, result)

    @staticmethod
    def _is_valid_http_url(url: str) -> bool:
        return isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))

    @staticmethod
    def _summarise_search_results(results: Iterable[dict[str, Any]], limit: int = 8) -> str:
        lines: list[str] = []
        for idx, result in enumerate(results):
            if idx >= limit:
                break
            title = (result.get("title") or "").strip()
            url = (result.get("url") or "").strip()
            snippet = (result.get("snippet") or result.get("content") or "").strip()[:240]
            line = f"- {title or 'Result'}"
            if url:
                line += f" — {url}"
            if snippet:
                line += f"\n  Snippet: {snippet}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _strip_html(text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"(?is)<(script|style)[^>]*>.*?</\\1>", " ", text)
        cleaned = re.sub(r"(?is)<head[^>]*>.*?</head>", " ", cleaned)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    async def _perform_web_fetch(self, url: str, *, max_bytes: int = 20000) -> dict[str, Any]:
        timeout = httpx.Timeout(timeout=min(self.settings.workflow_timeout_seconds, 20.0), connect=4.0)
        headers = {
            "User-Agent": "ComparooBot/1.0 (+https://comparoo.com)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,application/xml;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)

        if response.status_code >= 400:
            logger.warning("glm_web_fetch_http_error", url=url, status_code=response.status_code)
            return {"status": "error", "url": url, "status_code": response.status_code}

        text = (response.text or "")[:max_bytes]
        title_match = re.search(r"(?is)<title>(.*?)</title>", response.text or "")
        title = self._strip_html(title_match.group(1)) if title_match else ""
        content = self._strip_html(text)

        return {
            "status": "ok",
            "url": url,
            "status_code": response.status_code,
            "title": title,
            "content": content[:4000],
        }

    @staticmethod
    async def _immediate_result(content: str) -> str:
        return content

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._client:
            raise GlmClientError("HTTP client not initialized")

        @retry(
            retry=retry_if_exception_type((httpx.RequestError, GlmRateLimitError)),
            stop=stop_after_attempt((self.settings.glm_max_retries or 0) + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        )
        async def send_request() -> dict[str, Any]:
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:  # pragma: no cover - network call
                raise GlmTimeoutError(str(exc)) from exc
            except httpx.RequestError as exc:  # pragma: no cover - network call
                logger.warning("glm_request_error", error=str(exc))
                raise

            request_id = response.headers.get("x-request-id") or response.headers.get("openrouter-request-id")
            if response.status_code >= 400:
                logger.warning(
                    "glm_request_failed",
                    status_code=response.status_code,
                    response=response.text,
                    request_id=request_id,
                )
                error_cls = _classify_error(response.status_code)
                if response.status_code == 429:
                    raise GlmRateLimitError(response.text)
                raise error_cls(response.text)

            try:
                response_payload = response.json()
            except Exception as exc:
                logger.error(
                    "glm_response_json_parse_failed",
                    status_code=response.status_code,
                    response_text=response.text[:500],
                    request_id=request_id,
                )
                raise GlmClientError(f"Failed to parse JSON response: {exc}") from exc

            if "error" in response_payload:
                error_msg = response_payload.get("error", {}).get("message", "Unknown error")
                logger.error(
                    "glm_api_error",
                    error=error_msg,
                    error_type=response_payload.get("error", {}).get("type"),
                    request_id=request_id,
                )
                raise GlmClientError(f"API error: {error_msg}")

            choices = response_payload.get("choices", [])
            finish_reason = choices[0].get("finish_reason") if choices else "unknown"
            logger.debug("glm_response_received", finish_reason=finish_reason, request_id=request_id)
            return response_payload

        try:
            return await send_request()
        except RetryError as exc:
            raise GlmClientError("Exceeded maximum retry attempts") from exc

    async def _execute_tool_call(self, tool_call: dict[str, Any]) -> str:
        tool_type = tool_call.get("type")
        tool_id = tool_call.get("id", "unknown")
        function_payload = tool_call.get("function", {}) or {}
        function_name = function_payload.get("name") or tool_type or ""

        arguments = function_payload.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                logger.warning("glm_tool_call_invalid_json", tool_id=tool_id)
                arguments = {}

        if tool_type == "web_search" or function_name == "web_search":
            query = arguments.get("query", "")
            if not query or not isinstance(query, str):
                logger.warning("glm_tool_call_empty_query", tool_id=tool_id)
                return json.dumps({"error": "Empty search query"})

            logger.info("glm_executing_web_search", tool_id=tool_id, query=query[:100])

            try:
                brave = await self._get_brave_client()

                cached = self._get_cached_results(query)
                if cached is not None:
                    results = cached
                else:
                    results = await brave.search(query)
                    self._cache_brave_results(query, results)

                await self._prefetch_related_queries(brave, query)

                formatted_results = []
                for idx, result in enumerate(results, 1):
                    formatted_results.append(
                        {
                            "position": idx,
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "snippet": (result.get("snippet") or "")[:300],
                        }
                    )

                return json.dumps({"results": formatted_results})

            except Exception as exc:
                logger.error("glm_tool_call_failed", tool_id=tool_id, error=str(exc))
                return json.dumps({"error": f"Search failed: {str(exc)}"})

        if function_name == "web_fetch":
            url = arguments.get("url") or arguments.get("source_url")
            if not url or not isinstance(url, str):
                logger.warning("glm_tool_call_empty_url", tool_id=tool_id)
                return json.dumps({"error": "Empty fetch url"})

            if not self._is_valid_http_url(url):
                logger.warning("glm_tool_call_invalid_url", tool_id=tool_id, url=url)
                return json.dumps({"error": "Invalid URL"})

            logger.info("glm_executing_web_fetch", tool_id=tool_id, url=url)

            try:
                fetch_result = await self._perform_web_fetch(url)
                return json.dumps(fetch_result)
            except Exception as exc:
                logger.error("glm_web_fetch_failed", tool_id=tool_id, url=url, error=str(exc))
                return json.dumps({"status": "error", "url": url, "error": str(exc)})

        logger.warning(
            "glm_tool_call_unsupported",
            tool_type=tool_type,
            tool_id=tool_id,
            function_name=function_name,
        )
        return json.dumps({"error": f"Unsupported tool type: {function_name or tool_type}"})

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
        model_name = model or self.settings.glm_model

        tools = None
        tool_choice: Any = None
        if max_searches > 0:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web for up-to-date information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to issue to the Brave Search API.",
                                }
                            },
                            "required": ["query"],
                        },
                    },
                }
            ]
            tool_choice = "auto"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        aggregated_results: list[dict[str, Any]] = []

        routing_config = self.settings.openrouter_routing
        if not routing_config:
            routing_config = {
                "sort": "throughput",
                "order": ["cerebras", "fireworks"],
                "allow_fallbacks": True,
            }

        reasoning_effort = getattr(self.settings, "glm_reasoning_effort", None)

        logger.info(
            "glm_request_start",
            model=model_name,
            max_searches=max_searches,
            max_tokens=max_tokens,
            has_search=tools is not None,
        )
        if routing_config:
            logger.debug("glm_request_routing", routing=routing_config)
        if tools:
            logger.debug("glm_request_tools", tools=tools)

        total_search_count = 0
        max_tool_iterations = max(6, max_searches * 3 if max_searches else 6)
        last_response: dict[str, Any] | None = None
        searches_used = 0

        for iteration in range(max_tool_iterations):
            logger.debug("glm_iteration_start", iteration=iteration, message_count=len(messages))
            payload: dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
                "routing": routing_config,
            }

            if reasoning_effort:
                payload["reasoning"] = {"effort": reasoning_effort}

            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice

            try:
                response = await self._post(payload)
            except Exception as exc:
                logger.error(
                    "glm_request_failed",
                    model=model_name,
                    iteration=iteration,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise

            last_response = response

            search_count = _extract_search_steps(response)
            total_search_count += search_count
            usage_reported_searches = search_count > 0

            choices = response.get("choices", [])
            if not choices:
                logger.warning("glm_response_no_choices", iteration=iteration)
                return response, total_search_count

            message = choices[0].get("message", {}) or {}
            tool_calls = message.get("tool_calls") or []
            finish_reason = choices[0].get("finish_reason", "unknown")

            logger.debug(
                "glm_iteration_response",
                iteration=iteration,
                finish_reason=finish_reason,
                tool_call_count=len(tool_calls),
            )

            if not tool_calls:
                logger.info(
                    "glm_request_complete",
                    iteration=iteration,
                    finish_reason=finish_reason,
                    total_searches=total_search_count,
                )
                return response, total_search_count

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )

            remaining_budget = max_searches - searches_used if max_searches else None
            task_entries: list[tuple[dict[str, Any], bool, bool, asyncio.Task[str]]] = []

            for tool_call in tool_calls:
                is_search_call = (
                    tool_call.get("type") == "web_search"
                    or tool_call.get("function", {}).get("name") == "web_search"
                )

                consumes_budget = False
                if is_search_call and max_searches > 0:
                    if remaining_budget is not None and remaining_budget <= 0:
                        task = asyncio.create_task(
                            self._immediate_result(json.dumps({"error": "Search budget exhausted"}))
                        )
                    else:
                        consumes_budget = True
                        if remaining_budget is not None:
                            remaining_budget -= 1
                        task = asyncio.create_task(self._execute_tool_call(tool_call))
                else:
                    task = asyncio.create_task(self._execute_tool_call(tool_call))

                task_entries.append((tool_call, is_search_call, consumes_budget, task))

            task_results = await asyncio.gather(
                *(entry[3] for entry in task_entries), return_exceptions=True
            )

            for (tool_call, is_search_call, consumes_budget, task), result in zip(task_entries, task_results):
                tool_id = tool_call.get("id", f"tool_{iteration}")

                if isinstance(result, Exception):
                    logger.error(
                        "glm_tool_call_exception",
                        tool_id=tool_id,
                        error=str(result),
                        error_type=type(result).__name__,
                    )
                    result_content = json.dumps({"error": str(result)})
                else:
                    result_content = result

                if consumes_budget:
                    searches_used += 1
                    if not usage_reported_searches:
                        total_search_count += 1

                try:
                    parsed_payload = json.loads(result_content)
                except json.JSONDecodeError:
                    parsed_payload = None

                if isinstance(parsed_payload, dict):
                    results_payload = parsed_payload.get("results")
                    if isinstance(results_payload, list):
                        for item in results_payload:
                            aggregated_results.append(
                                {
                                    "title": item.get("title", ""),
                                    "url": item.get("url", ""),
                                    "snippet": item.get("snippet", ""),
                                }
                            )
                    else:
                        content = parsed_payload.get("content")
                        if content:
                            aggregated_results.append(
                                {
                                    "title": parsed_payload.get("title", ""),
                                    "url": parsed_payload.get("url", ""),
                                    "snippet": content,
                                }
                            )

                if len(aggregated_results) > 24:
                    aggregated_results[:] = aggregated_results[-24:]

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result_content,
                    }
                )

            if max_searches > 0:
                remaining = max(max_searches - searches_used, 0)
                if remaining > 0:
                    reminder = (
                        f"Reminder: you have {remaining} web searches remaining out of {max_searches}. "
                        "Use them only if you truly need new evidence; otherwise start synthesizing the final answer."
                    )
                else:
                    summary = self._summarise_search_results(aggregated_results)
                    if summary:
                        reminder = (
                            "Search budget exhausted. You must now produce the final response using the gathered evidence below. "
                            "Do not call web_search again. Focus on selecting the best products and write the final JSON.\n\n"
                            f"Evidence summary:\n{summary}"
                        )
                    else:
                        reminder = (
                            "Search budget exhausted. You must now produce the final response using the information already collected. "
                            "Do not call web_search again; proceed with drafting the final JSON output."
                        )
                messages.append({"role": "assistant", "content": reminder})

        logger.warning("glm_tool_loop_max_iterations", max_iterations=max_tool_iterations)
        return last_response or {"choices": []}, total_search_count


__all__ = ["GlmClient", "GlmClientError", "GlmRateLimitError", "GlmTimeoutError"]

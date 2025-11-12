"""HTTP middleware helpers: request wrapping, CORS, and timeouts."""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from functools import wraps
from secrets import token_hex
from typing import Any, Callable, TypeVar, cast

from concurrent.futures import TimeoutError as FuturesTimeoutError

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from .auth import (
    AuthenticationError,
    AuthorizationError,
    RateLimitExceeded,
    check_rate_limit_async,
    require_admin_auth,
    require_auth,
)
from .bootstrap import CONFIG, LOG_ERROR, LOG_INFO, LOG_WARNING, METRICS, REQUEST_TIMEOUT_EXECUTOR

EndpointCallable = Callable[..., Any]
F = TypeVar("F", bound=EndpointCallable)


def generate_request_id() -> str:
    """Generate a unique, human-searchable request identifier."""

    return f"req_{int(time.time() * 1000)}_{token_hex(4)}"


def _get_request_method(request: Any) -> str:
    return getattr(request, "method", "UNKNOWN").upper()


def _get_request_path(request: Any) -> str:
    url = getattr(request, "url", None)
    if url and hasattr(url, "path"):
        return url.path
    return getattr(request, "path", "/unknown")


def _get_request_ip(request: Any) -> str:
    client = getattr(request, "client", None)
    if client and hasattr(client, "host") and client.host:
        return client.host
    return getattr(request, "remote_addr", "unknown")


def add_cors_headers(response: Any, request: Any) -> Any:
    """Add CORS headers to a response object if the origin is allowed."""

    origin = ""
    headers = getattr(request, "headers", {})
    if isinstance(headers, dict):
        origin = headers.get("Origin", "")
    elif hasattr(headers, "get"):
        origin = headers.get("Origin", "")  # type: ignore[assignment]

    allowed_origins = CONFIG["CORS_ORIGINS"]
    if origin in allowed_origins or "*" in allowed_origins:
        headers_obj = getattr(response, "headers", None)
        if headers_obj is None:
            return response

        # Starlette/fastapi responses expose MutableHeaders; fall back to dict-like behaviour otherwise.
        try:
            headers_obj["Access-Control-Allow-Origin"] = origin
            headers_obj["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            headers_obj["Access-Control-Allow-Headers"] = f"Content-Type, {CONFIG['API_KEY_HEADER']}"
            headers_obj["Access-Control-Max-Age"] = str(CONFIG["CORS_MAX_AGE"])
            headers_obj["Access-Control-Allow-Credentials"] = "true"
        except TypeError:
            # In case headers_obj behaves like a plain mapping without __setitem__
            if isinstance(headers_obj, dict):
                headers_obj["Access-Control-Allow-Origin"] = origin
                headers_obj["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                headers_obj["Access-Control-Allow-Headers"] = f"Content-Type, {CONFIG['API_KEY_HEADER']}"
                headers_obj["Access-Control-Max-Age"] = str(CONFIG["CORS_MAX_AGE"])
                headers_obj["Access-Control-Allow-Credentials"] = "true"

    return response


def handle_options_request() -> tuple[dict[str, str], int]:
    """Handle CORS preflight OPTIONS requests."""

    response = {"status": "ok"}
    return response, 200


def _coerce_to_dict(payload: Any) -> dict[str, Any]:
    """Convert arbitrary payloads into JSON-serialisable dictionaries."""

    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {}
    if isinstance(payload, (list, tuple, set)):
        return {"data": list(payload)}
    if isinstance(payload, bytes):
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            return {"data": payload.decode("utf-8", errors="ignore")}
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return {"message": payload}
    return {"data": payload}


def _build_response(result: Any, request_id: str) -> Response:
    """Normalise endpoint return values into a FastAPI Response."""

    headers: dict[str, str] = {}

    if isinstance(result, Response):
        result.headers.setdefault("X-Request-ID", request_id)
        return result

    if isinstance(result, tuple):
        if len(result) == 3:
            body, status_code, extra_headers = result
            headers = dict(extra_headers or {})
        elif len(result) == 2:
            body, status_code = result
        else:  # pragma: no cover - defensive programming for unexpected tuples
            raise ValueError("Endpoint tuples must contain (body, status) or (body, status, headers).")
    else:
        body, status_code = result, 200

    body_dict = _coerce_to_dict(body)
    body_dict.setdefault("status", "SUCCESS" if status_code < 400 else "ERROR")
    body_dict["request_id"] = request_id

    response = JSONResponse(content=body_dict, status_code=status_code)
    response.headers.update(headers)
    response.headers["X-Request-ID"] = request_id
    return response


def endpoint_wrapper(
    func: EndpointCallable | None = None,
    *,
    requires_auth: bool = True,
    requires_admin: bool = False,
    rate_limit_config: dict[str, int] | None = None,
) -> Callable[[EndpointCallable], EndpointCallable]:
    """Decorator that layers logging, auth, rate limiting, metrics, and error handling."""

    def decorator(fn: EndpointCallable) -> EndpointCallable:
        is_coroutine = asyncio.iscoroutinefunction(fn)

        @wraps(fn)
        async def wrapped_endpoint(request: Request, *args: Any, **kwargs: Any) -> Response:
            request_id = generate_request_id()
            start_time = time.time()
            method = _get_request_method(request)
            path = _get_request_path(request)
            ip = _get_request_ip(request)

            LOG_INFO("Request received", request_id=request_id, method=method, path=path, ip=ip)

            try:
                if method == "OPTIONS":
                    body, status_code = handle_options_request()
                    payload = _coerce_to_dict(body)
                    payload["request_id"] = request_id
                    response = JSONResponse(content=payload, status_code=status_code)
                    response.headers["X-Request-ID"] = request_id
                    return add_cors_headers(response, request)

                if requires_auth:
                    if requires_admin:
                        require_admin_auth(request)
                    else:
                        require_auth(request)

                user_id = getattr(request, "user_id", "anonymous")

                if rate_limit_config:
                    max_req = int(rate_limit_config.get("requests", CONFIG["RATE_LIMIT_REQUESTS"]))
                    window = int(rate_limit_config.get("window", CONFIG["RATE_LIMIT_WINDOW"]))
                    allowed, _, reset = await check_rate_limit_async(user_id, fn.__name__, max_req, window)
                    if not allowed:
                        retry_after = max(reset - int(time.time()), 0)
                        payload = {
                            "status": "ERROR",
                            "error": "Rate limit exceeded",
                            "error_code": "RATE_LIMIT_EXCEEDED",
                            "retry_after": retry_after,
                            "request_id": request_id,
                        }
                        response = JSONResponse(content=payload, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
                        response.headers["Retry-After"] = str(retry_after)
                        response.headers["X-Request-ID"] = request_id
                        METRICS.increment("request.rate_limit", endpoint=fn.__name__)
                        return add_cors_headers(response, request)

                if is_coroutine:
                    result = await fn(request, *args, **kwargs)
                else:
                    result = fn(request, *args, **kwargs)

                response = _build_response(result, request_id)
                duration = time.time() - start_time

                LOG_INFO(
                    "Request completed",
                    request_id=request_id,
                    status=response.status_code,
                    duration=duration,
                    user_id=getattr(request, "user_id", "anonymous"),
                )
                METRICS.histogram("request.duration", duration, endpoint=fn.__name__)
                metric_name = "request.success" if response.status_code < 400 else "request.failure"
                METRICS.increment(metric_name, endpoint=fn.__name__)

                return add_cors_headers(response, request)

            except AuthenticationError as exc:
                duration = time.time() - start_time
                LOG_WARNING("Authentication failed", request_id=request_id, error=str(exc), duration=duration)
                METRICS.increment("request.auth_error", endpoint=fn.__name__)
                payload = {
                    "status": "ERROR",
                    "error": str(exc),
                    "error_code": "AUTHENTICATION_FAILED",
                    "request_id": request_id,
                }
                response = JSONResponse(content=payload, status_code=status.HTTP_401_UNAUTHORIZED)
                response.headers["X-Request-ID"] = request_id
                return add_cors_headers(response, request)

            except AuthorizationError as exc:
                duration = time.time() - start_time
                LOG_WARNING("Authorization failed", request_id=request_id, error=str(exc), duration=duration)
                METRICS.increment("request.authz_error", endpoint=fn.__name__)
                payload = {
                    "status": "ERROR",
                    "error": str(exc),
                    "error_code": "AUTHORIZATION_FAILED",
                    "request_id": request_id,
                }
                response = JSONResponse(content=payload, status_code=status.HTTP_403_FORBIDDEN)
                response.headers["X-Request-ID"] = request_id
                return add_cors_headers(response, request)

            except RateLimitExceeded as exc:
                duration = time.time() - start_time
                LOG_WARNING(
                    "Rate limit exceeded",
                    request_id=request_id,
                    user_id=getattr(request, "user_id", "anonymous"),
                    duration=duration,
                )
                METRICS.increment("request.rate_limit", endpoint=fn.__name__)

                payload: dict[str, Any]
                if exc.args:
                    try:
                        payload = json.loads(exc.args[0])
                    except (TypeError, json.JSONDecodeError):
                        payload = {}
                else:
                    payload = {}

                payload.setdefault("status", "ERROR")
                payload.setdefault("error", "Rate limit exceeded")
                payload.setdefault("error_code", "RATE_LIMIT_EXCEEDED")
                payload["request_id"] = request_id

                response = JSONResponse(content=payload, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
                response.headers["X-Request-ID"] = request_id
                return add_cors_headers(response, request)

            except Exception as exc:
                duration = time.time() - start_time
                LOG_ERROR(
                    "Request failed",
                    request_id=request_id,
                    error=str(exc),
                    traceback=traceback.format_exc(),
                    duration=duration,
                )
                METRICS.increment("request.error", endpoint=fn.__name__)

                payload = {
                    "status": "ERROR",
                    "error": "Internal server error",
                    "error_code": "INTERNAL_ERROR",
                    "request_id": request_id,
                }
                if CONFIG["DEBUG"]:
                    payload["error_details"] = str(exc)

                response = JSONResponse(content=payload, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
                response.headers["X-Request-ID"] = request_id
                return add_cors_headers(response, request)

        return wrapped_endpoint

    if func is not None:
        return decorator(func)

    return decorator


def timeout_decorator(seconds: int) -> Callable[[F], F]:
    """Decorator to enforce execution timeout on synchronous or async functions."""

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
                except asyncio.TimeoutError:
                    LOG_ERROR("Request timeout", function=func.__name__, timeout=seconds)
                    METRICS.increment("request.timeout")
                    return {
                        "status": "ERROR",
                        "error": "Request timeout",
                        "error_code": "TIMEOUT",
                    }, status.HTTP_504_GATEWAY_TIMEOUT

            return cast(F, async_wrapper)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            future = REQUEST_TIMEOUT_EXECUTOR.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=seconds)
            except FuturesTimeoutError:
                future.cancel()
                LOG_ERROR("Request timeout", function=func.__name__, timeout=seconds)
                METRICS.increment("request.timeout")
                return {
                    "status": "ERROR",
                    "error": "Request timeout",
                    "error_code": "TIMEOUT",
                }, status.HTTP_504_GATEWAY_TIMEOUT
            except Exception:
                # Any other exception should propagate to the caller.
                raise

        return cast(F, wrapper)

    return decorator


__all__ = [
    "add_cors_headers",
    "endpoint_wrapper",
    "generate_request_id",
    "handle_options_request",
    "timeout_decorator",
]


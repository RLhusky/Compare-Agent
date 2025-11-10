"""Authentication, authorization, validation, and rate limiting helpers."""

from __future__ import annotations

import json
import re
import time
from functools import wraps
from typing import Any, Callable, TypeVar, cast

from .bootstrap import (
    CONFIG,
    LOG_DEBUG,
    LOG_ERROR,
    LOG_INFO,
    LOG_WARNING,
    METRICS,
    raw_redis_connection,
)

AuthCallable = Callable[..., Any]
F = TypeVar("F", bound=AuthCallable)


class AuthenticationError(PermissionError):
    """Raised when authentication fails."""


class AuthorizationError(PermissionError):
    """Raised when authorization fails."""


def validate_api_key(api_key: str | None) -> tuple[bool, str | None, bool]:
    """Validate an API key against the configured admin and user lists."""

    if not CONFIG["REQUIRE_AUTH"]:
        return True, "dev_user", True

    if not api_key:
        return False, None, False

    if api_key in CONFIG["ADMIN_API_KEYS"]:
        return True, f"admin_{api_key[:8]}", True

    if api_key in CONFIG["USER_API_KEYS"]:
        return True, f"user_{api_key[:8]}", False

    return False, None, False


def require_auth(request: Any) -> None:
    """Populate ``request.user_id`` and ``request.is_admin`` or raise on failure."""

    if not CONFIG["REQUIRE_AUTH"]:
        setattr(request, "user_id", "dev_user")
        setattr(request, "is_admin", True)
        return

    headers = getattr(request, "headers", {})
    api_key = headers.get(CONFIG["API_KEY_HEADER"]) if isinstance(headers, dict) else getattr(
        headers,
        "get",
        lambda *_args, **_kwargs: None,
    )(CONFIG["API_KEY_HEADER"])

    if not api_key:
        LOG_WARNING("Missing API key in request", ip=getattr(request, "remote_addr", "unknown"))
        METRICS.increment("auth.missing_key")
        raise AuthenticationError("Missing API key")

    is_valid, user_id, is_admin = validate_api_key(api_key)
    if not is_valid or user_id is None:
        LOG_WARNING(
            "Invalid API key",
            key_prefix=api_key[:8],
            ip=getattr(request, "remote_addr", "unknown"),
        )
        METRICS.increment("auth.invalid_key")
        raise AuthenticationError("Invalid API key")

    setattr(request, "user_id", user_id)
    setattr(request, "is_admin", is_admin)
    LOG_DEBUG("Authentication successful", user_id=user_id, is_admin=is_admin)
    METRICS.increment("auth.success")


def require_admin_auth(request: Any) -> None:
    """Ensure the caller is an administrator."""

    require_auth(request)
    if not getattr(request, "is_admin", False):
        LOG_WARNING(
            "Admin access denied",
            user_id=getattr(request, "user_id", "unknown"),
            ip=getattr(request, "remote_addr", "unknown"),
        )
        METRICS.increment("auth.admin_denied")
        raise AuthorizationError("Admin access required")

    LOG_DEBUG("Admin authentication successful", user_id=request.user_id)
    METRICS.increment("auth.admin_success")


def sanitize_html(text: str | None) -> str:
    """Remove potentially dangerous HTML or JavaScript snippets."""

    if not text:
        return ""

    cleaned = re.sub(r"<[^>]*>", "", text)
    dangerous_patterns = [
        r"javascript:",
        r"onerror\s*=",
        r"onclick\s*=",
        r"onload\s*=",
        r"<script",
        r"</script>",
    ]
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def validate_comparison_request(data: dict[str, Any]) -> tuple[bool, list[str], dict[str, str] | None]:
    """Validate incoming comparison requests and return sanitised data."""

    errors: list[str] = []

    if "category" not in data:
        errors.append("Missing required field: category")
        return False, errors, None

    if not isinstance(data["category"], str) or not data["category"].strip():
        errors.append("Category cannot be empty")

    category = sanitize_html(cast(str, data.get("category", ""))).strip()
    constraints = sanitize_html(cast(str, data.get("constraints", ""))).strip()

    if len(category) > CONFIG["MAX_CATEGORY_LENGTH"]:
        errors.append(f"Category too long (max {CONFIG['MAX_CATEGORY_LENGTH']} chars)")
    if len(constraints) > CONFIG["MAX_CONSTRAINTS_LENGTH"]:
        errors.append(f"Constraints too long (max {CONFIG['MAX_CONSTRAINTS_LENGTH']} chars)")

    suspicious_patterns = [
        "ignore previous",
        "ignore all previous",
        "disregard",
        "forget your",
        "you are now",
        "pretend you are",
        "act as",
        "roleplay",
    ]
    combined_text = (category + " " + constraints).lower()
    for pattern in suspicious_patterns:
        if pattern in combined_text:
            errors.append("Input contains suspicious patterns")
            LOG_WARNING("Suspicious input detected", pattern=pattern, category=category[:50])
            METRICS.increment("validation.suspicious_input")
            break

    if errors:
        return False, errors, None

    sanitized_data = {"category": category, "constraints": constraints}
    return True, [], sanitized_data


class RateLimitExceeded(RuntimeError):
    """Raised when rate limit is exceeded."""


def get_rate_limit_key(user_id: str, endpoint: str) -> str:
    return f"rate_limit:{user_id}:{endpoint}"


def check_rate_limit(user_id: str, endpoint: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
    """Check if a user has exceeded their rate limit."""

    if not CONFIG["RATE_LIMIT_ENABLED"]:
        return True, 999, 0

    key = get_rate_limit_key(user_id, endpoint)
    current_time = int(time.time())
    window_start = current_time - window_seconds

    try:
        pipe = raw_redis_connection.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {current_time: current_time})
        pipe.expire(key, window_seconds)

        results = pipe.execute()
        current_count = cast(int, results[1])

        requests_remaining = max_requests - current_count
        reset_time = current_time + window_seconds

        if current_count >= max_requests:
            LOG_WARNING(
                "Rate limit exceeded",
                user_id=user_id,
                endpoint=endpoint,
                count=current_count,
                max=max_requests,
            )
            METRICS.increment("rate_limit.exceeded", user_id=user_id)
            return False, 0, reset_time

        return True, requests_remaining, reset_time

    except Exception as error:  # pragma: no cover - Redis failures are environment specific
        LOG_ERROR("Rate limit check failed", error=str(error), user_id=user_id)
        return True, max_requests, current_time + window_seconds


def rate_limit_decorator(max_requests: int | None = None, window_seconds: int | None = None) -> Callable[[F], F]:
    """Decorator to enforce rate limits on synchronous request handlers."""

    max_req = max_requests or CONFIG["RATE_LIMIT_REQUESTS"]
    window = window_seconds or CONFIG["RATE_LIMIT_WINDOW"]

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            user_id = getattr(request, "user_id", "anonymous")
            endpoint = func.__name__

            allowed, remaining, reset_time = check_rate_limit(user_id, endpoint, max_req, window)
            if not allowed:
                response = {"error": "Rate limit exceeded", "retry_after": max(reset_time - int(time.time()), 0)}
                raise RateLimitExceeded(json.dumps(response))

            result = func(request, *args, **kwargs)

            if isinstance(result, tuple) and len(result) == 2:
                response_data, status_code = result
            else:
                response_data, status_code = result, 200

            if isinstance(response_data, dict):
                response_data.setdefault("rate_limit", {})
                response_data["rate_limit"].update(
                    {
                        "limit": max_req,
                        "remaining": remaining,
                        "reset": reset_time,
                    }
                )

            return response_data, status_code

        return cast(F, wrapper)

    return decorator


__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitExceeded",
    "check_rate_limit",
    "rate_limit_decorator",
    "require_admin_auth",
    "require_auth",
    "sanitize_html",
    "validate_api_key",
    "validate_comparison_request",
]


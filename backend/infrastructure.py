"""Comparoo backend production infrastructure helpers.

This module turns the high-level pseudocode specification into working Python
code.  Everything here is written to favour clarity over cleverness—each
function includes comments that explain *why* it exists and *how* it should be
used so that team members without a deep technical background can still follow
the flow.

The module is intentionally self-contained: it is safe to import individual
pieces (for example, the configuration loader or rate limiter) without pulling
in the rest of the backend.  Wherever external services are required (Redis,
HTTP APIs, background schedulers), we fail early with readable error messages so
misconfiguration is caught during startup rather than in production traffic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from collections.abc import Callable, Generator, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from secrets import token_hex
from typing import Any, TypeVar, cast

import requests
import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
import prometheus_client
from prometheus_client import Counter, Gauge, Histogram
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionErrorType
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.agent.orchestrator import ProductComparisonAgent, WorkflowBudgetExceeded
from backend.models.schemas import CompareRequest, ComparisonResponse
from config import get_settings

try:
    # FuzzyWuzzy is the requested library; RapidFuzz is a faster drop-in
    # replacement that we fall back to automatically if needed.
    from fuzzywuzzy import fuzz as fuzzy_fuzz  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from rapidfuzz import fuzz as fuzzy_fuzz  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Neither 'fuzzywuzzy' nor 'rapidfuzz' is installed. "
            "Install one of them to enable fuzzy matching support."
        ) from exc

# -----------------------------------------------------------------------------
# Bootstrap logging so that early configuration errors are still visible.  The
# structured logging configuration below will override this once the settings
# are loaded successfully.
# -----------------------------------------------------------------------------
_BOOTSTRAP_LOGGER = logging.getLogger("comparoo.bootstrap")
if not _BOOTSTRAP_LOGGER.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


class ConfigurationError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _split_csv(raw_value: str) -> list[str]:
    """Convert a comma-separated env string into a clean list."""

    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def load_from_env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    """Return an environment variable or a default value.

    Parameters
    ----------
    key:
        Name of the environment variable.
    default:
        Value to return when the variable is missing.
    required:
        When ``True`` the function raises :class:`ConfigurationError` if the
        variable is not set and no default is provided.
    """

    value = os.getenv(key, default)

    if required and value is None:
        raise ConfigurationError(f"Missing required environment variable: {key}")

    return value


def _boolean_from_env(raw_value: str, key: str) -> bool:
    """Interpret common truthy/falsey string values."""

    lowered = raw_value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    raise ConfigurationError(f"Environment variable {key} must be a boolean-like string, got {raw_value!r}")


def _int_from_env(raw_value: str, key: str) -> int:
    """Convert an environment string into an integer with friendly errors."""

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {key} must be an integer, got {raw_value!r}") from exc


def _float_from_env(raw_value: str, key: str) -> float:
    """Convert an environment string into a float with friendly errors."""

    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {key} must be a float, got {raw_value!r}") from exc


def load_config() -> dict[str, Any]:
    """Read and validate the full application configuration.

    All casting and validation happens here so the rest of the code can assume
    values already have the correct type.
    """

    config: dict[str, Any] = {}

    # Environment
    config["ENVIRONMENT"] = load_from_env("ENVIRONMENT", "development")
    config["DEBUG"] = _boolean_from_env(load_from_env("DEBUG", "false"), "DEBUG")
    config["LOG_LEVEL"] = load_from_env("LOG_LEVEL", "INFO")

    # Server
    config["HOST"] = load_from_env("HOST", "0.0.0.0")
    config["PORT"] = _int_from_env(load_from_env("PORT", "8000"), "PORT")
    config["WORKERS"] = _int_from_env(load_from_env("WORKERS", "4"), "WORKERS")

    # Redis
    config["REDIS_HOST"] = load_from_env("REDIS_HOST", "localhost")
    config["REDIS_PORT"] = _int_from_env(load_from_env("REDIS_PORT", "6379"), "REDIS_PORT")
    config["REDIS_PASSWORD"] = load_from_env("REDIS_PASSWORD", None)
    config["REDIS_DB"] = _int_from_env(load_from_env("REDIS_DB", "0"), "REDIS_DB")
    config["REDIS_MAX_CONNECTIONS"] = _int_from_env(load_from_env("REDIS_MAX_CONNECTIONS", "50"), "REDIS_MAX_CONNECTIONS")

    # API Keys - REQUIRED
    config["PERPLEXITY_API_KEY"] = load_from_env("PERPLEXITY_API_KEY", required=True)
    config["GROK_API_KEY"] = load_from_env("GROK_API_KEY", required=True)

    # API Configuration
    config["PERPLEXITY_BASE_URL"] = load_from_env("PERPLEXITY_BASE_URL", "https://api.perplexity.ai")
    config["GROK_BASE_URL"] = load_from_env("GROK_BASE_URL", "https://api.x.ai/v1")
    config["API_REQUEST_TIMEOUT"] = _int_from_env(load_from_env("API_REQUEST_TIMEOUT", "30"), "API_REQUEST_TIMEOUT")
    config["API_MAX_RETRIES"] = _int_from_env(load_from_env("API_MAX_RETRIES", "3"), "API_MAX_RETRIES")
    config["API_BACKOFF_FACTOR"] = _float_from_env(load_from_env("API_BACKOFF_FACTOR", "2"), "API_BACKOFF_FACTOR")

    # Authentication
    config["API_KEY_HEADER"] = load_from_env("API_KEY_HEADER", "X-API-Key")
    config["ADMIN_API_KEYS"] = _split_csv(load_from_env("ADMIN_API_KEYS", ""))
    config["USER_API_KEYS"] = _split_csv(load_from_env("USER_API_KEYS", ""))
    config["REQUIRE_AUTH"] = _boolean_from_env(load_from_env("REQUIRE_AUTH", "true"), "REQUIRE_AUTH")

    # CORS
    config["CORS_ORIGINS"] = _split_csv(load_from_env("CORS_ORIGINS", "http://localhost:3000"))
    config["CORS_MAX_AGE"] = _int_from_env(load_from_env("CORS_MAX_AGE", "3600"), "CORS_MAX_AGE")

    # Rate Limiting
    config["RATE_LIMIT_ENABLED"] = _boolean_from_env(load_from_env("RATE_LIMIT_ENABLED", "true"), "RATE_LIMIT_ENABLED")
    config["RATE_LIMIT_REQUESTS"] = _int_from_env(load_from_env("RATE_LIMIT_REQUESTS", "10"), "RATE_LIMIT_REQUESTS")
    config["RATE_LIMIT_WINDOW"] = _int_from_env(load_from_env("RATE_LIMIT_WINDOW", "60"), "RATE_LIMIT_WINDOW")

    # Search Budgets
    config["MAX_TOTAL_SEARCHES"] = _int_from_env(load_from_env("MAX_TOTAL_SEARCHES", "40"), "MAX_TOTAL_SEARCHES")
    config["A1_SEARCH_BUDGET"] = _int_from_env(load_from_env("A1_SEARCH_BUDGET", "10"), "A1_SEARCH_BUDGET")
    config["B_SEARCH_BUDGET_PER_AGENT"] = _int_from_env(load_from_env("B_SEARCH_BUDGET_PER_AGENT", "4"), "B_SEARCH_BUDGET_PER_AGENT")

    # Request Limits
    config["MAX_REQUEST_TIMEOUT"] = _int_from_env(load_from_env("MAX_REQUEST_TIMEOUT", "60"), "MAX_REQUEST_TIMEOUT")
    config["MAX_CATEGORY_LENGTH"] = _int_from_env(load_from_env("MAX_CATEGORY_LENGTH", "200"), "MAX_CATEGORY_LENGTH")
    config["MAX_CONSTRAINTS_LENGTH"] = _int_from_env(load_from_env("MAX_CONSTRAINTS_LENGTH", "500"), "MAX_CONSTRAINTS_LENGTH")

    # Background Jobs
    config["ENABLE_BACKGROUND_JOBS"] = _boolean_from_env(load_from_env("ENABLE_BACKGROUND_JOBS", "true"), "ENABLE_BACKGROUND_JOBS")
    config["PRICE_REFRESH_HOUR"] = _int_from_env(load_from_env("PRICE_REFRESH_HOUR", "3"), "PRICE_REFRESH_HOUR")
    config["PRICE_REFRESH_AGE_DAYS"] = _int_from_env(load_from_env("PRICE_REFRESH_AGE_DAYS", "60"), "PRICE_REFRESH_AGE_DAYS")

    # Cost Tracking
    config["COST_PER_SEARCH"] = _float_from_env(load_from_env("COST_PER_SEARCH", "0.005"), "COST_PER_SEARCH")
    config["COST_PER_SECOND"] = _float_from_env(load_from_env("COST_PER_SECOND", "0.001"), "COST_PER_SECOND")

    # Post-validation warnings help operators catch incomplete setups without
    # aborting the entire deployment (useful for staging environments).
    if config["REQUIRE_AUTH"] and not config["ADMIN_API_KEYS"]:
        _BOOTSTRAP_LOGGER.warning("REQUIRE_AUTH is true but ADMIN_API_KEYS is empty.")
    if config["REQUIRE_AUTH"] and not config["USER_API_KEYS"]:
        _BOOTSTRAP_LOGGER.warning("REQUIRE_AUTH is true but USER_API_KEYS is empty.")

    _BOOTSTRAP_LOGGER.info("Configuration loaded", extra={"environment": config["ENVIRONMENT"]})
    return config


# Load configuration once during module import so the rest of the module can
# rely on typed values being available.
CONFIG = load_config()


def setup_logging() -> structlog.stdlib.BoundLogger:
    """Configure structured logging using structlog.

    The configuration mirrors the pseudocode specification with a JSON renderer
    so logs are machine-readable.  We still keep human-friendly defaults by
    honouring ``CONFIG['LOG_LEVEL']`` and writing to standard output.
    """

    logging_level = getattr(logging, CONFIG["LOG_LEVEL"].upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging_level,
        stream=sys.stdout,
    )

    logger = structlog.get_logger("comparoo")
    logger.info("Logging initialized", level=CONFIG["LOG_LEVEL"])
    return cast(structlog.stdlib.BoundLogger, logger)


LOGGER = setup_logging()


def LOG_DEBUG(message: str, **kwargs: Any) -> None:
    """Convenience wrapper to keep original pseudocode semantics."""

    LOGGER.debug(message, **kwargs)


def LOG_INFO(message: str, **kwargs: Any) -> None:
    """Convenience wrapper to keep original pseudocode semantics."""

    LOGGER.info(message, **kwargs)


def LOG_WARNING(message: str, **kwargs: Any) -> None:
    """Convenience wrapper to keep original pseudocode semantics."""

    LOGGER.warning(message, **kwargs)


def LOG_ERROR(message: str, **kwargs: Any) -> None:
    """Convenience wrapper to keep original pseudocode semantics."""

    LOGGER.error(message, **kwargs)


# =============================================================================
# METRICS SETUP
# =============================================================================


class MetricsCollector:
    """Simple Prometheus metrics collector with lazy metric creation."""

    def __init__(self) -> None:
        self.counters: dict[str, Counter] = {}
        self.histograms: dict[str, Histogram] = {}
        self.gauges: dict[str, Gauge] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, value: float = 1.0, **labels: Any) -> None:
        """Increment a counter metric."""

        with self._lock:
            counter = self.counters.get(name)
            if counter is None:
                label_names = list(labels.keys())
                counter = Counter(name.replace(".", "_"), f"Counter for {name}", labelnames=label_names or None)
                self.counters[name] = counter

        if labels:
            counter.labels(**labels).inc(value)
        else:
            counter.inc(value)

    def histogram(self, name: str, value: float, **labels: Any) -> None:
        """Record a histogram metric."""

        with self._lock:
            histogram = self.histograms.get(name)
            if histogram is None:
                label_names = list(labels.keys())
                histogram = Histogram(name.replace(".", "_"), f"Histogram for {name}", labelnames=label_names or None)
                self.histograms[name] = histogram

        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)

    def gauge(self, name: str, value: float, **labels: Any) -> None:
        """Set a gauge metric."""

        with self._lock:
            gauge = self.gauges.get(name)
            if gauge is None:
                label_names = list(labels.keys())
                gauge = Gauge(name.replace(".", "_"), f"Gauge for {name}", labelnames=label_names or None)
                self.gauges[name] = gauge

        if labels:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)


METRICS = MetricsCollector()


# =============================================================================
# REDIS CONNECTION WITH RETRY
# =============================================================================


class RedisConnectionError(RuntimeError):
    """Raised when Redis connection initialisation fails."""


def initialize_redis() -> Redis:
    """Initialise Redis connection with retry and configuration."""

    max_attempts = 5
    connection: Redis | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            LOG_INFO(
                "Attempting Redis connection",
                attempt=attempt,
                host=CONFIG["REDIS_HOST"],
                port=CONFIG["REDIS_PORT"],
            )

            connection = Redis(
                host=CONFIG["REDIS_HOST"],
                port=CONFIG["REDIS_PORT"],
                password=CONFIG["REDIS_PASSWORD"],
                db=CONFIG["REDIS_DB"],
                socket_timeout=2.0,
                socket_connect_timeout=5.0,
                decode_responses=True,
                max_connections=CONFIG["REDIS_MAX_CONNECTIONS"],
                health_check_interval=30,
            )

            connection.ping()

            try:
                connection.config_set("maxmemory-policy", "allkeys-lru")
                connection.config_set("maxmemory", "2gb")
            except Exception as config_error:  # pragma: no cover - depends on Redis permissions
                LOG_WARNING("Could not set Redis config", error=str(config_error))

            LOG_INFO("Redis connected successfully", host=CONFIG["REDIS_HOST"], port=CONFIG["REDIS_PORT"])
            METRICS.increment("redis.connection.success")
            return connection

        except RedisConnectionErrorType as connection_error:
            LOG_WARNING(
                "Redis connection attempt failed",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(connection_error),
            )

            if attempt == max_attempts:
                LOG_ERROR("Failed to connect to Redis after all retries")
                METRICS.increment("redis.connection.failure")
                raise RedisConnectionError(
                    f"Cannot connect to Redis at {CONFIG['REDIS_HOST']}:{CONFIG['REDIS_PORT']}"
                ) from connection_error

            sleep_time = 2**attempt
            LOG_INFO("Retrying Redis connection", wait_seconds=sleep_time)
            time.sleep(sleep_time)

    raise RedisConnectionError("Failed to initialise Redis connection")


try:
    raw_redis_connection = initialize_redis()
except RedisConnectionError as error:
    LOG_ERROR("Cannot start application without Redis", error=str(error))
    raise


# =============================================================================
# API CLIENT CONFIGURATION
# =============================================================================


class APIClientError(RuntimeError):
    """Raised when API client calls fail."""


@dataclass(slots=True)
class APIClient:
    """Base API client with retry logic and error handling."""

    name: str
    base_url: str
    api_key: str

    def __post_init__(self) -> None:
        self.timeout = CONFIG["API_REQUEST_TIMEOUT"]
        self.max_retries = CONFIG["API_MAX_RETRIES"]
        self.backoff_factor = CONFIG["API_BACKOFF_FACTOR"]
        self._session = requests.Session()

    def call(self, endpoint: str, payload: dict[str, Any], timeout: int | None = None) -> dict[str, Any]:
        """Make an API call with retry logic."""

        url = f"{self.base_url}{endpoint}"
        request_timeout = timeout or self.timeout

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                LOG_DEBUG(
                    "API call",
                    service=self.name,
                    attempt=attempt,
                    endpoint=endpoint,
                    timeout=request_timeout,
                )

                start_time = time.time()
                response = self._session.post(url, json=payload, headers=headers, timeout=request_timeout)
                duration = time.time() - start_time

                LOG_DEBUG(
                    "API response",
                    service=self.name,
                    status_code=response.status_code,
                    duration=duration,
                )
                METRICS.histogram(f"api.{self.name}.duration", duration)

                if response.status_code >= 500:
                    raise APIClientError(f"Server error: {response.status_code}")

                if response.status_code >= 400:
                    error_msg = f"Client error: {response.status_code}"
                    try:
                        error_data = response.json()
                        detail = error_data.get("error") or error_data.get("message")
                        if detail:
                            error_msg = f"{error_msg} - {detail}"
                    except json.JSONDecodeError:
                        pass

                    LOG_ERROR(
                        "API client error",
                        service=self.name,
                        status=response.status_code,
                        error=error_msg,
                    )
                    METRICS.increment(f"api.{self.name}.client_error")
                    raise APIClientError(error_msg)

                METRICS.increment(f"api.{self.name}.success")
                return cast(dict[str, Any], response.json())

            except (requests.ConnectionError, requests.Timeout) as connection_error:
                last_error = connection_error
                LOG_WARNING(
                    "API connection error",
                    service=self.name,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    error=str(connection_error),
                )
                METRICS.increment(f"api.{self.name}.connection_error")

                if attempt == self.max_retries:
                    LOG_ERROR("API failed after retries", service=self.name)
                    METRICS.increment(f"api.{self.name}.failure")
                    raise APIClientError(f"API call failed: {last_error}") from connection_error

                sleep_time = self.backoff_factor**attempt
                LOG_DEBUG("API retry backoff", service=self.name, wait_seconds=sleep_time)
                time.sleep(sleep_time)

            except APIClientError:
                raise

            except Exception as unexpected_error:
                last_error = unexpected_error
                LOG_ERROR(
                    "API unexpected error",
                    service=self.name,
                    error=str(unexpected_error),
                    attempt=attempt,
                )
                METRICS.increment(f"api.{self.name}.unexpected_error")

                if attempt == self.max_retries:
                    raise APIClientError(f"Unexpected error: {unexpected_error}") from unexpected_error

                time.sleep(self.backoff_factor**attempt)

        raise APIClientError(f"Failed after {self.max_retries} retries: {last_error}")


perplexity_client = APIClient(
    name="perplexity",
    base_url=CONFIG["PERPLEXITY_BASE_URL"],
    api_key=CONFIG["PERPLEXITY_API_KEY"],
)

grok_client = APIClient(
    name="grok",
    base_url=CONFIG["GROK_BASE_URL"],
    api_key=CONFIG["GROK_API_KEY"],
)

LOG_INFO(
    "API clients initialized",
    perplexity=CONFIG["PERPLEXITY_BASE_URL"],
    grok=CONFIG["GROK_BASE_URL"],
)


# =============================================================================
# AUTHENTICATION & AUTHORIZATION
# =============================================================================


class AuthenticationError(PermissionError):
    """Raised when authentication fails."""


class AuthorizationError(PermissionError):
    """Raised when authorization fails."""


def validate_api_key(api_key: str | None) -> tuple[bool, str | None, bool]:
    """Validate an API key using configuration lists."""

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
    """Populate ``request.user_id`` and ``request.is_admin`` if the key is valid."""

    if not CONFIG["REQUIRE_AUTH"]:
        setattr(request, "user_id", "dev_user")
        setattr(request, "is_admin", True)
        return

    headers = getattr(request, "headers", {})
    api_key = headers.get(CONFIG["API_KEY_HEADER"]) if isinstance(headers, dict) else getattr(headers, "get", lambda *_: None)(CONFIG["API_KEY_HEADER"])

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
    """Ensure a request is made by an administrator."""

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


# =============================================================================
# INPUT VALIDATION & SANITIZATION
# =============================================================================


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


# =============================================================================
# RATE LIMITING
# =============================================================================


class RateLimitExceeded(RuntimeError):
    """Raised when rate limit is exceeded."""


def get_rate_limit_key(user_id: str, endpoint: str) -> str:
    """Generate a Redis key for rate limiting."""

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


F = TypeVar("F", bound=Callable[..., Any])


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


# =============================================================================
# REQUEST TIMEOUT DECORATOR
# =============================================================================

_timeout_executor = ThreadPoolExecutor(max_workers=max(CONFIG["WORKERS"] * 2, 8))


def _execute_with_timeout(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], seconds: int) -> Any:
    """Run a function in a thread pool and enforce a timeout."""

    future: Future[Any] = _timeout_executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=seconds)
    except FuturesTimeoutError as timeout_error:
        future.cancel()
        raise TimeoutError(f"Function call timed out after {seconds} seconds") from timeout_error


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
                    }, 504

            return cast(F, async_wrapper)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return _execute_with_timeout(func, args, kwargs, seconds)
            except TimeoutError:
                LOG_ERROR("Request timeout", function=func.__name__, timeout=seconds)
                METRICS.increment("request.timeout")
                return {
                    "status": "ERROR",
                    "error": "Request timeout",
                    "error_code": "TIMEOUT",
                }, 504

        return cast(F, wrapper)

    return decorator


# =============================================================================
# CORS CONFIGURATION
# =============================================================================


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
        response_headers = getattr(response, "headers", None)
        if response_headers is None or not isinstance(response_headers, dict):
            response_headers = {}
            setattr(response, "headers", response_headers)

        response_headers["Access-Control-Allow-Origin"] = origin
        response_headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response_headers["Access-Control-Allow-Headers"] = f"Content-Type, {CONFIG['API_KEY_HEADER']}"
        response_headers["Access-Control-Max-Age"] = str(CONFIG["CORS_MAX_AGE"])
        response_headers["Access-Control-Allow-Credentials"] = "true"

    return response


def handle_options_request() -> tuple[dict[str, str], int]:
    """Handle CORS preflight OPTIONS requests."""

    response = {"status": "ok"}
    return response, 200


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================


def MEASURE_REDIS_LATENCY() -> float | None:
    """Measure Redis latency in milliseconds."""

    try:
        start = time.time()
        raw_redis_connection.ping()
        latency = (time.time() - start) * 1000
        return round(latency, 2)
    except Exception:  # pragma: no cover - depends on Redis availability
        return None


def health_check() -> tuple[dict[str, Any], int]:
    """Minimal health check for load balancers."""

    health_status: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": CONFIG["ENVIRONMENT"],
        "checks": {},
    }

    all_healthy = True

    try:
        raw_redis_connection.ping()
        health_status["checks"]["redis"] = {"status": "ok", "latency_ms": MEASURE_REDIS_LATENCY()}
    except Exception as error:
        health_status["checks"]["redis"] = {"status": "error", "error": str(error)}
        all_healthy = False

    health_status["checks"]["api_clients"] = {
        "perplexity": "configured" if perplexity_client.api_key else "missing",
        "grok": "configured" if grok_client.api_key else "missing",
    }

    if all_healthy:
        health_status["status"] = "healthy"
        status_code = 200
    else:
        health_status["status"] = "unhealthy"
        status_code = 503

    return health_status, status_code


def readiness_check() -> tuple[dict[str, Any], int]:
    """Readiness check intended for orchestration systems."""

    checks = {"redis": False, "config": False, "api_clients": False}

    try:
        raw_redis_connection.ping()
        raw_redis_connection.get("readiness_test")
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    checks["config"] = bool(CONFIG["PERPLEXITY_API_KEY"] and CONFIG["GROK_API_KEY"])
    checks["api_clients"] = bool(perplexity_client.api_key and grok_client.api_key)

    all_ready = all(checks.values())
    status_code = 200 if all_ready else 503
    return {"ready": all_ready, "checks": checks}, status_code


# =============================================================================
# COST TRACKING
# =============================================================================


def track_request_cost(user_id: str, searches_used: int, duration_seconds: float) -> float:
    """Estimate the cost of handling a request."""

    search_cost = searches_used * CONFIG["COST_PER_SEARCH"]
    compute_cost = duration_seconds * CONFIG["COST_PER_SECOND"]
    total_cost = search_cost + compute_cost

    METRICS.histogram("cost.per_request", total_cost, user_id=user_id)
    METRICS.histogram("cost.searches", search_cost, user_id=user_id)
    METRICS.histogram("cost.compute", compute_cost, user_id=user_id)

    LOG_INFO(
        "Request cost tracked",
        user_id=user_id,
        searches=searches_used,
        duration=duration_seconds,
        search_cost=search_cost,
        compute_cost=compute_cost,
        total_cost=total_cost,
    )

    return total_cost


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def fuzzy_ratio(str1: str, str2: str) -> int:
    """Calculate fuzzy string match ratio (0-100)."""

    return int(fuzzy_fuzz.ratio(str1, str2))


def days_to_seconds(days: int) -> int:
    """Convert days into seconds."""

    return days * 24 * 60 * 60


def chunks(sequence: Iterable[Any], size: int) -> Generator[list[Any], None, None]:
    """Split an iterable into chunks of the requested size."""

    chunk: list[Any] = []
    for item in sequence:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def sha256_hash(text: str) -> str:
    """Generate SHA256 hash of a text string."""

    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# =============================================================================
# BACKGROUND JOBS SCHEDULER
# =============================================================================

background_scheduler = BackgroundScheduler()


def refresh_product_prices() -> None:
    """Placeholder job that refreshes stale product prices."""

    LOG_INFO("Price refresh job started")
    METRICS.increment("jobs.price_refresh.started")

    try:
        expiration_threshold = time.time() - days_to_seconds(CONFIG["PRICE_REFRESH_AGE_DAYS"])
        stale_keys = raw_redis_connection.zrangebyscore("product_prices:index", 0, expiration_threshold)
        if stale_keys:
            pipeline = raw_redis_connection.pipeline()
            for key in stale_keys:
                pipeline.delete(f"product_price:{key}")
                pipeline.zrem("product_prices:index", key)
            pipeline.execute()
            LOG_INFO("Removed stale product prices", count=len(stale_keys))
        else:
            LOG_INFO("No stale product prices found")
        METRICS.increment("jobs.price_refresh.completed")
    except Exception as error:  # pragma: no cover - depends on Redis schema
        LOG_ERROR("Price refresh job failed", error=str(error))
        METRICS.increment("jobs.price_refresh.failed")


def start_background_jobs() -> None:
    """Start background jobs when the application boots."""

    if not CONFIG["ENABLE_BACKGROUND_JOBS"]:
        LOG_INFO("Background jobs disabled")
        return

    if background_scheduler.running:
        LOG_INFO("Background jobs already running")
        return

    LOG_INFO("Starting background jobs")

    background_scheduler.add_job(
        func=refresh_product_prices,
        trigger="cron",
        hour=CONFIG["PRICE_REFRESH_HOUR"],
        minute=0,
        id="price_refresh",
        replace_existing=True,
        max_instances=1,
    )

    background_scheduler.start()
    LOG_INFO("Background jobs started", jobs=len(background_scheduler.get_jobs()))


def stop_background_jobs() -> None:
    """Stop background jobs during shutdown."""

    if background_scheduler.running:
        background_scheduler.shutdown(wait=True)
        LOG_INFO("Background jobs stopped")


# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================


def startup() -> None:
    """Application startup routine."""

    LOG_INFO("=== COMPAROO BACKEND STARTING ===")
    LOG_INFO("Environment", env=CONFIG["ENVIRONMENT"])
    LOG_INFO("Checking dependencies...")

    try:
        raw_redis_connection.ping()
        LOG_INFO("✓ Redis connection OK")

        if perplexity_client.api_key:
            LOG_INFO("✓ Perplexity API configured")

        if grok_client.api_key:
            LOG_INFO("✓ Grok API configured")

        if CONFIG["ENABLE_BACKGROUND_JOBS"]:
            start_background_jobs()
            LOG_INFO("✓ Background jobs started")

        LOG_INFO("=== STARTUP COMPLETE ===")
        METRICS.increment("app.startup.success")
    except Exception as error:
        LOG_ERROR("STARTUP FAILED", error=str(error))
        METRICS.increment("app.startup.failure")
        raise


def shutdown() -> None:
    """Application shutdown routine."""

    LOG_INFO("=== COMPAROO BACKEND SHUTTING DOWN ===")

    try:
        stop_background_jobs()
        raw_redis_connection.close()
        LOG_INFO("✓ Redis connection closed")
        METRICS.increment("app.shutdown.success")
    except Exception as error:
        LOG_ERROR("Error during shutdown", error=str(error))
        METRICS.increment("app.shutdown.failure")

    _timeout_executor.shutdown(wait=False)


# =============================================================================
# EXAMPLE .env FILE
# =============================================================================

EXAMPLE_ENV_FILE = """# Environment
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password_here
REDIS_DB=0
REDIS_MAX_CONNECTIONS=50

# API Keys (REQUIRED)
PERPLEXITY_API_KEY=your_perplexity_key_here
GROK_API_KEY=your_grok_key_here

# API Configuration
PERPLEXITY_BASE_URL=https://api.perplexity.ai
GROK_BASE_URL=https://api.x.ai/v1
API_REQUEST_TIMEOUT=30
API_MAX_RETRIES=3

# Authentication
API_KEY_HEADER=X-API-Key
ADMIN_API_KEYS=admin_key_1,admin_key_2
USER_API_KEYS=user_key_1,user_key_2,user_key_3
REQUIRE_AUTH=true

# CORS
CORS_ORIGINS=https://comparoo.com,https://www.comparoo.com
CORS_MAX_AGE=3600

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=60

# Search Budgets
MAX_TOTAL_SEARCHES=40
A1_SEARCH_BUDGET=10
B_SEARCH_BUDGET_PER_AGENT=4

# Request Limits
MAX_REQUEST_TIMEOUT=60
MAX_CATEGORY_LENGTH=200
MAX_CONSTRAINTS_LENGTH=500

# Background Jobs
ENABLE_BACKGROUND_JOBS=true
PRICE_REFRESH_HOUR=3
PRICE_REFRESH_AGE_DAYS=60

# Cost Tracking
COST_PER_SEARCH=0.005
COST_PER_SECOND=0.001
"""


# =============================================================================
# ENDPOINT WRAPPER WITH MIDDLEWARE
# =============================================================================


def generate_request_id() -> str:
    """Generate a unique, human-searchable request identifier."""

    return f"req_{int(time.time() * 1000)}_{token_hex(4)}"


def _get_request_method(request: Any) -> str:
    """Return the HTTP method for logging."""

    return getattr(request, "method", "UNKNOWN").upper()


def _get_request_path(request: Any) -> str:
    """Return the path associated with the request."""

    url = getattr(request, "url", None)
    if url and hasattr(url, "path"):
        return url.path
    return getattr(request, "path", "/unknown")


def _get_request_ip(request: Any) -> str:
    """Extract the caller IP address."""

    client = getattr(request, "client", None)
    if client and hasattr(client, "host") and client.host:
        return client.host
    return getattr(request, "remote_addr", "unknown")


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
    func: Callable[..., Any] | None = None,
    *,
    requires_auth: bool = True,
    requires_admin: bool = False,
    rate_limit_config: dict[str, int] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that layers logging, auth, rate limiting, metrics, and error handling."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
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
                    allowed, _, reset = check_rate_limit(user_id, fn.__name__, max_req, window)
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


# =============================================================================
# COMPARISON SERVICE HELPERS
# =============================================================================


async def run_full_comparison_with_caching(
    category: str,
    constraints: str | None,
    *,
    use_cache: bool = True,
) -> ComparisonResponse:
    """Execute the full comparison workflow using the orchestrator."""

    settings = get_settings()
    compare_request = CompareRequest(category=category, constraints=constraints, use_cache=use_cache)
    agent = ProductComparisonAgent.from_settings(settings=settings)
    try:
        return await agent.compare_products(compare_request)
    finally:
        await agent.close()


def _comparison_response_to_payload(result: ComparisonResponse) -> dict[str, Any]:
    """Convert the orchestrator response into the public API payload structure."""

    return {
        "status": "SUCCESS",
        "request": result.request.model_dump(mode="json"),
        "metrics": result.metrics.model_dump(mode="json"),
        "products": [product.model_dump(mode="json") for product in result.products],
        "comparison": result.comparison.model_dump(mode="json"),
        "comparison_table": result.comparison.metrics_table.model_dump(mode="json"),
        "metadata": {
            "workflow_stats": result.stats.model_dump(mode="json"),
            "cached_result": result.cached_result,
        },
        "cache_hit": result.cached_result,
        "generated_at": result.generated_at.isoformat(),
    }


# =============================================================================
# PUBLIC ENDPOINTS
# =============================================================================


@endpoint_wrapper(
    requires_auth=True,
    rate_limit_config={"requests": 10, "window": 60},
)
@timeout_decorator(seconds=CONFIG["MAX_REQUEST_TIMEOUT"])
async def compare_endpoint(request: Request) -> tuple[dict[str, Any], int]:
    """Handle POST /api/v1/compare requests."""

    LOG_INFO("Compare request received", user_id=getattr(request, "user_id", "anonymous"))

    try:
        data = await request.json()
    except Exception:
        return {
            "status": "ERROR",
            "error": "Invalid JSON in request body",
            "error_code": "INVALID_JSON",
        }, status.HTTP_400_BAD_REQUEST

    if not isinstance(data, dict):
        return {
            "status": "ERROR",
            "error": "Request body must be a JSON object",
            "error_code": "INVALID_JSON",
        }, status.HTTP_400_BAD_REQUEST

    is_valid, errors, sanitized_data = validate_comparison_request(data)

    if not is_valid or sanitized_data is None:
        LOG_WARNING("Invalid request", errors=errors, user_id=getattr(request, "user_id", "anonymous"))
        METRICS.increment("compare.validation_error")
        return {
            "status": "ERROR",
            "error": "Validation failed",
            "error_code": "VALIDATION_ERROR",
            "details": errors,
        }, status.HTTP_400_BAD_REQUEST

    category = sanitized_data["category"]
    constraints = sanitized_data["constraints"] or None

    LOG_INFO(
        "Processing comparison",
        category=category,
        constraints=constraints,
        user_id=getattr(request, "user_id", "anonymous"),
    )

    METRICS.increment("compare.request", category=category.replace(" ", "_"))

    comparison_start = time.time()

    try:
        result = await run_full_comparison_with_caching(category, constraints)
        comparison_duration = time.time() - comparison_start
        searches_used = result.stats.api_calls

        track_request_cost(getattr(request, "user_id", "anonymous"), searches_used, comparison_duration)

        LOG_INFO(
            "Comparison successful",
            user_id=getattr(request, "user_id", "anonymous"),
            category=category,
            products=len(result.products),
            searches=searches_used,
            duration=comparison_duration,
            from_cache=result.cached_result,
        )

        METRICS.increment("compare.success", from_cache=str(result.cached_result))

        payload = _comparison_response_to_payload(result)
        return payload, status.HTTP_200_OK

    except WorkflowBudgetExceeded as exc:
        LOG_ERROR(
            "Search budget exceeded",
            user_id=getattr(request, "user_id", "anonymous"),
            category=category,
            error=str(exc),
        )
        METRICS.increment("compare.budget_exceeded")
        return {
            "status": "ERROR",
            "error": "Search budget exceeded",
            "error_code": "BUDGET_EXCEEDED",
            "message": "Too many searches required for this query",
        }, status.HTTP_503_SERVICE_UNAVAILABLE

    except ValueError as exc:
        LOG_ERROR(
            "Comparison validation failure",
            user_id=getattr(request, "user_id", "anonymous"),
            category=category,
            error=str(exc),
        )
        METRICS.increment("compare.pipeline_error", error_code="validation_error")
        return {
            "status": "ERROR",
            "error": str(exc),
            "error_code": "VALIDATION_ERROR",
        }, status.HTTP_400_BAD_REQUEST

    except Exception as exc:
        LOG_ERROR(
            "Compare endpoint exception",
            user_id=getattr(request, "user_id", "anonymous"),
            category=category,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        METRICS.increment("compare.exception")
        return {
            "status": "ERROR",
            "error": "Internal server error",
            "error_code": "INTERNAL_ERROR",
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


@endpoint_wrapper(requires_auth=False)
async def health_endpoint(request: Request) -> tuple[dict[str, Any], int]:
    """GET /health: lightweight health signal for load balancers."""

    return health_check()


@endpoint_wrapper(requires_auth=False)
async def readiness_endpoint(request: Request) -> tuple[dict[str, Any], int]:
    """GET /ready: readiness probe for orchestration."""

    return readiness_check()


@endpoint_wrapper(requires_auth=False)
async def metrics_endpoint(request: Request) -> Response:
    """GET /metrics: Prometheus scrape endpoint."""

    content = prometheus_client.generate_latest().decode("utf-8")
    response = PlainTextResponse(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
    return response


# =============================================================================
# ADMIN HELPERS
# =============================================================================


def _normalize_cache_identifier(value: str | None) -> str:
    """Normalize identifiers for consistent cache key generation."""

    if not value:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower())
    return cleaned.strip("_")


def generate_product_cache_key(product_id: str | None, product_name: str) -> list[str]:
    """Return all Redis keys that may store product data for the provided identifiers."""

    patterns: list[str] = []
    normalized_name = _normalize_cache_identifier(product_name)
    if normalized_name:
        patterns.append(f"product:{normalized_name}:*")

    normalized_id = _normalize_cache_identifier(product_id)
    if normalized_id:
        patterns.append(f"product:{normalized_id}:*")

    keys: list[str] = []
    for pattern in patterns:
        keys.extend(list(raw_redis_connection.scan_iter(match=pattern, count=1000)))
    # Deduplicate while preserving discovery order.
    return list(dict.fromkeys(keys))


def generate_alias_key(product_name: str) -> str:
    """Alias keys allow quick lookup by product display name."""

    normalized = _normalize_cache_identifier(product_name)
    return f"alias:{normalized}" if normalized else ""


def generate_query_cache_key(category: str, constraints: str | None) -> str:
    """Produce the same cache key used by the orchestrator for comparison responses."""

    normalized_category = category.lower().strip()
    normalized_constraints = (constraints or "").lower().strip()
    hashed = sha256_hash(f"{normalized_category}|{normalized_constraints}")
    return f"comparison:{hashed}"


async def _delete_keys(keys: list[str]) -> int:
    """Delete multiple Redis keys in a background thread."""

    if not keys:
        return 0
    return await asyncio.to_thread(lambda: raw_redis_connection.delete(*keys))


async def _count_keys(pattern: str) -> int:
    """Count Redis keys matching a pattern without blocking the event loop."""

    return await asyncio.to_thread(lambda: sum(1 for _ in raw_redis_connection.scan_iter(match=pattern, count=1000)))


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================


@endpoint_wrapper(requires_auth=True, requires_admin=True)
async def admin_invalidate_product_cache(request: Request) -> tuple[dict[str, Any], int]:
    """POST /admin/cache/invalidate/product: remove cached product entries."""

    try:
        data = await request.json()
    except Exception:
        return {
            "status": "ERROR",
            "error": "Invalid JSON in request body",
            "error_code": "INVALID_JSON",
        }, status.HTTP_400_BAD_REQUEST

    if not isinstance(data, dict):
        return {
            "status": "ERROR",
            "error": "Request body must be a JSON object",
            "error_code": "INVALID_JSON",
        }, status.HTTP_400_BAD_REQUEST

    if "product_id" not in data or "product_name" not in data:
        return {
            "status": "ERROR",
            "error": "Missing required fields: product_id, product_name",
        }, status.HTTP_400_BAD_REQUEST

    product_id = str(data.get("product_id", "")).strip() or None
    product_name = str(data.get("product_name", "")).strip()

    LOG_INFO(
        "Admin invalidating product cache",
        admin_user=getattr(request, "user_id", "unknown_admin"),
        product_id=product_id,
        product=product_name,
    )

    keys = await asyncio.to_thread(generate_product_cache_key, product_id, product_name)
    deleted_primary = await _delete_keys(keys)

    alias_key = generate_alias_key(product_name)
    deleted_alias = await asyncio.to_thread(raw_redis_connection.delete, alias_key) if alias_key else 0

    if deleted_primary or deleted_alias:
        LOG_INFO(
            "Product cache invalidated",
            product_id=product_id,
            product=product_name,
            deleted_primary=deleted_primary,
            deleted_alias=deleted_alias,
        )
        METRICS.increment("admin.cache.invalidate.success")
        return {
            "status": "SUCCESS",
            "message": "Product will be re-indexed on next comparison",
            "deleted_keys": {
                "primary": deleted_primary,
                "alias": deleted_alias,
            },
        }, status.HTTP_200_OK

    LOG_INFO("Product not found in cache", product_id=product_id, product=product_name)
    METRICS.increment("admin.cache.invalidate.not_found")
    return {
        "status": "NOT_FOUND",
        "message": "Product not in cache",
    }, status.HTTP_404_NOT_FOUND


@endpoint_wrapper(requires_auth=True, requires_admin=True)
async def admin_invalidate_query_cache(request: Request) -> tuple[dict[str, Any], int]:
    """POST /admin/cache/invalidate/query: remove cached comparison results."""

    try:
        data = await request.json()
    except Exception:
        return {
            "status": "ERROR",
            "error": "Invalid JSON in request body",
            "error_code": "INVALID_JSON",
        }, status.HTTP_400_BAD_REQUEST

    if not isinstance(data, dict):
        return {
            "status": "ERROR",
            "error": "Request body must be a JSON object",
            "error_code": "INVALID_JSON",
        }, status.HTTP_400_BAD_REQUEST

    if "category" not in data:
        return {
            "status": "ERROR",
            "error": "Missing required field: category",
        }, status.HTTP_400_BAD_REQUEST

    category = str(data.get("category", "")).strip()
    constraints = str(data.get("constraints", "")).strip() or None

    LOG_INFO(
        "Admin invalidating query cache",
        admin_user=getattr(request, "user_id", "unknown_admin"),
        category=category,
        constraints=constraints,
    )

    key = generate_query_cache_key(category, constraints)
    deleted = await asyncio.to_thread(raw_redis_connection.delete, key)

    if deleted:
        LOG_INFO("Query cache invalidated", category=category, constraints=constraints)
        METRICS.increment("admin.cache.invalidate.query.success")
        return {
            "status": "SUCCESS",
            "message": "Query cache invalidated",
        }, status.HTTP_200_OK

    LOG_INFO("Query not found in cache", category=category, constraints=constraints)
    METRICS.increment("admin.cache.invalidate.query.not_found")
    return {
        "status": "NOT_FOUND",
        "message": "Query not in cache",
    }, status.HTTP_404_NOT_FOUND


@endpoint_wrapper(requires_auth=True, requires_admin=True)
async def admin_cache_stats(request: Request) -> tuple[dict[str, Any], int]:
    """GET /admin/cache/stats: provide cache inventory and Redis memory usage."""

    LOG_INFO("Admin requesting cache stats", admin_user=getattr(request, "user_id", "unknown_admin"))

    try:
        query_count, product_count, alias_count = await asyncio.gather(
            _count_keys("comparison:*"),
            _count_keys("product:*"),
            _count_keys("alias:*"),
        )

        redis_info = await asyncio.to_thread(raw_redis_connection.info, "memory")

        stats = {
            "cache_counts": {
                "queries": query_count,
                "products": product_count,
                "aliases": alias_count,
                "total": query_count + product_count + alias_count,
            },
            "redis_memory": {
                "used_memory_human": redis_info.get("used_memory_human", "unknown"),
                "used_memory_peak_human": redis_info.get("used_memory_peak_human", "unknown"),
                "maxmemory_human": redis_info.get("maxmemory_human", "not set"),
                "used_memory_bytes": redis_info.get("used_memory", 0),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        METRICS.increment("admin.cache.stats.success")
        return stats, status.HTTP_200_OK

    except Exception as exc:
        LOG_ERROR("Failed to get cache stats", error=str(exc), admin_user=getattr(request, "user_id", "unknown_admin"))
        METRICS.increment("admin.cache.stats.error")
        return {
            "status": "ERROR",
            "error": "Failed to retrieve cache stats",
            "details": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


@endpoint_wrapper(requires_auth=True, requires_admin=True)
async def admin_trigger_price_refresh(request: Request) -> tuple[dict[str, Any], int]:
    """POST /admin/jobs/trigger/price-refresh: manually start the price refresh job."""

    LOG_INFO("Admin triggering price refresh", admin_user=getattr(request, "user_id", "unknown_admin"))

    try:
        thread = threading.Thread(target=refresh_product_prices, name="price-refresh-manual", daemon=True)
        thread.start()

        METRICS.increment("admin.jobs.price_refresh.triggered")

        return {
            "status": "SUCCESS",
            "message": "Price refresh job triggered",
            "note": "Job is running asynchronously",
        }, status.HTTP_200_OK

    except Exception as exc:
        LOG_ERROR("Failed to trigger price refresh", error=str(exc), admin_user=getattr(request, "user_id", "unknown_admin"))
        return {
            "status": "ERROR",
            "error": "Failed to trigger job",
            "details": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# ERROR HANDLERS
# =============================================================================


def handle_404(_: Exception) -> tuple[dict[str, str], int]:
    """Return a consistent 404 error payload."""

    return {
        "status": "ERROR",
        "error": "Endpoint not found",
        "error_code": "NOT_FOUND",
    }, status.HTTP_404_NOT_FOUND


def handle_405(_: Exception) -> tuple[dict[str, str], int]:
    """Return a consistent 405 error payload."""

    return {
        "status": "ERROR",
        "error": "Method not allowed",
        "error_code": "METHOD_NOT_ALLOWED",
    }, status.HTTP_405_METHOD_NOT_ALLOWED


def handle_500(error: Exception) -> tuple[dict[str, str], int]:
    """Return a consistent 500 error payload."""

    LOG_ERROR("Unhandled error", error=str(error))
    return {
        "status": "ERROR",
        "error": "Internal server error",
        "error_code": "INTERNAL_ERROR",
    }, status.HTTP_500_INTERNAL_SERVER_ERROR


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Translate Starlette HTTP exceptions into our JSON envelope."""

    if exc.status_code == status.HTTP_404_NOT_FOUND:
        body, status_code = handle_404(exc)
    elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        body, status_code = handle_405(exc)
    else:
        body = {
            "status": "ERROR",
            "error": exc.detail or "HTTP error",
            "error_code": "HTTP_ERROR",
        }
        status_code = exc.status_code

    body["request_id"] = generate_request_id()
    response = JSONResponse(content=body, status_code=status_code)
    response.headers["X-Request-ID"] = body["request_id"]
    return response


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI request validation errors with descriptive feedback."""

    request_id = generate_request_id()
    payload = {
        "status": "ERROR",
        "error": "Validation failed",
        "error_code": "VALIDATION_ERROR",
        "details": exc.errors(),
        "request_id": request_id,
    }
    response = JSONResponse(content=payload, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    response.headers["X-Request-ID"] = request_id
    return response


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler to ensure we always respond with JSON."""

    request_id = generate_request_id()
    LOG_ERROR(
        "Unhandled exception",
        request_id=request_id,
        error=str(exc),
        traceback=traceback.format_exc(),
    )
    body, status_code = handle_500(exc)
    body["request_id"] = request_id
    if CONFIG["DEBUG"]:
        body["error_details"] = str(exc)
    response = JSONResponse(content=body, status_code=status_code)
    response.headers["X-Request-ID"] = request_id
    return response


# =============================================================================
# SERVER INITIALIZATION
# =============================================================================


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title="Comparoo Backend", version="1.0.0")
    router = APIRouter()

    # Public routes
    router.add_api_route("/api/v1/compare", compare_endpoint, methods=["POST", "OPTIONS"], include_in_schema=True)
    router.add_api_route("/health", health_endpoint, methods=["GET"], include_in_schema=False)
    router.add_api_route("/ready", readiness_endpoint, methods=["GET"], include_in_schema=False)
    router.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

    # Admin routes
    router.add_api_route(
        "/admin/cache/invalidate/product",
        admin_invalidate_product_cache,
        methods=["POST"],
        include_in_schema=False,
    )
    router.add_api_route(
        "/admin/cache/invalidate/query",
        admin_invalidate_query_cache,
        methods=["POST"],
        include_in_schema=False,
    )
    router.add_api_route(
        "/admin/cache/stats",
        admin_cache_stats,
        methods=["GET"],
        include_in_schema=False,
    )
    router.add_api_route(
        "/admin/jobs/trigger/price-refresh",
        admin_trigger_price_refresh,
        methods=["POST"],
        include_in_schema=False,
    )

    app.include_router(router)

    @app.on_event("startup")
    async def _on_startup() -> None:
        startup()

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:
        shutdown()

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    return app


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


if __name__ == "__main__":
    application = create_app()
    LOG_INFO("Starting server", host=CONFIG["HOST"], port=CONFIG["PORT"], workers=CONFIG["WORKERS"])

    try:
        import uvicorn

        uvicorn.run(
            application,
            host=CONFIG["HOST"],
            port=CONFIG["PORT"],
            workers=CONFIG["WORKERS"],
            reload=CONFIG["DEBUG"],
        )
    except ModuleNotFoundError:  # pragma: no cover - uvicorn optional in some envs
        LOG_ERROR("uvicorn is required to run the server directly. Please install uvicorn or use a WSGI server.")

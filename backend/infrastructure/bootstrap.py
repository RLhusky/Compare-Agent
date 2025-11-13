"""Core infrastructure bootstrap utilities shared across the backend."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Generator, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, cast

from dotenv import load_dotenv
import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import Counter, Gauge, Histogram
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionErrorType
from pathlib import Path

try:
    # FuzzyWuzzy is the requested library; RapidFuzz is a faster drop-in replacement.
    from fuzzywuzzy import fuzz as fuzzy_fuzz  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    try:
        from rapidfuzz import fuzz as fuzzy_fuzz  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Neither 'fuzzywuzzy' nor 'rapidfuzz' is installed. "
            "Install one of them to enable fuzzy matching support."
        ) from exc

# -----------------------------------------------------------------------------#
# Early bootstrap logging keeps configuration errors visible in plain stderr.  #
# -----------------------------------------------------------------------------#
_BOOTSTRAP_LOGGER = logging.getLogger("comparoo.bootstrap")
if not _BOOTSTRAP_LOGGER.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


MIN_PYTHON_VERSION = (3, 11)

if sys.version_info < MIN_PYTHON_VERSION:
    detected = ".".join(str(part) for part in sys.version_info[:3])
    raise RuntimeError(
        f"Comparoo backend requires Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]} "
        f"or newer. Detected: Python {detected}."
    )


# Load environment variables from backend/.env if present so local development
# automatically picks up API keys and other configuration without additional
# shell plumbing. Values already present in the environment take precedence.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


class ConfigurationError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _split_csv(raw_value: str) -> list[str]:
    """Convert a comma-separated env string into a clean list."""

    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def load_from_env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    """Return an environment variable or a default value."""

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
    """Read and validate the full application configuration."""

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
    config["REDIS_MAX_CONNECTIONS"] = _int_from_env(
        load_from_env("REDIS_MAX_CONNECTIONS", "50"),
        "REDIS_MAX_CONNECTIONS",
    )

    # API keys
    config["OPENROUTER_API_KEY"] = load_from_env("OPENROUTER_API_KEY", required=True)
    config["BRAVE_API_KEY"] = load_from_env("BRAVE_API_KEY", required=True)

    # API configuration
    config["OPENROUTER_BASE_URL"] = load_from_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    config["API_REQUEST_TIMEOUT"] = _int_from_env(load_from_env("API_REQUEST_TIMEOUT", "30"), "API_REQUEST_TIMEOUT")
    config["API_MAX_RETRIES"] = _int_from_env(load_from_env("API_MAX_RETRIES", "3"), "API_MAX_RETRIES")
    config["API_BACKOFF_FACTOR"] = _float_from_env(load_from_env("API_BACKOFF_FACTOR", "2"), "API_BACKOFF_FACTOR")

    # Authentication
    config["API_KEY_HEADER"] = load_from_env("API_KEY_HEADER", "X-API-Key")
    config["ADMIN_API_KEYS"] = _split_csv(load_from_env("ADMIN_API_KEYS", ""))
    config["USER_API_KEYS"] = _split_csv(load_from_env("USER_API_KEYS", ""))
    config["REQUIRE_AUTH"] = _boolean_from_env(load_from_env("REQUIRE_AUTH", "false"), "REQUIRE_AUTH")

    # CORS
    cors_origins = _split_csv(load_from_env("CORS_ORIGINS", "http://localhost:3000"))
    local_origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
    config["CORS_ORIGINS"] = sorted({*cors_origins, *local_origins})
    config["CORS_MAX_AGE"] = _int_from_env(load_from_env("CORS_MAX_AGE", "3600"), "CORS_MAX_AGE")

    # Rate limiting
    config["RATE_LIMIT_ENABLED"] = _boolean_from_env(load_from_env("RATE_LIMIT_ENABLED", "true"), "RATE_LIMIT_ENABLED")
    config["RATE_LIMIT_REQUESTS"] = _int_from_env(load_from_env("RATE_LIMIT_REQUESTS", "10"), "RATE_LIMIT_REQUESTS")
    config["RATE_LIMIT_WINDOW"] = _int_from_env(load_from_env("RATE_LIMIT_WINDOW", "60"), "RATE_LIMIT_WINDOW")

    # Search budgets
    config["MAX_TOTAL_SEARCHES"] = _int_from_env(load_from_env("MAX_TOTAL_SEARCHES", "40"), "MAX_TOTAL_SEARCHES")
    config["A1_SEARCH_BUDGET"] = _int_from_env(load_from_env("A1_SEARCH_BUDGET", "10"), "A1_SEARCH_BUDGET")
    config["B_SEARCH_BUDGET_PER_AGENT"] = _int_from_env(
        load_from_env("B_SEARCH_BUDGET_PER_AGENT", "4"),
        "B_SEARCH_BUDGET_PER_AGENT",
    )

    # Request limits
    config["MAX_REQUEST_TIMEOUT"] = _int_from_env(load_from_env("MAX_REQUEST_TIMEOUT", "60"), "MAX_REQUEST_TIMEOUT")
    config["MAX_CATEGORY_LENGTH"] = _int_from_env(load_from_env("MAX_CATEGORY_LENGTH", "200"), "MAX_CATEGORY_LENGTH")
    config["MAX_CONSTRAINTS_LENGTH"] = _int_from_env(
        load_from_env("MAX_CONSTRAINTS_LENGTH", "500"),
        "MAX_CONSTRAINTS_LENGTH",
    )

    # Background jobs
    config["ENABLE_BACKGROUND_JOBS"] = _boolean_from_env(
        load_from_env("ENABLE_BACKGROUND_JOBS", "true"),
        "ENABLE_BACKGROUND_JOBS",
    )
    config["PRICE_REFRESH_HOUR"] = _int_from_env(load_from_env("PRICE_REFRESH_HOUR", "3"), "PRICE_REFRESH_HOUR")
    config["PRICE_REFRESH_AGE_DAYS"] = _int_from_env(load_from_env("PRICE_REFRESH_AGE_DAYS", "60"), "PRICE_REFRESH_AGE_DAYS")

    # Cost tracking
    config["COST_PER_SEARCH"] = _float_from_env(load_from_env("COST_PER_SEARCH", "0.005"), "COST_PER_SEARCH")
    config["COST_PER_SECOND"] = _float_from_env(load_from_env("COST_PER_SECOND", "0.001"), "COST_PER_SECOND")

    if config["REQUIRE_AUTH"] and not config["ADMIN_API_KEYS"]:
        _BOOTSTRAP_LOGGER.warning("REQUIRE_AUTH is true but ADMIN_API_KEYS is empty.")
    if config["REQUIRE_AUTH"] and not config["USER_API_KEYS"]:
        _BOOTSTRAP_LOGGER.warning("REQUIRE_AUTH is true but USER_API_KEYS is empty.")

    _BOOTSTRAP_LOGGER.info("Configuration loaded", extra={"environment": config["ENVIRONMENT"]})
    return config


CONFIG = load_config()


def setup_logging() -> structlog.stdlib.BoundLogger:
    """Configure structured logging using structlog."""

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
    LOGGER.debug(message, **kwargs)


def LOG_INFO(message: str, **kwargs: Any) -> None:
    LOGGER.info(message, **kwargs)


def LOG_WARNING(message: str, **kwargs: Any) -> None:
    LOGGER.warning(message, **kwargs)


def LOG_ERROR(message: str, **kwargs: Any) -> None:
    LOGGER.error(message, **kwargs)


class MetricsCollector:
    """Lazy Prometheus collector that creates metrics on demand."""

    def __init__(self) -> None:
        self.counters: dict[str, Counter] = {}
        self.histograms: dict[str, Histogram] = {}
        self.gauges: dict[str, Gauge] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, value: float = 1.0, **labels: Any) -> None:
        with self._lock:
            counter = self.counters.get(name)
            if counter is None:
                label_names = list(labels.keys())
                counter = Counter(name.replace(".", "_"), f"Counter for {name}", labelnames=label_names or [])
                self.counters[name] = counter
        if labels:
            counter.labels(**labels).inc(value)
        else:
            counter.inc(value)

    def histogram(self, name: str, value: float, **labels: Any) -> None:
        with self._lock:
            histogram = self.histograms.get(name)
            if histogram is None:
                label_names = list(labels.keys())
                histogram = Histogram(name.replace(".", "_"), f"Histogram for {name}", labelnames=label_names or [])
                self.histograms[name] = histogram
        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)

    def gauge(self, name: str, value: float, **labels: Any) -> None:
        with self._lock:
            gauge = self.gauges.get(name)
            if gauge is None:
                label_names = list(labels.keys())
                gauge = Gauge(name.replace(".", "_"), f"Gauge for {name}", labelnames=label_names or [])
                self.gauges[name] = gauge
        if labels:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)


METRICS = MetricsCollector()


class RedisConnectionError(RuntimeError):
    """Raised when Redis connection initialisation fails."""


def initialize_redis() -> Redis:
    """Initialise a Redis connection with retry and configuration."""

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


raw_redis_connection = initialize_redis()


REQUEST_TIMEOUT_EXECUTOR = ThreadPoolExecutor(max_workers=max(CONFIG["WORKERS"] * 2, 8))

background_scheduler = BackgroundScheduler()


def days_to_seconds(days: int) -> int:
    return days * 24 * 60 * 60


def fuzzy_ratio(str1: str, str2: str) -> int:
    return int(fuzzy_fuzz.ratio(str1, str2))


def chunks(sequence: Iterable[Any], size: int) -> Generator[list[Any], None, None]:
    chunk: list[Any] = []
    for item in sequence:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def sha256_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def refresh_product_prices() -> None:
    """Placeholder background job that clears stale product price entries."""

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
    if background_scheduler.running:
        background_scheduler.shutdown(wait=True)
        LOG_INFO("Background jobs stopped")


def MEASURE_REDIS_LATENCY() -> float | None:
    try:
        start = time.time()
        raw_redis_connection.ping()
        latency = (time.time() - start) * 1000
        return round(latency, 2)
    except Exception:  # pragma: no cover
        return None


def health_check() -> tuple[dict[str, Any], int]:
    """Lightweight health check consumed by load balancers."""

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
        "openrouter": "configured" if CONFIG["OPENROUTER_API_KEY"] else "missing",
        "brave": "configured" if CONFIG["BRAVE_API_KEY"] else "missing",
    }

    if all_healthy:
        health_status["status"] = "healthy"
        status_code = 200
    else:
        health_status["status"] = "unhealthy"
        status_code = 503
    return health_status, status_code


def readiness_check() -> tuple[dict[str, Any], int]:
    checks = {"redis": False, "config": False, "api_clients": False}

    try:
        raw_redis_connection.ping()
        raw_redis_connection.get("readiness_test")
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    checks["config"] = bool(CONFIG["OPENROUTER_API_KEY"] and CONFIG["BRAVE_API_KEY"])
    checks["api_clients"] = checks["config"]

    all_ready = all(checks.values())
    status_code = 200 if all_ready else 503
    return {"ready": all_ready, "checks": checks}, status_code


def startup() -> None:
    """Application startup routine."""

    LOG_INFO("=== COMPAROO BACKEND STARTING ===")
    LOG_INFO("Environment", env=CONFIG["ENVIRONMENT"])
    LOG_INFO("Checking dependencies...")

    try:
        raw_redis_connection.ping()
        LOG_INFO("✓ Redis connection OK")

        if CONFIG["OPENROUTER_API_KEY"]:
            LOG_INFO("✓ OpenRouter API configured")

        if CONFIG["BRAVE_API_KEY"]:
            LOG_INFO("✓ Brave Search API configured")

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

    REQUEST_TIMEOUT_EXECUTOR.shutdown(wait=False)


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
OPENROUTER_API_KEY=your_openrouter_key_here
BRAVE_API_KEY=your_brave_key_here

# API Configuration
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
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


__all__ = [
    "CONFIG",
    "EXAMPLE_ENV_FILE",
    "LOG_DEBUG",
    "LOG_ERROR",
    "LOG_INFO",
    "LOG_WARNING",
    "METRICS",
    "MEASURE_REDIS_LATENCY",
    "REQUEST_TIMEOUT_EXECUTOR",
    "RedisConnectionError",
    "background_scheduler",
    "chunks",
    "days_to_seconds",
    "fuzzy_ratio",
    "health_check",
    "raw_redis_connection",
    "readiness_check",
    "refresh_product_prices",
    "sha256_hash",
    "shutdown",
    "start_background_jobs",
    "startup",
    "track_request_cost",
]


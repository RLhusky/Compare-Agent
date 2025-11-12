"""HTTP endpoint implementations for the Comparoo backend."""

from __future__ import annotations

import asyncio
import re
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Callable

import prometheus_client
from fastapi import Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.agent.orchestrator import ProductComparisonAgent, WorkflowBudgetExceeded
from backend.models.schemas import CompareRequest, ComparisonResponse
from config import get_settings

from .auth import validate_comparison_request
from .bootstrap import (
    CONFIG,
    LOG_ERROR,
    LOG_INFO,
    LOG_WARNING,
    METRICS,
    health_check,
    readiness_check,
    refresh_product_prices,
    raw_redis_connection,
    sha256_hash,
    track_request_cost,
)
from .middleware import endpoint_wrapper, generate_request_id, timeout_decorator
from .websocket_progress import get_broadcaster


async def run_full_comparison_with_caching(
    category: str,
    constraints: str | None,
    *,
    use_cache: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ComparisonResponse:
    """Execute the full comparison workflow using the orchestrator."""

    settings = get_settings()
    compare_request = CompareRequest(category=category, constraints=constraints, use_cache=use_cache)
    agent = ProductComparisonAgent.from_settings(settings=settings)
    try:
        return await agent.compare_products(compare_request, progress_callback=progress_callback)
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

    # Get session_id from request headers or body for WebSocket progress updates
    session_id = request.headers.get("X-Session-Id") or data.get("session_id")
    
    LOG_INFO(
        "Processing comparison",
        category=category,
        constraints=constraints,
        user_id=getattr(request, "user_id", "anonymous"),
        session_id=session_id,
    )

    METRICS.increment("compare.request", category=category.replace(" ", "_"))

    comparison_start = time.time()

    # Create progress callback if session_id is provided
    progress_callback = None
    if session_id:
        broadcaster = get_broadcaster()
        progress_callback = broadcaster.create_callback(session_id)

    try:
        result = await run_full_comparison_with_caching(
            category, constraints, progress_callback=progress_callback
        )
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

    return await asyncio.to_thread(health_check)


@endpoint_wrapper(requires_auth=False)
async def readiness_endpoint(request: Request) -> tuple[dict[str, Any], int]:
    """GET /ready: readiness probe for orchestration."""

    return await asyncio.to_thread(readiness_check)


@endpoint_wrapper(requires_auth=False)
async def metrics_endpoint(request: Request) -> Response:
    """GET /metrics: Prometheus scrape endpoint."""

    content = prometheus_client.generate_latest().decode("utf-8")
    response = PlainTextResponse(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
    return response


def _normalize_cache_identifier(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower())
    return cleaned.strip("_")


def generate_product_cache_key(product_id: str | None, product_name: str) -> list[str]:
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
    return list(dict.fromkeys(keys))


def generate_alias_key(product_name: str) -> str:
    normalized = _normalize_cache_identifier(product_name)
    return f"alias:{normalized}" if normalized else ""


def generate_query_cache_key(category: str, constraints: str | None) -> str:
    normalized_category = category.lower().strip()
    normalized_constraints = (constraints or "").lower().strip()
    hashed = sha256_hash(f"{normalized_category}|{normalized_constraints}")
    return f"comparison:{hashed}"


async def _delete_keys(keys: list[str]) -> int:
    if not keys:
        return 0
    return await asyncio.to_thread(lambda: raw_redis_connection.delete(*keys))


async def _count_keys(pattern: str) -> int:
    return await asyncio.to_thread(lambda: sum(1 for _ in raw_redis_connection.scan_iter(match=pattern, count=1000)))


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


def handle_404(_: Exception) -> tuple[dict[str, str], int]:
    return {
        "status": "ERROR",
        "error": "Endpoint not found",
        "error_code": "NOT_FOUND",
    }, status.HTTP_404_NOT_FOUND


def handle_405(_: Exception) -> tuple[dict[str, str], int]:
    return {
        "status": "ERROR",
        "error": "Method not allowed",
        "error_code": "METHOD_NOT_ALLOWED",
    }, status.HTTP_405_METHOD_NOT_ALLOWED


def handle_500(error: Exception) -> tuple[dict[str, str], int]:
    LOG_ERROR("Unhandled error", error=str(error))
    return {
        "status": "ERROR",
        "error": "Internal server error",
        "error_code": "INTERNAL_ERROR",
    }, status.HTTP_500_INTERNAL_SERVER_ERROR


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
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


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
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


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
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


__all__ = [
    "admin_cache_stats",
    "admin_invalidate_product_cache",
    "admin_invalidate_query_cache",
    "admin_trigger_price_refresh",
    "compare_endpoint",
    "generate_alias_key",
    "generate_product_cache_key",
    "generate_query_cache_key",
    "handle_404",
    "handle_405",
    "handle_500",
    "health_endpoint",
    "http_exception_handler",
    "metrics_endpoint",
    "readiness_endpoint",
    "run_full_comparison_with_caching",
    "unhandled_exception_handler",
    "validation_exception_handler",
]


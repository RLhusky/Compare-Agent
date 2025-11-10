"""FastAPI application factory wiring all infrastructure components together."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .bootstrap import shutdown, startup
from .endpoints import (
    admin_cache_stats,
    admin_invalidate_product_cache,
    admin_invalidate_query_cache,
    admin_trigger_price_refresh,
    compare_endpoint,
    health_endpoint,
    http_exception_handler,
    metrics_endpoint,
    readiness_endpoint,
    unhandled_exception_handler,
    validation_exception_handler,
)


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

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    return app


__all__ = ["create_app"]


"""FastAPI application factory wiring all infrastructure components together."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .bootstrap import CONFIG, shutdown, startup
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
from .websocket_progress import progress_websocket_endpoint


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title="Comparoo Backend", version="1.0.0")
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CONFIG["CORS_ORIGINS"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Session-Id"],
        max_age=CONFIG["CORS_MAX_AGE"],
    )
    
    router = APIRouter()

    # Public routes
    router.add_api_route("/api/v1/compare", compare_endpoint, methods=["POST", "OPTIONS"], include_in_schema=True)
    router.add_api_route("/health", health_endpoint, methods=["GET"], include_in_schema=False)
    router.add_api_route("/ready", readiness_endpoint, methods=["GET"], include_in_schema=False)
    router.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    
    # WebSocket route for progress updates
    @app.websocket("/ws/compare/{session_id}")
    async def websocket_progress(websocket: WebSocket, session_id: str) -> None:
        await progress_websocket_endpoint(websocket, session_id)

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


"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.routes import router as comparison_router
from backend.logging_config import configure_logging, get_logger
from config import Settings, get_settings

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    logger.info("application_startup", env=settings.env)
    try:
        yield
    finally:
        logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Product Comparison Agent", version="0.1.0", lifespan=lifespan)
    app.include_router(comparison_router)
    return app


app = create_app()

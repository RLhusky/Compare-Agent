"""FastAPI application entry point leveraging the infrastructure module."""

from __future__ import annotations

from backend.infrastructure import create_app

app = create_app()

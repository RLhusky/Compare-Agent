"""Allow `python -m backend.infrastructure` to run the API with uvicorn."""

from __future__ import annotations

from . import create_app
from .bootstrap import CONFIG, LOG_ERROR, LOG_INFO


def main() -> None:
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


if __name__ == "__main__":
    main()


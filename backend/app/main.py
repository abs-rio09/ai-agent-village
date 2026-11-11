"""FastAPI application: one process serves /api (and, from Part C, the built frontend)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import api_router
from app.config import get_settings


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail fast on invalid configuration (e.g. a non-loopback host)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Agent Village",
        version=__version__,
        lifespan=_lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(api_router)
    return app


app = create_app()


def run() -> None:
    """Start the single uvicorn worker. Host and port come only from validated settings."""
    import copy

    import uvicorn
    from uvicorn.config import LOGGING_CONFIG

    settings = get_settings()
    log_config = copy.deepcopy(LOGGING_CONFIG)
    for formatter in log_config["formatters"].values():  # timestamps for logs/village.log
        formatter["fmt"] = "%(asctime)s " + formatter["fmt"]
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level="info",
        log_config=log_config,
    )


if __name__ == "__main__":
    run()

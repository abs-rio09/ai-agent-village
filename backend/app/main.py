"""FastAPI application: one process serves /api (and, from Part C, the built frontend)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api import api_router
from app.config import get_settings

_ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "[::1]"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _hostname(host_header: str) -> str:
    """Host header without the port ("[::1]:8000" -> "[::1]", "localhost:8000" -> "localhost")."""
    if host_header.endswith("]"):
        return host_header
    return host_header.rsplit(":", 1)[0] if ":" in host_header else host_header


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

    @app.middleware("http")
    async def _local_requests_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Host allowlist: blocks DNS-rebinding (a foreign domain resolving to 127.0.0.1).
        host = request.headers.get("host", "")
        if _hostname(host).lower() not in _ALLOWED_HOSTNAMES:
            return JSONResponse(status_code=400, content={"detail": "Invalid Host header"})
        # Same-origin check for state-changing API calls: other local web apps on different
        # ports count as "same-site", so SameSite=Strict alone does not stop them.
        if request.method not in _SAFE_METHODS and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin is not None and urlsplit(origin).netloc.lower() != host.lower():
                return JSONResponse(status_code=403, content={"detail": "Cross-origin request rejected"})
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default handler echoes the rejected input back. That input can be a
        # password or an API key, so only location, message and type are returned.
        errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

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

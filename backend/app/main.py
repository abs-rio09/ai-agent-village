"""FastAPI application: one process serves /api and the built frontend (frontend/dist)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app import __version__
from app.api import api_router
from app.config import get_settings

_ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "[::1]"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}

_NOT_BUILT_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AI Agent Village</title></head>
<body style="font-family: system-ui, sans-serif; background: #0a1211; color: #dfe9e4; padding: 3rem;">
<h1>AI Agent Village</h1>
<p>The backend is running, but the frontend has not been built yet.</p>
<p>Run <code>./village setup</code> in the project folder, then reload this page.</p>
</body>
</html>
"""


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
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default handler echoes the rejected input back. That input can be a
        # password or an API key, so only location, message and type are returned.
        errors = [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    app.include_router(api_router)

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def _frontend(full_path: str) -> Response:
        """Serve the built frontend: real files from dist, index.html for every other path."""
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        dist = get_settings().dist_path.resolve()
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(_NOT_BUILT_HTML, status_code=503)
        if full_path:
            candidate = (dist / full_path).resolve()
            if candidate.is_relative_to(dist) and candidate.is_file():
                if full_path.startswith("assets/"):  # content-hashed by Vite
                    return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"})
                return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
            if full_path.startswith("assets/"):
                raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})  # SPA fallback

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

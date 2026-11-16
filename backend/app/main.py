"""FastAPI application: one process serves /api and the built frontend (frontend/dist)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import inspect

from app import __version__
from app.api import api_router
from app.config import get_settings
from app.db import get_engine
from app.seed import seed_if_migrated
from app.task_runner import TaskWorker

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LOOPBACK_PEERS = {"127.0.0.1", "::1"}


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "manifest-src 'self'; worker-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}

# Files of the installable app (PWA) that browsers are strict about: the service worker must be
# JavaScript and must be re-checked on every load, the manifest has its own media type.
_PWA_MEDIA_TYPES = {
    "sw.js": "text/javascript",
    "manifest.webmanifest": "application/manifest+json",
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


def _first(value: str) -> str:
    """The first entry of a forwarded header ("a, b" when several proxies added to it)."""
    return value.split(",", 1)[0].strip()


def _is_local_proxy(request: Request) -> bool:
    """True when the TCP connection itself comes from this PC. The server only listens on
    127.0.0.1, so a remote device can only arrive through a local proxy (`tailscale serve`)."""
    return request.client is not None and request.client.host in _LOOPBACK_PEERS


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # fail fast on invalid configuration (e.g. a non-loopback host)
    worker: TaskWorker | None = None
    if settings.db_file.exists():  # never create the database here: that is `./village setup`
        engine = get_engine()
        # Idempotent: puts back a missing agent template or a missing Central Manager.
        seed_if_migrated(engine)
        if settings.task_worker:
            if inspect(engine).has_table("task"):
                worker = TaskWorker()
                worker.start()  # first queues tasks again that a crash left RUNNING
            else:
                logging.getLogger("village.tasks").warning(
                    "the task worker was not started: the database has no task table (run ./village setup)"
                )
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()


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
        # Loopback names are always allowed; VILLAGE_ALLOWED_HOSTS adds, for example, the
        # Tailscale name of this PC. Everything else is refused.
        allowed = get_settings().allowed_hostnames
        host = request.headers.get("host", "")
        if _hostname(host).lower() not in allowed:
            return JSONResponse(status_code=400, content={"detail": "Invalid Host header"})

        # What the browser really used. X-Forwarded-Host / -Proto are believed only when the
        # connection comes from this PC (the local Tailscale proxy) AND the forwarded host is
        # on the allowlist. From any other peer they are ignored.
        public_host, scheme = host, request.url.scheme
        if _is_local_proxy(request):
            forwarded_host = request.headers.get("x-forwarded-host")
            if forwarded_host is not None:
                forwarded_host = _first(forwarded_host)
                if _hostname(forwarded_host).lower() not in allowed:
                    return JSONResponse(status_code=400, content={"detail": "Invalid Host header"})
                public_host = forwarded_host
            forwarded_proto = _first(request.headers.get("x-forwarded-proto", "")).lower()
            if forwarded_proto in ("http", "https"):
                scheme = forwarded_proto
        request.state.secure = scheme == "https"  # → the session cookie gets the Secure flag

        # Same-origin check for state-changing API calls: other local web apps on different
        # ports count as "same-site", so SameSite=Strict alone does not stop them.
        if request.method not in _SAFE_METHODS and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin is not None and urlsplit(origin).netloc.lower() != public_host.lower():
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
                return FileResponse(
                    candidate, media_type=_PWA_MEDIA_TYPES.get(full_path), headers={"Cache-Control": "no-cache"}
                )
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
    # The application's own messages (tasks, revoked sessions, lockouts) go to the same log.
    log_config["loggers"]["village"] = {"handlers": ["default"], "level": "INFO", "propagate": False}
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level="info",
        log_config=log_config,
        # uvicorn must not rewrite the client address from X-Forwarded-For: the middleware
        # needs the real TCP peer to decide whether forwarded headers may be trusted at all.
        proxy_headers=False,
    )


if __name__ == "__main__":
    run()

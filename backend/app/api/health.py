"""GET /api/health — public liveness/readiness probe. Never returns secrets."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db import get_session
from app.models import get_meta

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    db_ok: bool
    journal_mode: str | None
    demo_mode: bool
    setup_completed: bool


@router.get("/health", response_model=HealthResponse)
def health(response: Response, session: Session = Depends(get_session)) -> HealthResponse:
    journal_mode: str | None = None
    setup_completed = False
    try:
        journal_mode = str(session.execute(text("PRAGMA journal_mode")).scalar_one())
        setup_completed = get_meta(session, "setup_completed") == "true"
        db_ok = True
    except SQLAlchemyError:
        db_ok = False
    if not db_ok:
        response.status_code = 503
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=__version__,
        db_ok=db_ok,
        journal_mode=journal_mode,
        demo_mode=get_settings().demo_mode,
        setup_completed=setup_completed,
    )

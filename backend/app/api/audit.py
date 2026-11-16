"""GET /api/audit — read the audit log. There is no route that changes or deletes an entry."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import as_utc, get_session
from app.models import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    id: int
    created_at: datetime
    actor: str  # "chairman:<username>", "agent:<id>", "system" or "unknown user"
    action: str
    agent_id: int | None
    agent_name: str | None
    task_id: int | None
    tool_key: str | None
    decision: str | None
    summary: str
    details: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditEntryOut]
    total: int  # entries that match the filters
    limit: int
    offset: int
    actions: list[str]  # every action that occurs in the log, for the filter


@router.get("", response_model=AuditPage)
def list_audit(
    agent_id: int | None = Query(default=None),
    task_id: int | None = Query(default=None),
    action: str | None = Query(default=None, max_length=48, pattern=r"^[a-z_.]+$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
) -> AuditPage:
    """Newest first. `action` is an exact action ("tool.denied") or a whole group ("tool")."""
    filters = []
    if agent_id is not None:
        filters.append(AuditLog.agent_id == agent_id)
    if task_id is not None:
        filters.append(AuditLog.task_id == task_id)
    if action:
        filters.append(AuditLog.action == action if "." in action else AuditLog.action.like(f"{action}.%"))
    total = db.execute(select(func.count()).select_from(AuditLog).where(*filters)).scalar_one()
    rows = db.execute(select(AuditLog).where(*filters).order_by(AuditLog.id.desc()).limit(limit).offset(offset)).scalars()
    return AuditPage(
        items=[
            AuditEntryOut(
                id=row.id,
                created_at=as_utc(row.created_at),  # type: ignore[arg-type]
                actor=row.actor,
                action=row.action,
                agent_id=row.agent_id,
                agent_name=row.agent_name,
                task_id=row.task_id,
                tool_key=row.tool_key,
                decision=row.decision,
                summary=row.summary,
                details=dict(row.details or {}),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        actions=sorted(db.execute(select(AuditLog.action).distinct()).scalars()),
    )

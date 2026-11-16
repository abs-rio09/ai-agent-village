"""GET /api/activity/recent — the dashboard's "Recent Activity" feed.

Built at request time from two things the database already holds, and from nothing else:
  • the audit log (tool use, approvals, agent changes, logins, memory, schedules), and
  • the tasks' own timestamps (created, finished).
No event is invented and nothing is stored for this feed. Audit summaries are already free of
secrets; task titles are passed through the same cleaning before they are shown.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import clean_text
from app.db import as_utc, get_session
from app.models import Agent, AuditLog, Task
from app.task_status import CANCELLED, FAILED, SUCCEEDED

router = APIRouter(prefix="/activity", tags=["activity"])

Tone = Literal["good", "bad", "warn", "info", "muted"]
HOUSEKEEPING = "health_check"
# The Central Manager's delegation is shown once, as "delegated task #n", not also as a tool call.
_SKIP_TOOL = "task.create_child"


class ActivityEvent(BaseModel):
    id: str  # "audit:12" or "task:5:created" — stable, unique in the feed
    time: datetime
    source: Literal["audit", "task"]
    action: str  # the audit action, or "task.created" / "task.succeeded" / "task.failed" / "task.cancelled"
    actor: str  # "Chairman (riyan)", "Mina", "System", "Schedule"
    agent_id: int | None
    task_id: int | None
    text: str
    link: str | None  # where the dashboard sends you for the details (a path of the app)
    tone: Tone


def _actor(raw: str, agent_name: str | None, names: dict[int, str]) -> str:
    kind, _, value = raw.partition(":")
    if kind == "chairman":
        return f"Chairman ({value})"
    if kind == "agent":
        return agent_name or names.get(int(value) if value.isdigit() else 0) or f"Agent #{value}"
    if kind == "schedule":
        return "Schedule"
    if raw == "system":
        return "System"
    return raw  # "unknown user", or the username that created a task


def _task_creator(created_by: str, names: dict[int, str]) -> str:
    """A task's creator is a bare username (the Chairman), "agent:<id>" or "schedule:<id>"."""
    if created_by.startswith(("agent:", "schedule:")):
        return _actor(created_by, None, names)
    return f"Chairman ({created_by})"


_AUDIT_TONE: dict[str, Tone] = {"denied": "bad", "rejected": "bad", "failed": "bad", "approved": "good", "pending": "warn"}


def _audit_link(row: AuditLog) -> str | None:
    group = row.action.split(".", 1)[0]
    details = row.details or {}
    if group == "approval" and isinstance(details.get("approval_id"), int):
        return f"/approvals?id={details['approval_id']}"
    if row.task_id is not None:
        return f"/tasks?id={row.task_id}"
    if group == "agent" and row.agent_id is not None and row.action != "agent.deleted":
        return f"/agents/profile?id={row.agent_id}"
    return {"memory": "/memory", "schedule": "/schedules", "auth": "/settings", "settings": "/settings"}.get(group, f"/audit?action={row.action}")


def _title(task: Task) -> str:
    return clean_text(task.title, 120)


@router.get("/recent", response_model=list[ActivityEvent])
def recent_activity(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_session)) -> list[ActivityEvent]:
    """The newest events first. Three small queries (plus one for agent names)."""
    audit_rows = list(
        db.execute(
            select(AuditLog)
            .where((AuditLog.tool_key.is_(None)) | (AuditLog.tool_key != _SKIP_TOOL) | (AuditLog.action != "tool.allowed"))
            .order_by(AuditLog.id.desc())
            .limit(limit)
        ).scalars()
    )
    real = Task.kind != HOUSEKEEPING
    created = list(db.execute(select(Task).where(real).order_by(Task.id.desc()).limit(limit)).scalars())
    finished = list(
        db.execute(
            select(Task)
            .where(real, Task.completed_at.is_not(None), Task.status.in_((SUCCEEDED, FAILED, CANCELLED)))
            .order_by(Task.completed_at.desc())
            .limit(limit)
        ).scalars()
    )
    agent_ids = {task.assigned_agent_id for task in (*created, *finished) if task.assigned_agent_id is not None}
    agent_ids |= {int(task.created_by[6:]) for task in created if task.created_by.startswith("agent:") and task.created_by[6:].isdigit()}
    names: dict[int, str] = (
        dict(db.execute(select(Agent.id, Agent.display_name).where(Agent.id.in_(agent_ids))).all()) if agent_ids else {}
    )

    events: list[ActivityEvent] = []
    for row in audit_rows:
        events.append(
            ActivityEvent(
                id=f"audit:{row.id}",
                time=as_utc(row.created_at),  # type: ignore[arg-type]
                source="audit",
                action=row.action,
                actor=_actor(row.actor, row.agent_name if row.actor.startswith("agent:") else None, names),
                agent_id=row.agent_id,
                task_id=row.task_id,
                text=row.summary,
                link=_audit_link(row),
                tone=_AUDIT_TONE.get(row.decision or "", "info" if row.action.startswith("tool.") else "muted"),
            )
        )
    for task in created:
        agent = names.get(task.assigned_agent_id or 0)
        if task.kind == "delegated":
            text = f"Task #{task.id} “{_title(task)}” was delegated to {agent or 'an agent'}."
        elif task.kind == "scheduled":
            text = f"A schedule created task #{task.id} “{_title(task)}” for {agent or 'an agent'}."
        elif task.kind == "daily_report":
            text = f"The daily report schedule created task #{task.id} “{_title(task)}”."
        else:
            text = f"Request #{task.id} “{_title(task)}” was sent to the Central Manager."
        events.append(
            ActivityEvent(
                id=f"task:{task.id}:created",
                time=as_utc(task.created_at),  # type: ignore[arg-type]
                source="task",
                action="task.created",
                actor=_task_creator(task.created_by, names),
                agent_id=task.assigned_agent_id,
                task_id=task.id,
                text=text,
                link=f"/tasks?id={task.id}",
                tone="info",
            )
        )
    for task in finished:
        word, tone = {SUCCEEDED: ("succeeded", "good"), FAILED: ("failed", "bad"), CANCELLED: ("was cancelled", "muted")}[task.status]
        events.append(
            ActivityEvent(
                id=f"task:{task.id}:{task.status.lower()}",
                time=as_utc(task.completed_at),  # type: ignore[arg-type]
                source="task",
                action=f"task.{task.status.lower()}",
                actor=names.get(task.assigned_agent_id or 0, "System"),
                agent_id=task.assigned_agent_id,
                task_id=task.id,
                text=f"Task #{task.id} “{_title(task)}” {word}.",
                link=f"/tasks?id={task.id}",
                tone=tone,  # type: ignore[arg-type]
            )
        )
    events.sort(key=lambda event: (event.time, event.id), reverse=True)
    return events[:limit]

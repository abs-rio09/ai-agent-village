"""Schedules API: list, create, pause, resume, delete.

A schedule creates a task for one agent at an interval or at a time of day; the task runner
does the work. The two built-in schedules (agent health check, daily report) can be paused
but not deleted. Every change is written to the audit log.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, scheduler
from app.api.tasks import AgentRef
from app.db import as_utc, get_session, utcnow
from app.models import Agent, Schedule, Task
from app.security import AuthContext, current_auth

router = APIRouter(prefix="/schedules", tags=["schedules"])

ScheduleName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
RequestText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
_CLOCK = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ScheduleOut(BaseModel):
    id: int
    name: str
    kind: Literal["builtin", "custom"]
    builtin_key: str | None
    agent: AgentRef | None  # who gets the task (None for the built-in system schedules)
    request_text: str  # what the task asks for; for a built-in schedule: what it does
    trigger_type: Literal["interval", "daily"]
    interval_minutes: int | None
    daily_time: str | None  # "HH:MM" in the village's timezone
    trigger_text: str  # "every 10 minutes", "every day at 21:00"
    paused: bool
    last_run_at: datetime | None
    last_task_id: int | None
    last_task_status: str | None
    next_run_at: datetime | None  # None while paused or while the scheduler is not running
    created_at: datetime


class SchedulesPage(BaseModel):
    scheduler_running: bool
    timezone: str
    schedules: list[ScheduleOut]


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ScheduleName = ""
    agent_id: int
    request_text: RequestText
    trigger_type: Literal["interval", "daily"]
    interval_minutes: int | None = Field(default=None, ge=scheduler.MIN_INTERVAL_MINUTES, le=scheduler.MAX_INTERVAL_MINUTES)
    daily_time: str | None = None

    @model_validator(mode="after")
    def _trigger_is_complete(self) -> ScheduleCreate:
        if self.trigger_type == "interval":
            if self.interval_minutes is None:
                raise ValueError("interval_minutes is required for an interval schedule")
            self.daily_time = None
        else:
            if self.daily_time is None or not _CLOCK.fullmatch(self.daily_time):
                raise ValueError("daily_time must be a time of day like 09:30")
            self.interval_minutes = None
        return self


class ScheduleDeleted(BaseModel):
    deleted: bool


def _out(db: Session, rows: list[Schedule]) -> list[ScheduleOut]:
    engine = scheduler.get_scheduler()
    tz = scheduler.village_timezone(db)
    now = utcnow()
    agents = {
        agent.id: agent
        for agent in db.execute(select(Agent).where(Agent.id.in_({row.agent_id for row in rows if row.agent_id}))).scalars()
    } if rows else {}
    task_ids = {row.last_task_id for row in rows if row.last_task_id is not None}
    statuses = dict(db.execute(select(Task.id, Task.status).where(Task.id.in_(task_ids))).all()) if task_ids else {}
    result = []
    for row in rows:
        agent = agents.get(row.agent_id or 0)
        # The real job's time when APScheduler has one; the same value computed from the row otherwise.
        upcoming = None
        if engine.running and not row.paused:
            upcoming = engine.job_next_run(row.id) or scheduler.next_run_time(row, now, tz)
        result.append(
            ScheduleOut(
                id=row.id,
                name=row.name,
                kind=row.kind,  # type: ignore[arg-type]
                builtin_key=row.builtin_key,
                agent=AgentRef(
                    id=agent.id,
                    display_name=agent.display_name,
                    role=agent.role,
                    avatar_key=agent.avatar_key,
                    is_central_manager=agent.is_central_manager,
                )
                if agent is not None
                else None,
                request_text=row.request_text,
                trigger_type=row.trigger_type,  # type: ignore[arg-type]
                interval_minutes=row.interval_minutes,
                daily_time=row.daily_time,
                trigger_text=scheduler.describe_trigger(row),
                paused=row.paused,
                last_run_at=as_utc(row.last_run_at),
                last_task_id=row.last_task_id if row.last_task_id in statuses else None,
                last_task_status=statuses.get(row.last_task_id or 0),
                next_run_at=as_utc(upcoming),
                created_at=as_utc(row.created_at),  # type: ignore[arg-type]
            )
        )
    return result


def _get(db: Session, schedule_id: int) -> Schedule:
    row = db.get(Schedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return row


def _audit(db: Session, auth: AuthContext, action: str, row: Schedule, summary: str) -> None:
    audit.record(
        db,
        action,
        actor=audit.chairman(auth.user.username),
        agent=db.get(Agent, row.agent_id) if row.agent_id is not None else None,
        summary=summary,
        details={"schedule_id": row.id, "trigger": scheduler.describe_trigger(row)},
    )


@router.get("", response_model=SchedulesPage)
def list_schedules(db: Session = Depends(get_session)) -> SchedulesPage:
    scheduler.ensure_builtin_schedules(db)
    rows = list(db.execute(select(Schedule).order_by(Schedule.kind, Schedule.id)).scalars())
    return SchedulesPage(
        scheduler_running=scheduler.get_scheduler().running,
        timezone=scheduler.village_timezone(db).key,
        schedules=_out(db, rows),
    )


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduleCreate, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> ScheduleOut:
    agent = db.get(Agent, body.agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent.is_central_manager:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Central Manager only routes requests. Choose the agent that should do the work.",
        )
    count = db.execute(select(func.count()).select_from(Schedule).where(Schedule.kind == "custom")).scalar_one()
    if count >= scheduler.MAX_CUSTOM_SCHEDULES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"There are already {scheduler.MAX_CUSTOM_SCHEDULES} schedules. Delete one before adding another.",
        )
    row = Schedule(
        name=body.name or body.request_text.splitlines()[0][:120],
        kind="custom",
        agent_id=agent.id,
        request_text=body.request_text,
        trigger_type=body.trigger_type,
        interval_minutes=body.interval_minutes,
        daily_time=body.daily_time,
        paused=False,
        anchor_at=utcnow().replace(microsecond=0),
    )
    db.add(row)
    db.flush()
    _audit(db, auth, "schedule.created", row, f"Created schedule '{row.name}' for '{agent.display_name}': {scheduler.describe_trigger(row)}.")
    db.commit()
    scheduler.get_scheduler().apply(row)
    return _out(db, [row])[0]


def _set_paused(schedule_id: int, paused: bool, auth: AuthContext, db: Session) -> ScheduleOut:
    row = _get(db, schedule_id)
    if row.paused != paused:
        row.paused = paused
        word = "Paused" if paused else "Resumed"
        _audit(db, auth, "schedule.paused" if paused else "schedule.resumed", row, f"{word} schedule '{row.name}'.")
        db.commit()
    scheduler.get_scheduler().apply(row)
    return _out(db, [row])[0]


@router.post("/{schedule_id}/pause", response_model=ScheduleOut)
def pause_schedule(
    schedule_id: int, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> ScheduleOut:
    """A paused schedule creates no tasks."""
    return _set_paused(schedule_id, True, auth, db)


@router.post("/{schedule_id}/resume", response_model=ScheduleOut)
def resume_schedule(
    schedule_id: int, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> ScheduleOut:
    return _set_paused(schedule_id, False, auth, db)


@router.delete("/{schedule_id}", response_model=ScheduleDeleted)
def delete_schedule(
    schedule_id: int, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> ScheduleDeleted:
    row = _get(db, schedule_id)
    if row.kind == "builtin":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A built-in schedule cannot be deleted. Pause it instead."
        )
    _audit(db, auth, "schedule.deleted", row, f"Deleted schedule '{row.name}'. The tasks it created are kept.")
    db.delete(row)
    db.commit()
    scheduler.get_scheduler().remove(schedule_id)
    return ScheduleDeleted(deleted=True)

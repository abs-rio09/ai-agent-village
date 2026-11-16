"""Task API: send a request to the Central Manager, follow it, cancel it.

Tasks are executed by the background worker (app/task_runner.py), never inside a request.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import task_runner  # the module, not its names: task_runner imports this package too
from app.db import as_utc, get_session
from app.models import Agent, AgentMessage, AgentTemplate, Approval, Task
from app.security import AuthContext, current_auth
from app.task_status import ACTIVE, CANCELLED, QUEUED, TERMINAL

router = APIRouter(prefix="/tasks", tags=["tasks"])

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TaskText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Status = Literal["QUEUED", "ASSIGNED", "RUNNING", "WAITING_APPROVAL", "SUCCEEDED", "FAILED", "CANCELLED"]
Priority = Literal["low", "normal", "high"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: TaskText = ""
    priority: Priority = "normal"


class AgentRef(BaseModel):
    id: int
    display_name: str
    role: str
    avatar_key: str
    template_key: str | None = None  # which of the 15 templates it was made from (→ its robot)
    is_central_manager: bool


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    created_by: str  # a username, or "agent:<id>" for a delegated task
    created_by_name: str
    assigned_agent: AgentRef | None
    parent_task_id: int | None
    depth: int
    # request | delegated | scheduled | daily_report | health_check
    kind: str
    priority: Priority
    input: dict[str, Any]
    output: str | None
    status: Status
    child_count: int
    # An open approval request of this task, or of a task below it (None = nothing waits for the Chairman).
    pending_approval_id: int | None = None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None


class MessageOut(BaseModel):
    id: int
    sender: AgentRef | None
    receiver: AgentRef | None
    task_id: int
    type: Literal["delegation", "result", "info_request"]
    payload: dict[str, Any]
    created_at: datetime


class TaskDetail(TaskOut):
    children: list[TaskOut]
    messages: list[MessageOut]  # of this task and of every task below it, oldest first


def agent_refs(db: Session, agent_ids: set[int]) -> dict[int, AgentRef]:
    """Short descriptions of agents for task, approval and schedule responses (one query)."""
    if not agent_ids:
        return {}
    rows = db.execute(
        select(Agent, AgentTemplate.key)
        .outerjoin(AgentTemplate, AgentTemplate.id == Agent.template_id)
        .where(Agent.id.in_(agent_ids))
    ).all()
    return {
        agent.id: AgentRef(
            id=agent.id,
            display_name=agent.display_name,
            role=agent.role,
            avatar_key=agent.avatar_key,
            template_key=template_key,
            is_central_manager=agent.is_central_manager,
        )
        for agent, template_key in rows
    }


def _creator_agent_id(created_by: str) -> int | None:
    kind, _, value = created_by.partition(":")
    return int(value) if kind == "agent" and value.isdigit() else None


def _tasks_out(db: Session, tasks: list[Task]) -> list[TaskOut]:
    """TaskOut for many tasks with two extra queries (agents, child counts), whatever the number."""
    agent_ids = {task.assigned_agent_id for task in tasks if task.assigned_agent_id is not None}
    agent_ids |= {creator for task in tasks if (creator := _creator_agent_id(task.created_by)) is not None}
    agents = agent_refs(db, agent_ids)
    ids = [task.id for task in tasks]
    child_counts: dict[int, int] = {}
    if ids:
        child_counts = dict(
            db.execute(
                select(Task.parent_task_id, func.count()).where(Task.parent_task_id.in_(ids)).group_by(Task.parent_task_id)
            ).all()
        )
    waiting = _pending_approvals(db, set(ids))
    result = []
    for task in tasks:
        creator = _creator_agent_id(task.created_by)
        if creator is None:
            created_by_name = task.created_by
        else:
            created_by_name = agents[creator].display_name if creator in agents else f"Agent #{creator}"
        result.append(
            TaskOut(
                id=task.id,
                title=task.title,
                description=task.description,
                created_by=task.created_by,
                created_by_name=created_by_name,
                assigned_agent=agents.get(task.assigned_agent_id or 0),
                parent_task_id=task.parent_task_id,
                depth=task.depth,
                kind=task.kind,
                priority=task.priority,  # type: ignore[arg-type]
                input=dict(task.input or {}),
                output=task.output,
                status=task.status,  # type: ignore[arg-type]
                child_count=child_counts.get(task.id, 0),
                pending_approval_id=waiting.get(task.id),
                created_at=as_utc(task.created_at),  # type: ignore[arg-type]
                started_at=as_utc(task.started_at),
                completed_at=as_utc(task.completed_at),
                error=task.error,
            )
        )
    return result


def _pending_approvals(db: Session, task_ids: set[int]) -> dict[int, int]:
    """task id → the oldest PENDING approval of that task or of a task below it. There are only
    ever a few open requests, so each one is walked up its (at most 3 levels of) parents."""
    found: dict[int, int] = {}
    if not task_ids:
        return found
    for approval_id, task_id in db.execute(
        select(Approval.id, Approval.task_id).where(Approval.status == "PENDING").order_by(Approval.id.desc())
    ).all():
        current: int | None = task_id
        while current is not None:
            if current in task_ids:
                found[current] = approval_id
            current = db.execute(select(Task.parent_task_id).where(Task.id == current)).scalar_one_or_none()
    return found


def descendants(db: Session, task_id: int) -> list[Task]:
    """Every task below `task_id`, level by level (delegation is at most a few levels deep)."""
    found: list[Task] = []
    level = [task_id]
    while level:
        children = db.execute(select(Task).where(Task.parent_task_id.in_(level)).order_by(Task.id)).scalars().all()
        found.extend(children)
        level = [child.id for child in children]
    return found


def _detail(db: Session, task: Task) -> TaskDetail:
    below = descendants(db, task.id)
    outs = _tasks_out(db, [task, *below])
    messages = db.execute(
        select(AgentMessage).where(AgentMessage.task_id.in_([task.id, *[item.id for item in below]])).order_by(AgentMessage.id)
    ).scalars().all()
    agents = agent_refs(db, {message.sender_agent_id for message in messages} | {message.receiver_agent_id for message in messages})
    return TaskDetail(
        **outs[0].model_dump(),
        children=[out for out in outs[1:] if out.parent_task_id == task.id],
        messages=[
            MessageOut(
                id=message.id,
                sender=agents.get(message.sender_agent_id),
                receiver=agents.get(message.receiver_agent_id),
                task_id=message.task_id,
                type=message.type,  # type: ignore[arg-type]
                payload=dict(message.payload or {}),
                created_at=as_utc(message.created_at),  # type: ignore[arg-type]
            )
            for message in messages
        ],
    )


def _get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreate, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> TaskOut:
    """Queue a request for the Central Manager. The background worker picks it up."""
    task = Task(
        title=body.title,
        description=body.description,
        created_by=auth.user.username,
        priority=body.priority,
        input={"request": f"{body.title}\n{body.description}".strip()},
        status=QUEUED,
    )
    db.add(task)
    db.commit()
    return _tasks_out(db, [task])[0]


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status_filter: Status | None = Query(default=None, alias="status"),
    agent_id: int | None = Query(default=None),
    top_level: bool = Query(default=False),
    system: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_session),
) -> list[TaskOut]:
    """Newest first. `top_level=true` leaves out delegated (child) tasks. The scheduler's health
    checks (one every 10 minutes) are left out unless `system=true`."""
    query = select(Task).order_by(Task.id.desc()).limit(limit)
    if not system:
        query = query.where(Task.kind != "health_check")
    if status_filter is not None:
        query = query.where(Task.status == status_filter)
    if agent_id is not None:
        query = query.where(Task.assigned_agent_id == agent_id)
    if top_level:
        query = query.where(Task.parent_task_id.is_(None))
    return _tasks_out(db, list(db.execute(query).scalars()))


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: int, db: Session = Depends(get_session)) -> TaskDetail:
    return _detail(db, _get_task(db, task_id))


@router.post("/{task_id}/cancel", response_model=TaskDetail)
def cancel_task(task_id: int, db: Session = Depends(get_session)) -> TaskDetail:
    """Cancel a task and every unfinished task below it. Finished tasks are left as they are."""
    task = _get_task(db, task_id)
    if task.status in TERMINAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"This task is already {task.status} and cannot be cancelled."
        )
    agent_ids: set[int | None] = set()
    for item in [task, *descendants(db, task.id)]:
        # A task the worker finished in this very moment keeps its result (move_task returns False).
        if item.status in ACTIVE and task_runner.move_task(db, item, CANCELLED):
            agent_ids.add(item.assigned_agent_id)
            db.commit()
    db.refresh(task)
    if task.status != CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"The task finished ({task.status}) before it could be cancelled."
        )
    for agent_id in agent_ids:
        task_runner.settle_agent(db, agent_id)
    db.commit()
    return _detail(db, task)

"""Approval Center API: list the requests of agents to use SENSITIVE tools, approve, reject.

Only a logged-in Chairman can decide (every /api route needs a session). A request can be
decided exactly once; a second decision answers 409.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import approvals, audit, task_runner
from app.api.tasks import AgentRef, agent_refs, descendants
from app.db import as_utc, get_session
from app.models import Agent, Approval, Task
from app.security import AuthContext, current_auth
from app.task_status import ACTIVE, CANCELLED, FAILED, RUNNING, InvalidTransition
from app.tools import get_tool

router = APIRouter(prefix="/approvals", tags=["approvals"])

ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "CANCELLED"]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ApprovalOut(BaseModel):
    id: int
    status: ApprovalStatus
    # docs/SPEC.md §8F — what the Chairman must see before deciding:
    agent: AgentRef | None  # requesting agent
    action: str  # requested action
    reason: str
    tool_key: str
    tool_name: str
    expected_changes: str
    risk_info: str
    risk: str  # the tool's risk level (always SENSITIVE today)
    args: dict[str, Any]
    task_id: int
    task_title: str
    task_status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None  # "chairman:<username>", or "system" when the task ended first
    decision_note: str
    executed_at: datetime | None
    result: str | None  # what happened after an approval


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Note = ""


class PendingCount(BaseModel):
    pending: int


def _out(db: Session, rows: list[Approval]) -> list[ApprovalOut]:
    agents = agent_refs(db, {row.agent_id for row in rows})
    tasks = {
        task.id: task for task in db.execute(select(Task).where(Task.id.in_({row.task_id for row in rows}))).scalars()
    } if rows else {}
    result = []
    for row in rows:
        agent, task, tool = agents.get(row.agent_id), tasks.get(row.task_id), get_tool(row.tool_key)
        result.append(
            ApprovalOut(
                id=row.id,
                status=row.status,  # type: ignore[arg-type]
                agent=agent,
                action=row.action,
                reason=row.reason,
                tool_key=row.tool_key,
                tool_name=tool.name if tool is not None else row.tool_key,
                expected_changes=row.expected_changes,
                risk_info=row.risk_info,
                risk=tool.risk.value if tool is not None else "SENSITIVE",
                args=dict(row.args or {}),
                task_id=row.task_id,
                task_title=task.title if task is not None else "",
                task_status=task.status if task is not None else "",
                created_at=as_utc(row.created_at),  # type: ignore[arg-type]
                decided_at=as_utc(row.decided_at),
                decided_by=row.decided_by,
                decision_note=row.decision_note,
                executed_at=as_utc(row.executed_at),
                result=row.result,
            )
        )
    return result


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _claim(db: Session, approval_id: int, approve: bool, auth: AuthContext, note: str) -> tuple[Approval, Task]:
    """Take the decision (once) and load the waiting task. 404 / 409 otherwise."""
    if db.get(Approval, approval_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    try:
        approval = approvals.claim_decision(db, approval_id, approve, auth.user.username, note)
    except approvals.AlreadyDecided as exc:
        raise _conflict(f"{exc} It cannot be decided again.") from None
    task = db.get(Task, approval.task_id)
    assert task is not None  # the foreign key cascades: no approval without its task
    return approval, task


def _not_waiting() -> HTTPException:
    return _conflict("The task is no longer waiting for this approval. Nothing was changed.")


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_session),
) -> list[ApprovalOut]:
    """Newest first."""
    query = select(Approval).order_by(Approval.id.desc()).limit(limit)
    if status_filter is not None:
        query = query.where(Approval.status == status_filter)
    return _out(db, list(db.execute(query).scalars()))


@router.get("/pending-count", response_model=PendingCount)
def pending_count(db: Session = Depends(get_session)) -> PendingCount:
    """How many requests wait for the Chairman (the badge in the navigation)."""
    count = db.execute(select(func.count()).select_from(Approval).where(Approval.status == approvals.PENDING)).scalar_one()
    return PendingCount(pending=count)


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: int, db: Session = Depends(get_session)) -> ApprovalOut:
    row = db.get(Approval, approval_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return _out(db, [row])[0]


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
def approve(
    approval_id: int,
    body: Decision | None = Body(default=None),
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_session),
) -> ApprovalOut:
    """Approve: the task continues. The background worker carries out the approved call."""
    note = body.note if body is not None else ""
    approval, task = _claim(db, approval_id, True, auth, note)
    try:
        moved = task_runner.move_task(db, task, RUNNING)
    except InvalidTransition:
        db.rollback()
        moved = False
    if not moved:  # (move_task rolled the decision back)
        raise _not_waiting()
    audit.record(
        db,
        "approval.approved",
        actor=audit.chairman(auth.user.username),
        agent=db.get(Agent, approval.agent_id),
        task_id=task.id,
        tool_key=approval.tool_key,
        decision="approved",
        summary=f"Approved request #{approval.id}: {approval.action}",
        details={"approval_id": approval.id, **({"note": note} if note else {})},
    )
    db.commit()
    return _out(db, [approval])[0]


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
def reject(
    approval_id: int,
    body: Decision | None = Body(default=None),
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_session),
) -> ApprovalOut:
    """Reject: nothing is done and the task fails with "rejected by Chairman"."""
    note = body.note if body is not None else ""
    approval, task = _claim(db, approval_id, False, auth, note)
    tool = get_tool(approval.tool_key)
    error = f"'{tool.name if tool is not None else approval.tool_key}' was {approvals.REJECTED_BY_CHAIRMAN}."
    if note:
        error += f" Note: {note}"
    try:
        moved = task_runner.move_task(db, task, FAILED, error=error)
    except InvalidTransition:
        db.rollback()
        moved = False
    if not moved:
        raise _not_waiting()
    task_runner.report_to_parent(db, task)
    agent_ids = {task.assigned_agent_id}
    for below in descendants(db, task.id):  # work it had handed on is stopped with it
        if below.status in ACTIVE and task_runner.move_task(db, below, CANCELLED):
            agent_ids.add(below.assigned_agent_id)
    for agent_id in agent_ids:
        task_runner.settle_agent(db, agent_id)
    audit.record(
        db,
        "approval.rejected",
        actor=audit.chairman(auth.user.username),
        agent=db.get(Agent, approval.agent_id),
        task_id=task.id,
        tool_key=approval.tool_key,
        decision="rejected",
        summary=f"Rejected request #{approval.id}: {approval.action}",
        details={"approval_id": approval.id, **({"note": note} if note else {})},
    )
    db.commit()
    return _out(db, [approval])[0]

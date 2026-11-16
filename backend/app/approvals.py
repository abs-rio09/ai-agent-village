"""Approvals: the Chairman decides about every SENSITIVE tool call (docs/SPEC.md §8F).

Flow:
  1. An agent asks for a SENSITIVE tool. `call_tool` checks the agent's permissions and then
     calls `request` here: an approval row (PENDING) is written, nothing is executed.
  2. The task runner moves the task to WAITING_APPROVAL.
  3. `decide(approve=True)`  → APPROVED, the task goes back to RUNNING and the runner carries
     out the approved call (and whatever the reply asked for after it).
     `decide(approve=False)` → REJECTED, the task is FAILED with "rejected by Chairman".
  A task that ends before the decision (cancelled) takes its request with it: CANCELLED.

Every step is written to the audit log. A decision can be made exactly once.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit
from app.db import utcnow
from app.models import Agent, Approval, Task
from app.tools.base import ApprovalText, Tool

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"
STATUSES = (PENDING, APPROVED, REJECTED, CANCELLED)

REJECTED_BY_CHAIRMAN = "rejected by Chairman"


class AlreadyDecided(Exception):
    """The approval is not PENDING any more: it was decided before, or its task ended."""

    def __init__(self, approval: Approval | None) -> None:
        self.approval = approval
        status = approval.status if approval is not None else "gone"
        super().__init__(f"This approval request is already {status}.")


def request(
    db: Session, agent: Agent, task: Task, tool: Tool, args: dict[str, Any], reason: str, text: ApprovalText
) -> Approval:
    """Write the approval request of `agent` for `tool`. The caller commits."""
    approval = Approval(
        agent_id=agent.id,
        task_id=task.id,
        tool_key=tool.key,
        args=args,
        action=text.action,
        reason=reason.strip() or "The agent gave no reason.",
        expected_changes=text.expected_changes,
        risk_info=text.risk_info,
        status=PENDING,
        continuation=[],
    )
    db.add(approval)
    db.flush()
    audit.record(
        db,
        "approval.created",
        actor=audit.agent_actor(agent),
        agent=agent,
        task_id=task.id,
        tool_key=tool.key,
        decision="pending",
        summary=f"'{agent.display_name}' asks for approval: {text.action}",
        details={"approval_id": approval.id, "reason": approval.reason},
    )
    return approval


def cancel_for_task(db: Session, task_id: int, why: str) -> int:
    """The task ended without a decision: its open requests are withdrawn. The caller commits."""
    open_requests = db.execute(select(Approval).where(Approval.task_id == task_id, Approval.status == PENDING)).scalars().all()
    for approval in open_requests:
        approval.status = CANCELLED
        approval.decided_at = utcnow()
        approval.decided_by = audit.SYSTEM
        approval.decision_note = why
        audit.record(
            db,
            "approval.cancelled",
            agent=db.get(Agent, approval.agent_id),
            task_id=task_id,
            tool_key=approval.tool_key,
            decision="cancelled",
            summary=f"Approval request #{approval.id} was withdrawn: {why}",
            details={"approval_id": approval.id},
        )
    return len(open_requests)


def claim_decision(db: Session, approval_id: int, approve: bool, username: str, note: str) -> Approval:
    """Mark a PENDING approval as decided — atomically, so two decisions cannot both win.
    Raises AlreadyDecided otherwise. Does not touch the task; the caller does and commits."""
    result = db.execute(
        update(Approval)
        .where(Approval.id == approval_id, Approval.status == PENDING)
        .values(
            status=APPROVED if approve else REJECTED,
            decided_at=utcnow(),
            decided_by=audit.chairman(username),
            decision_note=note,
        )
        .execution_options(synchronize_session=False)
    )
    approval = db.get(Approval, approval_id)
    if result.rowcount != 1 or approval is None:
        db.rollback()
        raise AlreadyDecided(db.get(Approval, approval_id))
    db.refresh(approval)
    return approval

"""Enforcement: the ONE permission check and the ONE way a tool is called.

`check_tool_use(agent, tool)` decides from the agent's own database row only — its lifecycle,
its assigned tools and its permissions. Nothing in a task, a message or a tool argument is
looked at, so an agent cannot be talked into a tool by another agent (docs/SPEC.md §8C).

`call_tool` is the only caller of `Tool.run`. It checks, audits and runs, in that order.
A SENSITIVE tool is never run by the first call: that call only writes an approval request.
It runs when `call_tool` is called again with that request, approved by the Chairman.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app import approvals, audit
from app.agent_catalog import PERMISSIONS
from app.db import utcnow
from app.models import Agent, Approval, Task
from app.tools.base import Tool, ToolContext, ToolDenied, ToolError, get_tool

_PERMISSION_LABELS = {item.key: item.label for item in PERMISSIONS}

OutcomeStatus = Literal["ok", "denied", "unavailable", "error", "pending_approval"]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class ToolOutcome:
    status: OutcomeStatus
    tool_key: str
    tool_name: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    approval_id: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def check_tool_use(agent: Agent, tool: Tool) -> Decision:
    """May `agent` use `tool` right now? Denied when the agent is not ACTIVE, the tool is not
    assigned to it, or it lacks the permission the tool needs."""
    if agent.lifecycle != "active":
        return Decision(False, f"'{agent.display_name}' is {agent.lifecycle}. Only an active agent may use tools.")
    if tool.key not in (agent.allowed_tools or []):
        return Decision(False, f"The tool '{tool.name}' is not assigned to '{agent.display_name}'.")
    needed = tool.required_permission
    if needed is not None and needed not in (agent.permissions or []):
        label = _PERMISSION_LABELS.get(needed, needed)
        return Decision(False, f"'{agent.display_name}' does not have the permission '{label}' that '{tool.name}' needs.")
    return Decision(True)


def call_tool(
    db: Session,
    agent: Agent,
    task: Task | None,
    key: str,
    args: dict[str, Any] | None = None,
    *,
    reason: str = "",
    approval: Approval | None = None,
) -> ToolOutcome:
    """Check, audit and run one tool call for `agent`. Never raises for a refused or failed call:
    the outcome says what happened. The caller commits.

    `approval` is the Chairman's approved request for exactly this call; without it a SENSITIVE
    tool is not run — an approval request is written and the outcome is "pending_approval"."""
    args = dict(args or {})
    task_id = task.id if task is not None else None
    actor = audit.agent_actor(agent)
    tool = get_tool(key)
    if tool is None:
        summary = f"There is no tool called '{key}'."
        audit.record(db, "tool.denied", actor=actor, agent=agent, task_id=task_id, tool_key=key[:64], decision="denied", summary=summary)
        return ToolOutcome("denied", key, key, summary)

    def outcome(status: OutcomeStatus, action: str, decision: str, summary: str, data: dict[str, Any] | None = None) -> ToolOutcome:
        audit.record(
            db,
            action,
            actor=actor,
            agent=agent,
            task_id=task_id,
            tool_key=tool.key,
            decision=decision,
            summary=summary,
            details={"risk": tool.risk.value, "args": args, **({"reason": reason} if reason else {})},
        )
        return ToolOutcome(status, tool.key, tool.name, summary, data or {})

    verdict = check_tool_use(agent, tool)
    if not verdict.allowed:
        return outcome("denied", "tool.denied", "denied", verdict.reason)
    if not tool.available:
        planned = f" It is planned for {tool.planned_for}." if tool.planned_for else ""
        return outcome("unavailable", "tool.unavailable", "allowed", f"'{tool.name}' is not available yet.{planned}")
    context = ToolContext(db=db, agent=agent, task=task)
    if tool.needs_approval and approval is None:
        # SENSITIVE: nothing runs now. The arguments are checked and the request is written.
        if task is None:
            return outcome("error", "tool.error", "allowed", f"'{tool.name}' can only be requested while working on a task.")
        assert tool.describe is not None  # guaranteed by register()
        try:
            text = tool.describe(context, args)
        except ToolError as exc:
            return outcome("error", "tool.error", "allowed", f"'{tool.name}' failed: {exc}")
        row = approvals.request(db, agent, task, tool, args, reason, text)  # writes "approval.created"
        return ToolOutcome(
            "pending_approval",
            tool.key,
            tool.name,
            f"Waiting for the Chairman's approval (request #{row.id}): {text.action}",
            approval_id=row.id,
        )
    if tool.needs_approval:
        usable = (
            approval is not None
            and approval.status == approvals.APPROVED
            and approval.executed_at is None
            and approval.tool_key == tool.key
            and approval.agent_id == agent.id
            and task is not None
            and approval.task_id == task.id
        )
        if not usable:
            return outcome("denied", "tool.denied", "denied", f"'{tool.name}' has no valid approval of the Chairman for this call.")
    try:
        result = tool.run(context, args)
    except ToolDenied as exc:
        return outcome("denied", "tool.denied", "denied", str(exc))
    except ToolError as exc:
        return outcome("error", "tool.error", "allowed", f"'{tool.name}' failed: {exc}")
    if approval is not None:
        approval.executed_at = utcnow()  # an approval is used exactly once
        approval.result = result.summary
        return outcome("ok", "tool.allowed", "approved", result.summary, result.data)
    return outcome("ok", "tool.allowed", "allowed", result.summary, result.data)

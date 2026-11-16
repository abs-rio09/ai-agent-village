"""Enforcement: the ONE permission check and the ONE way a tool is called.

`check_tool_use(agent, tool)` decides from the agent's own database row only — its lifecycle,
its assigned tools and its permissions. Nothing in a task, a message or a tool argument is
looked at, so an agent cannot be talked into a tool by another agent (docs/SPEC.md §8C).

`call_tool` is the only caller of `Tool.run`. It checks, audits and runs, in that order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app import audit
from app.agent_catalog import PERMISSIONS
from app.models import Agent, Task
from app.tools.base import Tool, ToolContext, ToolError, get_tool

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
) -> ToolOutcome:
    """Check, audit and run one tool call for `agent`. Never raises for a refused or failed call:
    the outcome says what happened. The caller commits."""
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
    if tool.needs_approval:
        # SENSITIVE tools never run without the Chairman's approval, and approvals are built in
        # M4 Part B. Until then the call is refused — it is not executed and not faked.
        return outcome(
            "unavailable",
            "tool.unavailable",
            "allowed",
            f"'{tool.name}' needs the Chairman's approval, and approvals are not available yet. Nothing was done.",
        )
    try:
        result = tool.run(ToolContext(db=db, agent=agent, task=task), args)
    except ToolError as exc:
        return outcome("error", "tool.error", "allowed", f"'{tool.name}' failed: {exc}")
    return outcome("ok", "tool.allowed", "allowed", result.summary, result.data)

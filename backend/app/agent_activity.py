"""What an agent is doing right now — computed from its lifecycle and its open tasks, never
stored (docs/SPEC.md §6 "status indicator" and "current task indicator").

  offline   the agent is paused or disabled
  waiting   one of its tasks waits for the Chairman's approval (WAITING_APPROVAL)
  working   one of its tasks is RUNNING
  idle      active, and none of the above

"waiting" wins over "working": a task that needs the Chairman is what matters most to show.
The current task is the task that decided the answer (the oldest one of that kind).
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Task
from app.task_status import RUNNING, WAITING_APPROVAL

OFFLINE = "offline"
WAITING = "waiting"
WORKING = "working"
IDLE = "idle"
ACTIVITIES = (WORKING, IDLE, WAITING, OFFLINE)
_SYSTEM_KINDS = ("health_check",)


def derive(lifecycle: str, running_task_id: int | None, waiting_task_id: int | None) -> tuple[str, int | None]:
    """(activity, current task id) from an agent's lifecycle and its oldest RUNNING and
    WAITING_APPROVAL task. A pure function: the one place where the rule lives."""
    if lifecycle != "active":
        return OFFLINE, None
    if waiting_task_id is not None:
        return WAITING, waiting_task_id
    if running_task_id is not None:
        return WORKING, running_task_id
    return IDLE, None


def open_tasks(db: Session, agent_ids: Iterable[int]) -> dict[int, dict[str, int]]:
    """agent id → {status: oldest task id} for RUNNING and WAITING_APPROVAL. One query."""
    ids = list(agent_ids)
    found: dict[int, dict[str, int]] = {}
    if not ids:
        return found
    for agent_id, status, task_id in db.execute(
        select(Task.assigned_agent_id, Task.status, func.min(Task.id))
        .where(Task.assigned_agent_id.in_(ids), Task.status.in_((RUNNING, WAITING_APPROVAL)), Task.kind.not_in(_SYSTEM_KINDS))
        .group_by(Task.assigned_agent_id, Task.status)
    ).all():
        found.setdefault(agent_id, {})[status] = task_id
    return found


def activity_of(db: Session, lifecycles: dict[int, str]) -> dict[int, tuple[str, int | None]]:
    """agent id → (activity, current task id) for the given agents ({id: lifecycle})."""
    tasks = open_tasks(db, lifecycles)
    return {
        agent_id: derive(lifecycle, tasks.get(agent_id, {}).get(RUNNING), tasks.get(agent_id, {}).get(WAITING_APPROVAL))
        for agent_id, lifecycle in lifecycles.items()
    }

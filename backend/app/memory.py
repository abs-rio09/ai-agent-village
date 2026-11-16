"""Memory scopes (docs/SPEC.md §8D) and who may use them. Every rule is enforced here, on the
server; the tools (memory.read / memory.write) and the API both go through this module.

  scope     an agent may READ                         an agent may WRITE
  VILLAGE   with "Read village memory"                with "Write village memory"
  UPAZILA   its OWN Upazila, with "Read Upazila       its OWN Upazila, with "Write Upazila
            memory"                                   memory"
  AGENT     its OWN notes, always                     its OWN notes, with "Keep its own notes"
  task      the context of the task it is working on (temporary; deleted when the task ends)

An agent in Central Administration has no Upazila, so it has no Upazila memory.

Customer data: a memory is marked `contains_customer_data` when the writer says so OR when the
text looks like it (an e-mail address or a phone number). Such a memory can never be stored in,
or moved into, VILLAGE memory — the shared scope. The Chairman is bound by this rule too.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Agent, Memory, Office, Task, TaskContext, UnionUnit, Ward

VILLAGE = "VILLAGE"
UPAZILA = "UPAZILA"
AGENT = "AGENT"
SCOPES = (VILLAGE, UPAZILA, AGENT)
TASK = "TASK"  # not a memory scope: the temporary context of one task

TITLE_MAX = 120
CONTENT_MAX = 4000
CONTEXT_ITEMS_MAX = 20  # per task

READ_VILLAGE = "read_village_memory"
READ_UPAZILA = "read_upazila_memory"
WRITE_AGENT = "write_agent_memory"
WRITE_UPAZILA = "write_upazila_memory"
WRITE_VILLAGE = "write_village_memory"

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w.])")

CUSTOMER_DATA_IN_VILLAGE = (
    "Customer data cannot be stored in Village memory, because the whole village can read it. "
    "Keep it in the memory of one Upazila or one agent instead."
)


class MemoryDenied(Exception):
    """The agent has no right to read or write there."""


class MemoryRefused(Exception):
    """The content is not acceptable where it should go (for example customer data in VILLAGE)."""


def looks_like_customer_data(*texts: str) -> bool:
    """A cautious guess: an e-mail address, or a phone number (9 or more digits)."""
    for text in texts:
        if _EMAIL.search(text):
            return True
        for match in _PHONE.finditer(text):
            if sum(char.isdigit() for char in match.group()) >= 9:
                return True
    return False


def check_customer_data(scope: str, title: str, content: str, flagged: bool) -> bool:
    """The value to store in `contains_customer_data`. Raises MemoryRefused for VILLAGE scope."""
    contains = flagged or looks_like_customer_data(title, content)
    if contains and scope == VILLAGE:
        raise MemoryRefused(CUSTOMER_DATA_IN_VILLAGE)
    return contains


def upazila_of(db: Session, agent: Agent) -> int | None:
    """The Upazila an agent works in (through its Office), or None for Central Administration."""
    if agent.office_id is None:
        return None
    return db.execute(
        select(UnionUnit.upazila_id)
        .join(Ward, Ward.union_id == UnionUnit.id)
        .join(Office, Office.ward_id == Ward.id)
        .where(Office.id == agent.office_id)
    ).scalar_one_or_none()


def _has(agent: Agent, permission: str) -> bool:
    return permission in (agent.permissions or [])


def readable_scopes(db: Session, agent: Agent) -> list[str]:
    scopes = [AGENT]
    if _has(agent, READ_UPAZILA) and upazila_of(db, agent) is not None:
        scopes.append(UPAZILA)
    if _has(agent, READ_VILLAGE):
        scopes.append(VILLAGE)
    return scopes


def check_read(db: Session, agent: Agent, scope: str) -> None:
    if scope == AGENT:
        return
    if scope == VILLAGE:
        if not _has(agent, READ_VILLAGE):
            raise MemoryDenied(f"'{agent.display_name}' does not have the permission 'Read village memory'.")
        return
    if scope == UPAZILA:
        if not _has(agent, READ_UPAZILA):
            raise MemoryDenied(f"'{agent.display_name}' does not have the permission 'Read Upazila memory'.")
        if upazila_of(db, agent) is None:
            raise MemoryDenied(f"'{agent.display_name}' does not work in an Upazila, so it has no Upazila memory.")
        return
    raise MemoryDenied(f"Unknown memory scope '{scope}'.")


def check_write(db: Session, agent: Agent, scope: str) -> None:
    needed = {AGENT: (WRITE_AGENT, "Keep its own notes"), UPAZILA: (WRITE_UPAZILA, "Write Upazila memory"), VILLAGE: (WRITE_VILLAGE, "Write village memory")}
    if scope not in needed:
        raise MemoryDenied(f"Unknown memory scope '{scope}'.")
    permission, label = needed[scope]
    if not _has(agent, permission):
        raise MemoryDenied(f"'{agent.display_name}' does not have the permission '{label}'.")
    if scope == UPAZILA and upazila_of(db, agent) is None:
        raise MemoryDenied(f"'{agent.display_name}' does not work in an Upazila, so it has no Upazila memory.")


def read_for_agent(db: Session, agent: Agent, scope: str | None = None, query: str = "", limit: int = 20) -> list[Memory]:
    """The memories `agent` may see — of one scope (MemoryDenied if it may not), or of every
    scope it is allowed to read. Newest first. Another agent's notes and another Upazila's
    memory are never returned, whatever is asked."""
    if scope is not None:
        check_read(db, agent, scope)
        scopes: Sequence[str] = [scope]
    else:
        scopes = readable_scopes(db, agent)
    conditions = []
    if AGENT in scopes:
        conditions.append((Memory.scope == AGENT) & (Memory.agent_id == agent.id))
    if UPAZILA in scopes:
        conditions.append((Memory.scope == UPAZILA) & (Memory.upazila_id == upazila_of(db, agent)))
    if VILLAGE in scopes:
        conditions.append(Memory.scope == VILLAGE)
    statement = select(Memory).where(or_(*conditions)).order_by(Memory.id.desc()).limit(limit)
    words = query.strip()
    if words:
        like = f"%{words}%"
        statement = statement.where(or_(Memory.title.ilike(like), Memory.content.ilike(like)))
    return list(db.execute(statement).scalars())


def write_for_agent(db: Session, agent: Agent, scope: str, title: str, content: str, flagged: bool = False) -> Memory:
    """Save a memory for `agent` in `scope`. MemoryDenied / MemoryRefused when it may not. The
    caller commits."""
    check_write(db, agent, scope)
    contains = check_customer_data(scope, title, content, flagged)
    actor = f"agent:{agent.id}"
    row = Memory(
        scope=scope,
        upazila_id=upazila_of(db, agent) if scope == UPAZILA else None,
        agent_id=agent.id if scope == AGENT else None,
        title=title,
        content=content,
        contains_customer_data=contains,
        created_by=actor,
        updated_by=actor,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------- task context (temporary)


def context_of(db: Session, task: Task) -> list[TaskContext]:
    return list(db.execute(select(TaskContext).where(TaskContext.task_id == task.id).order_by(TaskContext.id)).scalars())


def set_context(db: Session, agent: Agent, task: Task, key: str, value: str) -> TaskContext:
    """Add or replace one note in the context of the task `agent` is working on."""
    if task.assigned_agent_id != agent.id:
        raise MemoryDenied("An agent can only use the context of its own task.")
    row = db.execute(select(TaskContext).where(TaskContext.task_id == task.id, TaskContext.key == key)).scalar_one_or_none()
    if row is None:
        if len(context_of(db, task)) >= CONTEXT_ITEMS_MAX:
            raise MemoryRefused(f"A task can hold at most {CONTEXT_ITEMS_MAX} context notes.")
        row = TaskContext(task_id=task.id, agent_id=agent.id, key=key, value=value)
        db.add(row)
    else:
        row.value = value
        row.updated_at = utcnow()
    db.flush()
    return row


def clear_context(db: Session, task_id: int) -> None:
    """The task is finished: its temporary context is deleted."""
    db.execute(delete(TaskContext).where(TaskContext.task_id == task_id))

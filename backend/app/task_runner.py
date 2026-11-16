"""The task queue: one in-process background worker that polls SQLite and runs ONE step at a time.

A step is one of:
  1. finish a RUNNING task whose child tasks are all done (collect the outputs → report),
  2. start the next waiting task: the Central Manager routes a request of the Chairman,
     or an agent answers a delegated task through its provider.

An agent's reply may ask for tools. Each request goes through `app.tools.call_tool`, which
checks the agent's tools and permissions and writes the audit log; a refused or failed tool
call fails the task with the reason.

Every status change goes through `move_task`, which checks app.task_status and only changes a
task that still has the status the caller saw — so a cancel from the API and the worker cannot
overwrite each other. Tasks persist in the database: on start, a task a crash left RUNNING is
queued again (`recover_interrupted`).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, exists, select, update
from sqlalchemy.orm import Session, aliased, sessionmaker

from app import audit
from app import central_manager as manager_rules
from app.api.agents import agent_rows_query, location_of
from app.db import get_session_factory, utcnow
from app.models import Agent, AgentMessage, Task
from app.providers import AgentContext, AgentReply, TaskContext, ToolRequest, get_provider
from app.task_status import ACTIVE, ASSIGNED, FAILED, QUEUED, RUNNING, SUCCEEDED, TERMINAL, ensure_transition
from app.tools import call_tool

log = logging.getLogger("village.tasks")

POLL_SECONDS = 0.5
INTERRUPTED_NOTE = "Interrupted by a restart of the village; queued again."
_PRIORITY_RANK = case({"high": 0, "normal": 1, "low": 2}, value=Task.priority, else_=1)


# ---------------------------------------------------------------- status changes


def move_task(db: Session, task: Task, status: str, **values: Any) -> bool:
    """Change a task's status if the change is valid (InvalidTransition otherwise) AND the task
    still has the status this session last saw. Returns False — changing nothing, with `task`
    refreshed — when someone else changed it first. Sets started_at / completed_at. The caller
    commits; call this before other writes of the same step, because a lost race rolls back."""
    ensure_transition(task.status, status)
    now = utcnow()
    values = {"status": status, "updated_at": now, **values}
    if status == RUNNING:
        values.setdefault("started_at", now)
    if status in TERMINAL:
        values.setdefault("completed_at", now)
    result = db.execute(
        update(Task)
        .where(Task.id == task.id, Task.status == task.status)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        db.refresh(task)
        return False
    db.refresh(task)
    return True


def settle_agent(db: Session, agent_id: int | None) -> None:
    """Runtime state after a step: an active agent that still has RUNNING tasks is waiting for
    their child tasks, otherwise it is idle. Paused and disabled agents stay offline."""
    if agent_id is None:
        return
    busy = db.execute(select(Task.id).where(Task.assigned_agent_id == agent_id, Task.status == RUNNING).limit(1)).first()
    db.execute(
        update(Agent)
        .where(Agent.id == agent_id, Agent.lifecycle == "active")
        .values(runtime_state="waiting" if busy else "idle")
        .execution_options(synchronize_session=False)
    )


def _set_runtime(db: Session, agent_id: int, state: str) -> None:
    db.execute(
        update(Agent)
        .where(Agent.id == agent_id, Agent.lifecycle == "active")
        .values(runtime_state=state)
        .execution_options(synchronize_session=False)
    )


def _message(db: Session, task: Task, sender_id: int, receiver_id: int, payload: dict[str, Any]) -> None:
    db.add(AgentMessage(sender_agent_id=sender_id, receiver_agent_id=receiver_id, task_id=task.id, type="result", payload=payload))


def _report_to_parent(db: Session, task: Task) -> None:
    """Log the result of a delegated task as a message from its agent to the delegating agent."""
    if task.parent_task_id is None or task.assigned_agent_id is None:
        return
    parent = db.get(Task, task.parent_task_id)
    if parent is None or parent.assigned_agent_id is None:
        return
    payload: dict[str, Any] = {"parent_task_id": parent.id, "status": task.status}
    if task.status == SUCCEEDED:
        payload["output"] = task.output
    else:
        payload["error"] = task.error
    _message(db, task, task.assigned_agent_id, parent.assigned_agent_id, payload)


# ---------------------------------------------------------------- crash recovery


def recover_interrupted(db: Session) -> int:
    """After a restart: tasks left RUNNING go back to QUEUED with a note in `error`, and no agent
    is still shown as working. Returns the number of tasks that were queued again."""
    interrupted = db.execute(select(Task).where(Task.status == RUNNING).order_by(Task.id)).scalars().all()
    recovered = 0
    for task in interrupted:
        if move_task(db, task, QUEUED, error=INTERRUPTED_NOTE):
            recovered += 1
    db.execute(
        update(Agent)
        .where(Agent.runtime_state.in_(("working", "waiting")))
        .values(runtime_state=case((Agent.lifecycle == "active", "idle"), else_="offline"))
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return recovered


# ---------------------------------------------------------------- the steps


def _fail(db: Session, task: Task, reason: str, **values: Any) -> None:
    if move_task(db, task, FAILED, error=reason, **values):
        _report_to_parent(db, task)
    settle_agent(db, task.assigned_agent_id)
    db.commit()


def _finish_parent(db: Session, task: Task) -> None:
    """All child tasks are done: collect their outputs into this task's report."""
    children = db.execute(select(Task).where(Task.parent_task_id == task.id).order_by(Task.id)).scalars().all()
    if any(child.status == SUCCEEDED for child in children):
        ids = [child.assigned_agent_id for child in children if child.assigned_agent_id is not None]
        names = dict(db.execute(select(Agent.id, Agent.display_name).where(Agent.id.in_(ids))).all())
        owner = db.get(Agent, task.assigned_agent_id) if task.assigned_agent_id is not None else None
        if owner is not None and not owner.is_central_manager:
            # an ordinary agent that handed work on: its own reply, then what came back
            output = "\n\n".join(part for part in (task.output, manager_rules.child_results(children, names)) if part)
        else:
            output = manager_rules.final_report(task, children, names)
        moved = move_task(db, task, SUCCEEDED, output=output, error=None)
    else:
        reasons = "; ".join(f"task #{child.id} {child.status}" + (f" ({child.error})" if child.error else "") for child in children)
        moved = move_task(db, task, FAILED, error=f"None of the delegated tasks succeeded: {reasons}")
    if moved:
        _report_to_parent(db, task)
    settle_agent(db, task.assigned_agent_id)
    db.commit()


def _route(db: Session, task: Task) -> None:
    """The Central Manager's step for a request of the Chairman. It only routes and delegates."""
    manager = manager_rules.central_manager(db)
    if manager is None:
        if move_task(db, task, FAILED, error="The village has no Central Manager. Restart the village to restore it."):
            db.commit()
        return
    if task.status == QUEUED and not move_task(db, task, ASSIGNED, assigned_agent_id=manager.id):
        return
    if not move_task(db, task, RUNNING):
        return
    _set_runtime(db, manager.id, "working")
    db.commit()

    has_children = db.execute(select(Task.id).where(Task.parent_task_id == task.id).limit(1)).first()
    if has_children:  # routed before a restart: do not delegate twice, just wait for the children
        settle_agent(db, manager.id)
        db.commit()
        return
    routing = manager_rules.route(db, task)
    if routing.row is None:
        _fail(db, task, routing.reason or "The request could not be routed.")
        return
    # Delegation is a tool call like any other: checked against the manager's own tools and
    # permissions, and written to the audit log.
    outcome = call_tool(
        db,
        manager,
        task,
        "task.create_child",
        {"agent_id": routing.row[0].id, "routing": routing.details},
        reason="Routing a request of the Chairman.",
    )
    if not outcome.ok:
        _fail(db, task, f"The Central Manager could not delegate this request. {outcome.summary}")
        return
    settle_agent(db, manager.id)  # waiting for the child task
    db.commit()


def _as_reply(reply: str | AgentReply) -> AgentReply:
    return reply if isinstance(reply, AgentReply) else AgentReply(text=str(reply))


def _tool_line(name: str, summary: str) -> str:
    return f"[Tool] {name}: {summary}"


def _run_tool_calls(db: Session, task: Task, agent: Agent, output: str, calls: Sequence[ToolRequest]) -> None:
    """Run the tools an agent asked for, in order, then finish the task (or leave it RUNNING
    while child tasks it created are still open). Everything here is ONE transaction: if the
    task was cancelled meanwhile, `move_task` loses the race and nothing of it is kept."""
    for call in calls:
        outcome = call_tool(db, agent, task, call.tool, call.args, reason=call.reason)
        if not outcome.ok:
            prefix = "Tool call refused. " if outcome.status == "denied" else ""
            _fail(db, task, f"{prefix}{outcome.summary}", output=output)
            return
        output = f"{output}\n\n{_tool_line(outcome.tool_name, outcome.summary)}"

    open_children = db.execute(
        select(Task.id).where(Task.parent_task_id == task.id, Task.status.in_(ACTIVE)).limit(1)
    ).first()
    if open_children:  # it created child tasks: keep RUNNING, _finish_parent completes it later
        db.execute(
            update(Task)
            .where(Task.id == task.id, Task.status == RUNNING)
            .values(output=output, updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        settle_agent(db, agent.id)
        db.commit()
        return
    # A cancel may have arrived while the provider was working: then the task stays CANCELLED.
    if move_task(db, task, SUCCEEDED, output=output, error=None):
        _report_to_parent(db, task)
    settle_agent(db, agent.id)
    db.commit()


def _work(db: Session, task: Task) -> None:
    """An agent answers a delegated task through its provider."""
    row = db.execute(agent_rows_query().where(Agent.id == task.assigned_agent_id)).first()
    if row is None:
        _fail(db, task, "The task has no agent to run it.")
        return
    agent, template, office, ward, union, upazila = row
    if agent.is_central_manager:  # it routes and reports; it never answers a task itself
        _fail(db, task, "The Central Manager does not do delegated work itself.")
        return
    if agent.lifecycle != "active":  # paused or disabled after the task was handed over
        reason = f"'{agent.display_name}' is {agent.lifecycle}, so it did not receive this task."
        if move_task(db, task, FAILED, error=reason):
            audit.record(
                db, "agent.work_denied", agent=agent, task_id=task.id, decision="denied", summary=reason
            )
            _report_to_parent(db, task)
        settle_agent(db, task.assigned_agent_id)
        db.commit()
        return
    if task.status == QUEUED and not move_task(db, task, ASSIGNED):
        return
    if not move_task(db, task, RUNNING):
        return
    _set_runtime(db, agent.id, "working")
    db.commit()

    has_children = db.execute(select(Task.id).where(Task.parent_task_id == task.id).limit(1)).first()
    if has_children:  # worked before a restart and handed work on: do not start again, wait
        settle_agent(db, agent.id)
        db.commit()
        return

    provider = get_provider(agent.provider)
    context = AgentContext(
        display_name=agent.display_name,
        role=agent.role,
        template_key=template.key if template is not None else None,
        system_instructions=agent.system_instructions,
        location=location_of(office, ward, union, upazila).path if office is not None else "",
    )
    try:
        reply = _as_reply(provider.reply(context, TaskContext(title=task.title, description=task.description)))
    except Exception as exc:  # noqa: BLE001  (a provider failure must not stop the queue)
        log.warning("task %s: the %s provider failed (%s)", task.id, provider.name, type(exc).__name__)
        _fail(db, task, f"The {provider.name} provider failed ({type(exc).__name__}).")
        return
    _run_tool_calls(db, task, agent, reply.text, reply.tool_calls)


def _next_step(db: Session) -> tuple[str, Task] | None:
    child = aliased(Task)
    finished_parent = db.execute(
        select(Task)
        .where(
            Task.status == RUNNING,
            exists().where(child.parent_task_id == Task.id),
            ~exists().where(child.parent_task_id == Task.id, child.status.in_(ACTIVE)),
        )
        .order_by(Task.id)
        .limit(1)
    ).scalar_one_or_none()
    if finished_parent is not None:
        return "finish", finished_parent
    waiting = db.execute(
        select(Task).where(Task.status.in_((QUEUED, ASSIGNED))).order_by(_PRIORITY_RANK, Task.id).limit(1)
    ).scalar_one_or_none()
    if waiting is None:
        return None
    if waiting.parent_task_id is None:
        return "route", waiting
    return "work", waiting


def run_once(session_factory: sessionmaker[Session] | None = None) -> bool:
    """Run one step of the queue. Returns False when there was nothing to do."""
    factory = session_factory or get_session_factory()
    with factory() as db:
        step = _next_step(db)
        if step is None:
            return False
        kind, task = step
        task_id = task.id
        try:
            {"finish": _finish_parent, "route": _route, "work": _work}[kind](db, task)
        except Exception as exc:  # noqa: BLE001  (one broken task must not block the queue forever)
            db.rollback()
            log.exception("task %s: step '%s' failed", task_id, kind)
            broken = db.get(Task, task_id)
            if broken is not None and broken.status in ACTIVE:
                db.refresh(broken)
                _fail(db, broken, f"Internal error while running the task ({type(exc).__name__}).")
        return True


def drain(limit: int = 1000, session_factory: sessionmaker[Session] | None = None) -> int:
    """Run steps until the queue is empty (tests and scripts). Returns the number of steps."""
    steps = 0
    while steps < limit and run_once(session_factory):
        steps += 1
    return steps


# ---------------------------------------------------------------- the background worker


class TaskWorker:
    """One daemon thread, started and stopped with the FastAPI lifespan."""

    def __init__(self, poll_seconds: float = POLL_SECONDS) -> None:
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        with get_session_factory()() as db:
            recovered = recover_interrupted(db)
        if recovered:
            log.info("queued %s interrupted task(s) again", recovered)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="village-task-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = run_once()
            except Exception:  # noqa: BLE001  (for example: the database is locked for a moment)
                log.exception("task worker: step failed")
                worked = False
            if not worked:
                self._stop.wait(self.poll_seconds)

"""M3 Part B: tasks, status rules, Central Manager routing, delegation, cancel, crash recovery."""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient

from app import central_manager as cm
from app import task_runner
from app.config import get_settings
from app.db import get_session_factory
from app.dbcheck import alembic_config, check
from app.models import Agent, AgentMessage, Task
from app.providers import AgentContext, Provider, TaskContext, register_provider, unregister_provider
from app.routing_keywords import ROUTING_KEYWORDS
from app.task_runner import INTERRUPTED_NOTE, drain, move_task, recover_interrupted, run_once
from app.task_status import (
    ASSIGNED,
    CANCELLED,
    FAILED,
    QUEUED,
    RUNNING,
    STATUSES,
    SUCCEEDED,
    TERMINAL,
    WAITING_APPROVAL,
    InvalidTransition,
    can_transition,
    ensure_transition,
)
from tests.conftest import BASE_URL
from tests.test_m2_org import api, delete, make_upazila, ok  # noqa: F401  (api is a fixture)
from tests.test_m3_agents import central_manager, make_agent, rows, study_office, template
from tests.test_part_b_auth import PASSWORD, api_routes, do_setup

EXAM_REQUEST = "help me prepare for my exam"


def send(api: TestClient, title: str = EXAM_REQUEST, **extra: Any) -> dict[str, Any]:  # noqa: F811
    return ok(api.post("/api/tasks", json={"title": title, **extra}), 201)


def detail(api: TestClient, task_id: int) -> dict[str, Any]:  # noqa: F811
    return ok(api.get(f"/api/tasks/{task_id}"))


def run(api: TestClient, title: str = EXAM_REQUEST, **extra: Any) -> dict[str, Any]:  # noqa: F811
    """Send a request, run the queue until it is empty, return the task's detail."""
    task = send(api, title, **extra)
    drain()
    return detail(api, task["id"])


def agent_in(api: TestClient, upazila: dict[str, Any], key: str, name: str, ward_name: str | None = None) -> dict[str, Any]:  # noqa: F811
    """A new Union + Ward in `upazila` with one agent in the ward's office."""
    union = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": f"{name} Union"}), 201)
    ward = ok(api.post(f"/api/unions/{union['id']}/wards", json={"name": ward_name or f"{name} Ward"}), 201)
    return make_agent(api, key=key, name=name, office_id=ward["office"]["id"])


class RecordingProvider(Provider):
    """A provider for tests: records every call and can run a hook while the agent is 'working'."""

    name = "recorder"

    def __init__(self) -> None:
        self.calls: list[tuple[AgentContext, TaskContext]] = []
        self.hook: Any = None

    def is_configured(self) -> bool:
        return True

    def reply(self, agent: AgentContext, task: TaskContext) -> str:
        self.calls.append((agent, task))
        if self.hook is not None:
            self.hook()
        return f"recorded reply of {agent.display_name}"


@pytest.fixture
def recorder() -> Iterator[RecordingProvider]:
    provider = RecordingProvider()
    register_provider(provider)
    yield provider
    unregister_provider(provider.name)


# ---------------------------------------------------------------- migrations


def test_migrations_0003_to_0005_up_and_down_keep_existing_data(env: Path) -> None:
    config = alembic_config()
    command.upgrade(config, "0003")
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(get_settings().db_file) as connection:  # shaped like the live M2 village
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO village (name, chairman_name, timezone, ai_mode, default_structure, created_at) "
            "VALUES ('Old Village', 'Riyan', 'Asia/Dhaka', 'demo', 'standard', ?)",
            (now,),
        )
        connection.execute("INSERT INTO admin_user (username, password_hash, created_at) VALUES ('chairman', 'hash', ?)", (now,))
        connection.execute(
            "INSERT INTO upazila (village_id, name, description, icon, template_key, sort_order, created_at, updated_at) "
            "VALUES (1, 'Study Upazila', '', 'graduation-cap', 'study', 1, ?, ?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO union_unit (upazila_id, name, description, sort_order, created_at, updated_at) "
            "VALUES (1, 'Academic Management', '', 1, ?, ?)",
            (now, now),
        )
        for number in range(1, 10):
            connection.execute(
                "INSERT INTO ward (union_id, number, name, responsibility, created_at, updated_at) VALUES (1, ?, ?, '', ?, ?)",
                (number, f"Ward {number}", now, now),
            )
            connection.execute(
                "INSERT INTO office (kind, ward_id, name, description, created_at, updated_at) VALUES ('ward', ?, ?, '', ?, ?)",
                (number, f"Ward {number} Office", now, now),
            )
    m2_sql = (
        "SELECT (SELECT group_concat(name) FROM village), (SELECT group_concat(username || password_hash) FROM admin_user), "
        "(SELECT group_concat(name) FROM upazila), (SELECT group_concat(name) FROM union_unit), "
        "(SELECT group_concat(name) FROM ward), (SELECT group_concat(name) FROM office), "
        "(SELECT COUNT(*) FROM upazila_template), (SELECT COUNT(*) FROM union_template), (SELECT COUNT(*) FROM ward_template)"
    )
    m2 = rows(m2_sql)
    agents_sql = "SELECT (SELECT COUNT(*) FROM agent_template), (SELECT group_concat(display_name) FROM agent)"

    def tables() -> set[str]:
        return {row[0] for row in rows("SELECT name FROM sqlite_master WHERE type='table'")}

    def version() -> str:
        return rows("SELECT value FROM app_meta WHERE key = 'schema_version'")[0][0]

    command.upgrade(config, "0004")
    assert rows(m2_sql) == m2 and version() == "4" and not tables() & {"task", "agent_message"}
    with sqlite3.connect(get_settings().db_file) as connection:  # an agent the owner created under 0004
        connection.execute(
            "INSERT INTO agent (display_name, avatar_key, role, description, template_id, office_id, system_instructions, "
            "allowed_tools, permissions, provider, memory_config, working_schedule, lifecycle, runtime_state, "
            "is_central_manager, created_at, updated_at) VALUES ('Mina', 'student', 'Study Assistant', '', 4, 2, '', "
            "'[]', '[]', 'demo', '{}', '{}', 'active', 'idle', 0, ?, ?)",
            (now, now),
        )
    agents = rows(agents_sql)
    assert agents == [(15, "Central Manager,Mina")]

    command.upgrade(config, "0005")
    assert check()["current"] == "0005" and version() == "5"
    assert {"task", "agent_message"} <= tables()
    assert rows(m2_sql) == m2 and rows(agents_sql) == agents
    assert rows("SELECT COUNT(*) FROM task") == [(0,)] and rows("SELECT COUNT(*) FROM agent_message") == [(0,)]

    command.downgrade(config, "0004")
    assert not tables() & {"task", "agent_message"} and version() == "4"
    assert rows(m2_sql) == m2 and rows(agents_sql) == agents

    command.downgrade(config, "0003")
    assert not tables() & {"task", "agent_message", "agent", "agent_template"} and version() == "3"
    assert rows(m2_sql) == m2

    command.upgrade(config, "head")  # and all the way up again
    assert check()["current"] == check()["head"] and rows(m2_sql) == m2
    assert rows(agents_sql) == [(15, "Central Manager")]  # the downgrade to 0003 dropped the agent table


def test_database_rejects_unknown_status_priority_and_message_type(api: TestClient) -> None:  # noqa: F811
    task = send(api)
    manager = central_manager(api)["id"]
    with sqlite3.connect(get_settings().db_file) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE task SET status = 'DONE' WHERE id = ?", (task["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE task SET priority = 'urgent' WHERE id = ?", (task["id"],))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO agent_message (sender_agent_id, receiver_agent_id, task_id, type, payload, created_at) "
                "VALUES (?, ?, ?, 'gossip', '{}', '2026-01-01')",
                (manager, manager, task["id"]),
            )


# ---------------------------------------------------------------- status transitions

ALLOWED = {
    (QUEUED, ASSIGNED),
    (QUEUED, FAILED),
    (QUEUED, CANCELLED),
    (ASSIGNED, RUNNING),
    (ASSIGNED, FAILED),
    (ASSIGNED, CANCELLED),
    (RUNNING, WAITING_APPROVAL),
    (RUNNING, SUCCEEDED),
    (RUNNING, FAILED),
    (RUNNING, CANCELLED),
    (RUNNING, QUEUED),  # crash recovery only
    (WAITING_APPROVAL, RUNNING),
    (WAITING_APPROVAL, FAILED),
    (WAITING_APPROVAL, CANCELLED),
}


@pytest.mark.parametrize("current", STATUSES)
@pytest.mark.parametrize("new", STATUSES)
def test_only_valid_status_transitions_are_allowed(current: str, new: str) -> None:
    assert can_transition(current, new) is ((current, new) in ALLOWED)
    if (current, new) in ALLOWED:
        ensure_transition(current, new)
    else:
        with pytest.raises(InvalidTransition, match=f"cannot go from {current} to {new}"):
            ensure_transition(current, new)


def test_statuses_are_the_seven_of_the_spec_and_finished_tasks_never_change() -> None:
    assert set(STATUSES) == {"QUEUED", "ASSIGNED", "RUNNING", "WAITING_APPROVAL", "SUCCEEDED", "FAILED", "CANCELLED"}
    assert TERMINAL == {SUCCEEDED, FAILED, CANCELLED}
    assert not any(can_transition(done, new) for done in TERMINAL for new in STATUSES)
    assert not can_transition("NONSENSE", QUEUED)


def test_move_task_checks_the_rules_sets_timestamps_and_loses_races_cleanly(api: TestClient) -> None:  # noqa: F811
    task_id = send(api)["id"]
    with get_session_factory()() as db:
        task = db.get(Task, task_id)
        assert task is not None and task.status == QUEUED
        with pytest.raises(InvalidTransition):
            move_task(db, task, SUCCEEDED)  # QUEUED → SUCCEEDED skips the work
        assert move_task(db, task, ASSIGNED) and task.started_at is None
        assert move_task(db, task, RUNNING) and task.started_at is not None and task.completed_at is None
        db.commit()

        with get_session_factory()() as other:  # someone else cancels it meanwhile
            theirs = other.get(Task, task_id)
            assert theirs is not None and move_task(other, theirs, CANCELLED)
            other.commit()

        assert move_task(db, task, SUCCEEDED, output="late") is False  # the cancel wins
        assert (task.status, task.output) == (CANCELLED, None) and task.completed_at is not None
        with pytest.raises(InvalidTransition):
            move_task(db, task, RUNNING)


# ---------------------------------------------------------------- classification (pure)

SAMPLE_REQUESTS = {
    "study": "help me prepare for my exam",
    "business": "write a marketing plan for my new product",
    "career": "update my CV for a software job interview",
    "research": "find papers for my literature review",
    "project": "fix the bug in the backend API",
    "personal": "set a daily reminder for my morning routine",
}
STANDARD = [
    cm.UpazilaInfo(id=index, name=name, template_key=key, sort_order=index)
    for index, (key, name) in enumerate(
        [
            ("study", "Study Upazila"),
            ("business", "Business Upazila"),
            ("career", "Career & Job Preparation Upazila"),
            ("research", "Research Upazila"),
            ("project", "Project Development Upazila"),
            ("personal", "Personal Management Upazila"),
        ],
        start=1,
    )
]


def test_keyword_table_covers_the_six_templates_and_samples() -> None:
    assert set(ROUTING_KEYWORDS) == set(SAMPLE_REQUESTS) == {info.template_key for info in STANDARD}
    assert all(keyword == keyword.lower().strip() for keywords in ROUTING_KEYWORDS.values() for keyword in keywords)


@pytest.mark.parametrize("key", list(SAMPLE_REQUESTS))
def test_classify_picks_the_right_upazila_for_each_template(key: str) -> None:
    found = cm.classify(SAMPLE_REQUESTS[key], STANDARD)
    assert found.upazila is not None and found.upazila.template_key == key
    assert found.matched and found.reason is None


def test_classify_details() -> None:
    assert cm.classify("Three EXAMS next week", STANDARD).matched == ("exam",)  # plural, any case
    assert cm.classify("examine the examples", STANDARD).upazila is None  # whole words only
    assert cm.classify("do a data analysis", STANDARD).upazila.template_key == "research"  # type: ignore[union-attr]  # a phrase
    # more matching keywords win; a tie goes to the first Upazila in the village's order
    assert cm.classify("exam and homework for my project", STANDARD).upazila.template_key == "study"  # type: ignore[union-attr]
    assert cm.classify("exam project", STANDARD).upazila.template_key == "study"  # type: ignore[union-attr]
    # an Upazila without a template is known by its own name and its Union names
    garden = cm.UpazilaInfo(id=9, name="Garden", template_key=None, sort_order=9, union_names=("Vegetable Beds",))
    assert cm.classify("water the garden", [*STANDARD, garden]).upazila == garden
    assert cm.classify("plant a new vegetable", [*STANDARD, garden]).upazila == garden
    # a renamed template Upazila still gets its template's keywords, plus its new name
    renamed = cm.UpazilaInfo(id=1, name="Madrasa", template_key="study", sort_order=1)
    assert cm.classify("exam", [renamed]).upazila == renamed and cm.classify("madrasa fees", [renamed]).upazila == renamed


def test_classify_explains_why_nothing_matched() -> None:
    nothing = cm.classify("hello there", STANDARD)
    assert nothing.upazila is None and "could not tell which Upazila" in (nothing.reason or "")
    only_study = [STANDARD[0]]
    missing = cm.classify("write a marketing plan", only_study, {"business": "Business Upazila"})
    assert missing.upazila is None
    assert "'Business Upazila'" in (missing.reason or "") and "marketing" in (missing.reason or "")
    assert "no Upazila for it" in (missing.reason or "")
    empty = cm.classify("hello there", [])
    assert "no Upazilas yet" in (empty.reason or "")


# ---------------------------------------------------------------- the whole flow


def test_request_is_routed_delegated_run_by_the_demo_provider_and_reported(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")  # Study Assistant in Study Upazila › Academic Management › Ward 1
    manager = central_manager(api)

    queued = send(api, "Help me prepare for my exam", description="Physics, next Sunday")
    assert (queued["status"], queued["assigned_agent"], queued["parent_task_id"], queued["depth"]) == ("QUEUED", None, None, 0)
    assert (queued["created_by"], queued["created_by_name"], queued["priority"]) == ("chairman", "chairman", "normal")
    assert queued["input"] == {"request": "Help me prepare for my exam\nPhysics, next Sunday"}
    assert queued["output"] is None and queued["started_at"] is None and queued["child_count"] == 0

    assert run_once() is True  # step 1: the Central Manager routes and delegates
    routed = detail(api, queued["id"])
    assert routed["status"] == "RUNNING" and routed["assigned_agent"]["id"] == manager["id"]
    assert routed["started_at"] is not None and routed["child_count"] == 1
    child = routed["children"][0]
    assert (child["status"], child["assigned_agent"]["id"], child["parent_task_id"], child["depth"]) == ("ASSIGNED", mina["id"], queued["id"], 1)
    assert (child["created_by"], child["created_by_name"]) == (f"agent:{manager['id']}", "Central Manager")
    assert ok(api.get(f"/api/agents/{manager['id']}"))["runtime_state"] == "waiting"

    assert run_once() is True  # step 2: Mina answers through the Demo provider
    assert detail(api, child["id"])["status"] == "SUCCEEDED"
    assert detail(api, queued["id"])["status"] == "RUNNING"  # the report is the next step
    assert run_once() is True  # step 3: the Central Manager collects the result
    assert run_once() is False and drain() == 0  # the queue is empty

    done = detail(api, queued["id"])
    child = done["children"][0]
    assert child["status"] == "SUCCEEDED" and child["error"] is None
    assert child["output"].startswith("[Demo] Mina (Study Assistant, Study Upazila › Academic Management › Ward 1: Class Routine)")
    assert "no AI model was used" in child["output"] and "Physics, next Sunday" in child["output"]
    assert child["started_at"] is not None and child["completed_at"] is not None
    assert child["input"]["routing"] == {
        "upazila_id": mina["location"]["upazila"]["id"],
        "upazila_name": "Study Upazila",
        "matched_keywords": ["exam"],
        "agent_id": mina["id"],
        "agent_name": "Mina",
        "agent_role": "Study Assistant",
        "agent_path": "Study Upazila › Academic Management › Ward 1: Class Routine",
        "agent_matched_words": ["exam"],  # "exam" is in the Study Assistant's description
        "active_candidates": 1,
        "method": "demo keyword routing",
    }

    assert done["status"] == "SUCCEEDED" and done["error"] is None and done["completed_at"] is not None
    report = done["output"]
    assert report.startswith("[Demo] Central Manager report")
    assert "Routed to: Study Upazila (matched: exam) → Mina (Study Assistant)" in report
    assert "Delegated tasks: 1 succeeded, 0 not completed" in report
    assert f"--- Result from Mina (task #{child['id']}) ---" in report and child["output"] in report
    assert "did not do this work itself" in report

    # every delegation and every result is a message
    messages = done["messages"]
    assert [(m["type"], m["sender"]["display_name"], m["receiver"]["display_name"], m["task_id"]) for m in messages] == [
        ("delegation", "Central Manager", "Mina", child["id"]),
        ("result", "Mina", "Central Manager", child["id"]),
    ]
    assert messages[0]["payload"]["routing"]["upazila_name"] == "Study Upazila"
    assert messages[0]["payload"]["parent_task_id"] == queued["id"]
    assert messages[1]["payload"] == {"parent_task_id": queued["id"], "status": "SUCCEEDED", "output": child["output"]}
    assert detail(api, child["id"])["messages"] == messages and detail(api, child["id"])["children"] == []

    # both agents are idle again
    assert ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"] == "idle"
    assert ok(api.get(f"/api/agents/{manager['id']}"))["runtime_state"] == "idle"


@pytest.mark.parametrize("key", list(SAMPLE_REQUESTS))
def test_each_standard_upazila_receives_its_kind_of_request(api: TestClient, key: str) -> None:  # noqa: F811
    upazilas = {row["template_key"]: row for row in ok(api.post("/api/upazilas/standard"))["created"]}
    assert set(upazilas) == set(SAMPLE_REQUESTS)
    agents = {name: agent_in(api, upazila, "office_manager", f"{name} agent") for name, upazila in upazilas.items()}

    done = run(api, SAMPLE_REQUESTS[key])
    assert done["status"] == "SUCCEEDED", done["error"]
    child = done["children"][0]
    assert child["assigned_agent"]["id"] == agents[key]["id"]
    assert child["input"]["routing"]["upazila_id"] == upazilas[key]["id"]
    assert child["input"]["routing"]["matched_keywords"]


def test_custom_upazila_is_routed_by_its_own_name(api: TestClient) -> None:  # noqa: F811
    garden = make_upazila(api, "Garden")
    kamal = agent_in(api, garden, "pion_helper", "Kamal")
    done = run(api, "water the garden tonight")
    assert done["status"] == "SUCCEEDED"
    assert done["children"][0]["assigned_agent"]["id"] == kamal["id"]
    assert done["children"][0]["input"]["routing"]["matched_keywords"] == ["garden"]


def test_best_matching_agent_in_the_upazila_gets_the_task(api: TestClient) -> None:  # noqa: F811
    first = make_agent(api, key="pion_helper", name="Helper")  # Ward 1: Class Routine
    exam_office = study_office(api, union=0, ward=2)  # Ward 3: Exam Preparation
    tutor = make_agent(api, key="teacher_tutor", name="Tutor", office_id=exam_office["office"]["id"])
    notes_office = study_office(api, union=0, ward=4)  # Ward 5: Note Making
    notes = make_agent(api, key="pion_helper", name="Notes", office_id=notes_office["office"]["id"])

    exam = run(api, "exam next week")
    assert exam["children"][0]["assigned_agent"]["id"] == tutor["id"]  # its ward is "Exam Preparation"
    assert exam["children"][0]["input"]["routing"]["agent_matched_words"] == ["exam"]
    assert exam["children"][0]["input"]["routing"]["active_candidates"] == 3

    note = run(api, "study: tidy my note making")
    assert note["children"][0]["assigned_agent"]["id"] == notes["id"]

    # nothing about any agent matches: any active one — the first
    other = run(api, "plan my semester")
    assert other["children"][0]["assigned_agent"]["id"] == first["id"]
    assert other["children"][0]["input"]["routing"]["agent_matched_words"] == []


# ---------------------------------------------------------------- failures with a reason


def test_no_matching_upazila_fails_with_a_readable_reason(api: TestClient, recorder: RecordingProvider) -> None:  # noqa: F811
    make_agent(api)
    done = run(api, "hello there")
    assert done["status"] == "FAILED" and done["children"] == [] and done["messages"] == []
    assert "could not tell which Upazila this request belongs to" in done["error"]
    assert done["output"] is None and done["completed_at"] is not None

    missing = run(api, "write a marketing plan")  # a known topic, but the village has no Business Upazila
    assert missing["status"] == "FAILED"
    assert "'Business Upazila'" in missing["error"] and "no Upazila for it" in missing["error"]
    assert central_manager(api)["runtime_state"] == "idle"


def test_no_active_agent_fails_with_a_readable_reason(api: TestClient) -> None:  # noqa: F811
    study_office(api)  # Study Upazila with 45 offices and no agent
    done = run(api)
    assert done["status"] == "FAILED" and done["children"] == []
    assert done["error"] == (
        "The request was matched to 'Study Upazila' (keywords: exam), but that Upazila has no active agent. "
        "Create or activate an agent in one of its Offices and send the request again."
    )


def test_village_without_upazilas_fails_with_a_readable_reason(api: TestClient) -> None:  # noqa: F811
    done = run(api, "anything at all")
    assert done["status"] == "FAILED" and "no Upazilas yet" in done["error"]


def test_paused_and_disabled_agents_never_receive_tasks(api: TestClient) -> None:  # noqa: F811
    exam_office = study_office(api, union=0, ward=2)  # the best match for "exam"
    best = make_agent(api, key="teacher_tutor", name="Tutor", office_id=exam_office["office"]["id"])
    other = make_agent(api, key="pion_helper", name="Helper")
    disabled = make_agent(api, key="study_assistant", name="Old")
    ok(api.post(f"/api/agents/{best['id']}/pause"))
    ok(api.post(f"/api/agents/{disabled['id']}/disable"))

    done = run(api)
    assert done["status"] == "SUCCEEDED"
    assert done["children"][0]["assigned_agent"]["id"] == other["id"]  # the paused best match was skipped

    ok(api.post(f"/api/agents/{other['id']}/pause"))
    failed = run(api)
    assert failed["status"] == "FAILED" and failed["children"] == []
    assert "has no active agent. (3 agents there are paused or disabled.)" in failed["error"]
    for agent in (best, other, disabled):
        tasks = ok(api.get(f"/api/tasks?agent_id={agent['id']}"))
        assert len(tasks) == (1 if agent is other else 0)


def test_agent_paused_after_the_handover_does_not_run_the_task(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    task = send(api)
    assert run_once()  # delegated to Mina
    ok(api.post(f"/api/agents/{mina['id']}/pause"))
    drain()
    done = detail(api, task["id"])
    child = done["children"][0]
    assert child["status"] == "FAILED" and child["output"] is None
    assert child["error"] == "'Mina' is paused, so it did not receive this task."
    assert done["status"] == "FAILED"
    assert done["error"] == f"None of the delegated tasks succeeded: task #{child['id']} FAILED ({child['error']})"
    assert done["messages"][-1]["payload"] == {"parent_task_id": task["id"], "status": "FAILED", "error": child["error"]}
    assert ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"] == "offline"


def test_provider_failure_fails_the_task_and_the_queue_goes_on(api: TestClient, recorder: RecordingProvider) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    ok(api.patch(f"/api/agents/{mina['id']}", json={"provider": "recorder"}))

    def boom() -> None:
        raise RuntimeError("secret detail that must not be shown")

    recorder.hook = boom
    failed = run(api)
    assert failed["status"] == "FAILED"
    assert failed["children"][0]["error"] == "The recorder provider failed (RuntimeError)."
    assert "secret detail" not in str(failed)

    recorder.hook = None
    assert run(api)["status"] == "SUCCEEDED"
    assert ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"] == "idle"


# ---------------------------------------------------------------- central manager rules


def test_central_manager_never_does_the_work_itself(api: TestClient, recorder: RecordingProvider) -> None:  # noqa: F811
    manager = central_manager(api)
    mina = make_agent(api, name="Mina")
    ok(api.patch(f"/api/agents/{manager['id']}", json={"provider": "recorder"}))
    ok(api.patch(f"/api/agents/{mina['id']}", json={"provider": "recorder"}))

    done = run(api)
    assert done["status"] == "SUCCEEDED"
    assert [agent.display_name for agent, _task in recorder.calls] == ["Mina"]  # the provider was asked for Mina only
    assert done["output"].startswith("[Demo] Central Manager report") and "recorded reply of Mina" in done["output"]

    recorder.calls.clear()
    assert run(api, "hello there")["status"] == "FAILED"  # nobody to delegate to: it fails, it does not answer
    assert recorder.calls == []

    # even a task handed to the Central Manager by mistake is refused, not answered
    with get_session_factory()() as db:
        parent = db.get(Task, done["id"])
        assert parent is not None
        stray = Task(title="do it yourself", created_by="test", assigned_agent_id=manager["id"], parent_task_id=parent.id, depth=1, status=ASSIGNED)
        db.add(stray)
        db.commit()
        stray_id = stray.id
    drain()
    assert detail(api, stray_id)["error"] == "The Central Manager does not do delegated work itself."
    assert recorder.calls == []


def test_agent_is_working_while_its_task_runs_and_idle_after(api: TestClient, recorder: RecordingProvider) -> None:  # noqa: F811
    manager = central_manager(api)
    mina = make_agent(api, name="Mina")
    ok(api.patch(f"/api/agents/{mina['id']}", json={"provider": "recorder"}))
    seen: dict[str, Any] = {}

    def look() -> None:  # runs inside provider.reply
        seen["agent"] = ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"]
        seen["manager"] = ok(api.get(f"/api/agents/{manager['id']}"))["runtime_state"]
        seen["statuses"] = [task["status"] for task in ok(api.get("/api/tasks"))]

    recorder.hook = look
    assert run(api)["status"] == "SUCCEEDED"
    assert seen == {"agent": "working", "manager": "waiting", "statuses": ["RUNNING", "RUNNING"]}
    assert ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"] == "idle"
    assert ok(api.get(f"/api/agents/{manager['id']}"))["runtime_state"] == "idle"
    agent, task = recorder.calls[0]
    assert agent.template_key == "study_assistant" and agent.system_instructions == mina["system_instructions"]
    assert task.title == EXAM_REQUEST


def test_delegation_depth_is_limited_to_three(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    task = send(api)
    assert run_once()  # depth 0 → the child at depth 1
    assert cm.MAX_DELEGATION_DEPTH == 3
    with get_session_factory()() as db:
        agent = db.get(Agent, mina["id"])
        assert agent is not None
        current = db.execute(Task.__table__.select().where(Task.parent_task_id == task["id"])).first()
        level = db.get(Task, current.id)  # type: ignore[union-attr]
        assert level is not None and level.depth == 1
        for depth in (2, 3):
            level = cm.delegate(db, level, agent, {"note": "test"})
            db.flush()
            assert level.depth == depth and level.status == ASSIGNED and level.created_by == f"agent:{mina['id']}"
        with pytest.raises(cm.DelegationDepthError, match="at most 3 times"):
            cm.delegate(db, level, agent)
        db.commit()
        assert db.query(Task).count() == 4  # depths 0, 1, 2, 3 — nothing at depth 4
        assert db.query(AgentMessage).filter_by(type="delegation").count() == 3

    drain()  # the deepest tasks run first; every level reports to the one above
    done = detail(api, task["id"])
    assert done["status"] == "SUCCEEDED"
    assert [message["type"] for message in done["messages"]].count("result") == 3
    assert {row[0] for row in rows("SELECT status FROM task")} == {"SUCCEEDED"}


def test_high_priority_requests_are_started_first(api: TestClient) -> None:  # noqa: F811
    make_agent(api)
    low = send(api, "exam one", priority="low")
    normal = send(api, "exam two")
    high = send(api, "exam three", priority="high")
    order: list[int] = []  # the order in which the requests leave the queue
    finished: list[int] = []
    while run_once():
        for task in reversed(ok(api.get("/api/tasks?top_level=true"))):
            if task["status"] != "QUEUED" and task["id"] not in order:
                order.append(task["id"])
            if task["status"] == "SUCCEEDED" and task["id"] not in finished:
                finished.append(task["id"])
    assert order == [high["id"], normal["id"], low["id"]]
    # a delegated task inherits the priority, so the urgent request is also finished first
    assert finished == [high["id"], normal["id"], low["id"]]
    assert {task["status"] for task in ok(api.get("/api/tasks"))} == {"SUCCEEDED"}


# ---------------------------------------------------------------- cancel


def test_cancel_cancels_the_children_too(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    manager = central_manager(api)
    task = send(api)
    assert run_once()  # RUNNING parent, ASSIGNED child
    cancelled = ok(api.post(f"/api/tasks/{task['id']}/cancel"))
    assert cancelled["status"] == "CANCELLED" and cancelled["completed_at"] is not None
    assert [child["status"] for child in cancelled["children"]] == ["CANCELLED"]
    assert drain() == 0  # nothing left to run
    after = detail(api, task["id"])
    assert after["status"] == "CANCELLED" and after["output"] is None
    assert after["children"][0]["output"] is None
    assert ok(api.get(f"/api/agents/{manager['id']}"))["runtime_state"] == "idle"
    assert ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"] == "idle"

    again = api.post(f"/api/tasks/{task['id']}/cancel")
    assert again.status_code == 409 and "already CANCELLED" in again.json()["detail"]
    assert api.post("/api/tasks/999/cancel").status_code == 404


def test_cancel_of_a_queued_request_and_of_a_finished_one(api: TestClient) -> None:  # noqa: F811
    make_agent(api)
    queued = send(api)
    assert ok(api.post(f"/api/tasks/{queued['id']}/cancel"))["status"] == "CANCELLED"
    assert drain() == 0
    finished = run(api)
    response = api.post(f"/api/tasks/{finished['id']}/cancel")
    assert response.status_code == 409 and "already SUCCEEDED" in response.json()["detail"]
    assert detail(api, finished["id"])["status"] == "SUCCEEDED"


def test_cancel_while_the_agent_is_working_keeps_the_task_cancelled(api: TestClient, recorder: RecordingProvider) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    ok(api.patch(f"/api/agents/{mina['id']}", json={"provider": "recorder"}))
    task = send(api)
    recorder.hook = lambda: ok(api.post(f"/api/tasks/{task['id']}/cancel"))  # arrives in the middle of the work
    drain()
    done = detail(api, task["id"])
    assert done["status"] == "CANCELLED" and done["output"] is None
    child = done["children"][0]
    assert child["status"] == "CANCELLED" and child["output"] is None  # the late reply was thrown away
    assert [message["type"] for message in done["messages"]] == ["delegation"]  # no result message
    assert ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"] == "idle"
    assert central_manager(api)["runtime_state"] == "idle"


def test_cancelling_only_the_child_fails_the_parent_with_the_reason(api: TestClient) -> None:  # noqa: F811
    make_agent(api)
    task = send(api)
    assert run_once()
    child = detail(api, task["id"])["children"][0]
    assert ok(api.post(f"/api/tasks/{child['id']}/cancel"))["status"] == "CANCELLED"
    drain()
    done = detail(api, task["id"])
    assert done["status"] == "FAILED"
    assert done["error"] == f"None of the delegated tasks succeeded: task #{child['id']} CANCELLED"


# ---------------------------------------------------------------- crash recovery + the worker


def test_tasks_left_running_by_a_crash_are_queued_again(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    manager = central_manager(api)
    task = send(api)
    untouched = send(api, "exam two")
    assert run_once()  # parent RUNNING, child ASSIGNED
    child_id = detail(api, task["id"])["children"][0]["id"]
    with sqlite3.connect(get_settings().db_file) as connection:  # the state a crash in the middle of the work leaves
        connection.execute("UPDATE task SET status = 'RUNNING', started_at = '2026-01-01' WHERE id = ?", (child_id,))
        connection.execute("UPDATE agent SET runtime_state = 'working' WHERE id = ?", (mina["id"],))

    with get_session_factory()() as db:
        assert recover_interrupted(db) == 2
    for task_id in (task["id"], child_id):
        recovered = detail(api, task_id)
        assert (recovered["status"], recovered["error"]) == ("QUEUED", INTERRUPTED_NOTE)
        assert recovered["completed_at"] is None
    assert detail(api, untouched["id"])["status"] == "QUEUED" and detail(api, untouched["id"])["error"] is None
    assert ok(api.get(f"/api/agents/{mina['id']}"))["runtime_state"] == "idle"
    assert ok(api.get(f"/api/agents/{manager['id']}"))["runtime_state"] == "idle"
    with get_session_factory()() as db:
        assert recover_interrupted(db) == 0  # nothing left to recover

    drain()
    done = detail(api, task["id"])
    assert done["status"] == "SUCCEEDED" and done["error"] is None
    assert [child["id"] for child in done["children"]] == [child_id]  # the request was not delegated a second time
    assert done["children"][0]["status"] == "SUCCEEDED" and done["children"][0]["error"] is None
    assert [message["type"] for message in done["messages"]] == ["delegation", "result"]
    assert detail(api, untouched["id"])["status"] == "SUCCEEDED"


def wait_for(api: TestClient, task_id: int, seconds: float = 15.0) -> dict[str, Any]:  # noqa: F811
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = detail(api, task_id)
        if current["status"] in TERMINAL:
            return current
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} did not finish: {detail(api, task_id)}")


def test_background_worker_runs_with_the_app_and_recovers_on_start(migrated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setenv("VILLAGE_TASK_WORKER", "1")
    get_settings.cache_clear()
    assert get_settings().task_worker is True
    monkeypatch.setattr(task_runner, "POLL_SECONDS", 0.05)

    with TestClient(create_app(), base_url=BASE_URL) as client:  # the lifespan starts the worker
        do_setup(client)
        mina = make_agent(client, name="Mina")
        first = send(client)
        done = wait_for(client, first["id"])
        assert done["status"] == "SUCCEEDED", done
        assert done["children"][0]["output"].startswith("[Demo] Mina")
        failed = wait_for(client, send(client, "hello there")["id"])
        assert failed["status"] == "FAILED" and "could not tell" in failed["error"]
    # the lifespan stopped the worker: nothing is processed any more
    assert not [thread for thread in __import__("threading").enumerate() if thread.name == "village-task-worker"]

    with sqlite3.connect(get_settings().db_file) as connection:  # a "crash": one request stuck in RUNNING
        connection.execute(
            "INSERT INTO task (title, description, created_by, depth, priority, input, status, created_at, updated_at, "
            "started_at) VALUES ('exam after the crash', '', 'chairman', 0, 'normal', '{}', 'RUNNING', '2026-01-01', "
            "'2026-01-01', '2026-01-01')"
        )
        stuck = connection.execute("SELECT id FROM task WHERE status = 'RUNNING'").fetchone()[0]
    with TestClient(create_app(), base_url=BASE_URL) as client:  # the next start recovers and finishes it
        ok(client.post("/api/auth/login", json={"username": "chairman", "password": PASSWORD}))
        recovered = wait_for(client, stuck)
        assert recovered["status"] == "SUCCEEDED" and recovered["error"] is None
        assert recovered["children"][0]["assigned_agent"]["id"] == mina["id"]


def test_worker_is_off_in_tests_and_not_started_without_the_task_table(client: TestClient) -> None:
    import threading

    assert get_settings().task_worker is False
    assert not [thread for thread in threading.enumerate() if thread.name == "village-task-worker"]


def test_unexpected_error_in_a_step_fails_that_task_only(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    make_agent(api)
    broken = send(api, "exam one")
    healthy = send(api, "exam two")
    real_route = cm.route
    calls = {"n": 0}

    def flaky(db: Any, task: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real_route(db, task)

    monkeypatch.setattr(cm, "route", flaky)
    drain()
    assert detail(api, broken["id"])["status"] == "FAILED"
    assert detail(api, broken["id"])["error"] == "Internal error while running the task (RuntimeError)."
    assert detail(api, healthy["id"])["status"] == "SUCCEEDED"
    assert central_manager(api)["runtime_state"] == "idle"


# ---------------------------------------------------------------- agent history


def test_agent_with_history_cannot_be_deleted_only_disabled(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    fresh = make_agent(api, key="pion_helper", name="Fresh", office_id=study_office(api, union=1)["office"]["id"])
    done = run(api)
    assert done["children"][0]["assigned_agent"]["id"] == mina["id"]

    assert ok(api.get(f"/api/agents/{mina['id']}"))["has_history"] is True
    assert central_manager(api)["has_history"] is True
    assert ok(api.get(f"/api/agents/{fresh['id']}"))["has_history"] is False
    assert {agent["display_name"]: agent["has_history"] for agent in ok(api.get("/api/agents"))} == {
        "Central Manager": True,
        "Mina": True,
        "Fresh": False,
    }

    refused = delete(api, f"/api/agents/{mina['id']}", {"confirm_name": "Mina"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "'Mina' has task history, so it cannot be deleted. Disable it instead — its history is kept."
    disabled = ok(api.post(f"/api/agents/{mina['id']}/disable"))
    assert disabled["lifecycle"] == "disabled"
    history = ok(api.get(f"/api/tasks?agent_id={mina['id']}"))
    assert [task["status"] for task in history] == ["SUCCEEDED"]  # the history is kept
    assert ok(delete(api, f"/api/agents/{fresh['id']}", {"confirm_name": "Fresh"})) == {"deleted": True}


def test_deleting_the_office_of_an_agent_with_history_keeps_agent_and_tasks(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api, name="Mina")
    done = run(api)
    upazila = mina["location"]["upazila"]
    result = ok(delete(api, f"/api/upazilas/{upazila['id']}", {"confirm_name": upazila["name"]}))
    assert result["agents_disabled"] == 1
    after = ok(api.get(f"/api/agents/{mina['id']}"))
    assert (after["office_id"], after["lifecycle"], after["has_history"]) == (None, "disabled", True)
    kept = detail(api, done["id"])
    assert kept["status"] == "SUCCEEDED" and kept["children"][0]["assigned_agent"]["display_name"] == "Mina"
    assert len(kept["messages"]) == 2


# ---------------------------------------------------------------- API details


def test_task_api_validation_filters_and_404(api: TestClient) -> None:  # noqa: F811
    assert api.post("/api/tasks", json={"title": "  "}).status_code == 422
    assert api.post("/api/tasks", json={"title": "x" * 201}).status_code == 422
    assert api.post("/api/tasks", json={"title": "ok", "description": "x" * 4001}).status_code == 422
    assert api.post("/api/tasks", json={"title": "ok", "priority": "urgent"}).status_code == 422
    assert api.post("/api/tasks", json={"title": "ok", "status": "SUCCEEDED"}).status_code == 422  # unknown field
    assert api.post("/api/tasks", json={}).status_code == 422
    assert ok(api.get("/api/tasks")) == []
    assert api.get("/api/tasks/999").status_code == 404

    mina = make_agent(api, name="Mina")
    manager = central_manager(api)
    first = run(api, "  exam one  ", description="  with spaces  ")
    assert (first["title"], first["description"]) == ("exam one", "with spaces")
    failed = run(api, "hello there")
    queued = send(api, "exam three")

    def ids(query: str = "") -> list[int]:
        return [task["id"] for task in ok(api.get(f"/api/tasks{query}"))]

    child_id = first["children"][0]["id"]
    assert ids() == [queued["id"], failed["id"], child_id, first["id"]]  # newest first, children included
    assert ids("?top_level=true") == [queued["id"], failed["id"], first["id"]]
    assert ids("?status=SUCCEEDED") == [child_id, first["id"]]
    assert ids("?status=SUCCEEDED&top_level=true") == [first["id"]]
    assert ids("?status=FAILED") == [failed["id"]] and ids("?status=QUEUED") == [queued["id"]]
    assert ids(f"?agent_id={mina['id']}") == [child_id]
    assert ids(f"?agent_id={manager['id']}") == [failed["id"], first["id"]]  # the queued one has no agent yet
    assert ids("?limit=2") == [queued["id"], failed["id"]]
    assert api.get("/api/tasks?status=DONE").status_code == 422
    assert api.get("/api/tasks?limit=0").status_code == 422
    listed = next(task for task in ok(api.get("/api/tasks")) if task["id"] == first["id"])
    assert listed["child_count"] == 1 and listed["assigned_agent"]["is_central_manager"] is True
    assert "children" not in listed and "messages" not in listed


TASK_ROUTES = {
    ("POST", "/api/tasks"),
    ("GET", "/api/tasks"),
    ("GET", "/api/tasks/{task_id}"),
    ("POST", "/api/tasks/{task_id}/cancel"),
}


def test_every_task_route_needs_a_session(api: TestClient) -> None:  # noqa: F811
    make_agent(api)
    task = send(api)
    api.cookies.clear()

    routes = api_routes(api.app)
    assert {route for route in routes if route[1].startswith("/api/tasks")} == TASK_ROUTES
    for method, path_template in sorted(TASK_ROUTES):
        path = re.sub(r"\{\w+\}", str(task["id"]), path_template)
        response = api.request(method, path, json=None if method == "GET" else {"title": "Hacked"})
        assert response.status_code == 401, (method, path, response.text)
    assert rows("SELECT COUNT(*), MIN(status), MAX(status) FROM task") == [(1, "QUEUED", "QUEUED")]


def test_template_helper_is_used(api: TestClient) -> None:  # noqa: F811
    assert template(api, "study_assistant")["name"] == "Study Assistant"

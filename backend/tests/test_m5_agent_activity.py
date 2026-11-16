"""M5 Part B: an agent's activity (working / idle / waiting / offline) is computed, not stored."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import agent_activity
from app.agent_catalog import AGENT_TEMPLATES
from app.config import get_settings
from app.task_runner import drain, run_once
from tests.test_m2_org import api, ok  # noqa: F401  (api is a fixture)
from tests.test_m3_agents import central_manager, make_agent, rows
from tests.test_m3_tasks import detail, send
from tests.test_m4_approvals import ask, pending, support_agent
from tests.test_m4_memory_schedules import new_schedule


def activity(api: TestClient, agent_id: int) -> tuple[str, int | None]:  # noqa: F811
    agent = ok(api.get(f"/api/agents/{agent_id}"))
    listed = next(item for item in ok(api.get("/api/agents")) if item["id"] == agent_id)
    assert (agent["activity"], agent["current_task_id"]) == (listed["activity"], listed["current_task_id"])  # list and detail agree
    return agent["activity"], agent["current_task_id"]


@pytest.mark.parametrize(
    ("lifecycle", "running", "waiting", "expected"),
    [
        ("active", None, None, ("idle", None)),
        ("active", 7, None, ("working", 7)),
        ("active", None, 9, ("waiting", 9)),
        ("active", 7, 9, ("waiting", 9)),  # the task that needs the Chairman is what is shown
        ("paused", None, None, ("offline", None)),
        ("paused", 7, 9, ("offline", None)),
        ("disabled", 7, None, ("offline", None)),
    ],
)
def test_derivation_rule(lifecycle: str, running: int | None, waiting: int | None, expected: tuple[str, int | None]) -> None:
    assert agent_activity.derive(lifecycle, running, waiting) == expected
    assert expected[0] in agent_activity.ACTIVITIES and len(agent_activity.ACTIVITIES) == 4


def test_activity_follows_the_agents_tasks(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    manager = central_manager(api)
    assert activity(api, mina["id"]) == ("idle", None)
    assert activity(api, manager["id"]) == ("idle", None)

    task = send(api)
    assert run_once() is True  # routed and delegated: the Central Manager's request is RUNNING, Mina's task is ASSIGNED
    child = detail(api, task["id"])["children"][0]
    assert activity(api, manager["id"]) == ("working", task["id"])
    assert activity(api, mina["id"]) == ("idle", None)  # assigned, not started
    with sqlite3.connect(get_settings().db_file) as connection:  # the moment Mina's provider is busy
        connection.execute("UPDATE task SET status = 'RUNNING' WHERE id = ?", (child["id"],))
    assert activity(api, mina["id"]) == ("working", child["id"])
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("UPDATE task SET status = 'ASSIGNED' WHERE id = ?", (child["id"],))
    drain()
    assert activity(api, mina["id"]) == ("idle", None) and activity(api, manager["id"]) == ("idle", None)

    # paused and disabled agents are offline, whatever their tasks say
    ok(api.post(f"/api/agents/{mina['id']}/pause"))
    assert activity(api, mina["id"]) == ("offline", None)
    ok(api.post(f"/api/agents/{mina['id']}/disable"))
    assert activity(api, mina["id"]) == ("offline", None)
    ok(api.post(f"/api/agents/{mina['id']}/activate"))
    assert activity(api, mina["id"]) == ("idle", None)

    # nothing of this is stored
    assert "activity" not in {row[1] for row in rows("PRAGMA table_info(agent)")}
    assert "current_task_id" not in {row[1] for row in rows("PRAGMA table_info(agent)")}


def test_waiting_for_approval_shows_as_waiting(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api)
    manager = central_manager(api)
    result, child = ask(api)
    assert activity(api, sumi["id"]) == ("waiting", child["id"])
    assert activity(api, manager["id"]) == ("working", result["id"])  # its request is still open
    second_result, second_child = ask(api)
    assert activity(api, sumi["id"]) == ("waiting", child["id"])  # the oldest waiting task
    ok(api.post(f"/api/agents/{sumi['id']}/pause"))
    assert activity(api, sumi["id"]) == ("offline", None)
    ok(api.post(f"/api/agents/{sumi['id']}/activate"))
    for approval in pending(api):
        ok(api.post(f"/api/approvals/{approval['id']}/reject"))
    drain()
    assert activity(api, sumi["id"]) == ("idle", None) and activity(api, manager["id"]) == ("idle", None)
    assert second_result["id"] and second_child["id"]


def test_health_checks_do_not_make_anyone_busy(api: TestClient) -> None:  # noqa: F811
    manager = central_manager(api)
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute(
            "INSERT INTO task (title, description, created_by, assigned_agent_id, depth, kind, priority, input, status, created_at, updated_at) "
            "VALUES ('Agent health check', '', 'schedule:health_check', ?, 0, 'health_check', 'high', '{}', 'RUNNING', ?, ?)",
            (manager["id"], now, now),
        )
    assert activity(api, manager["id"]) == ("idle", None)


def test_agent_references_carry_the_template_key(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    sumi = support_agent(api)
    task = send(api)
    drain()
    result = detail(api, task["id"])
    assert result["assigned_agent"]["template_key"] == "village_manager"
    assert result["children"][0]["assigned_agent"]["template_key"] == "study_assistant"
    assert {message["sender"]["template_key"] for message in result["messages"]} == {"village_manager", "study_assistant"}
    ask(api)
    assert pending(api)[0]["agent"]["template_key"] == "customer_support"
    schedule = new_schedule(api, mina["id"])
    assert schedule["agent"]["template_key"] == "study_assistant" and sumi["template_key"] == "customer_support"
    # every template the application seeds has a key the frontend's robot table can use
    assert len({template.key for template in AGENT_TEMPLATES}) == 15


def test_agent_fields(api: TestClient) -> None:  # noqa: F811
    agent: dict[str, Any] = make_agent(api)
    assert agent["activity"] == "idle" and agent["current_task_id"] is None
    assert ok(api.post(f"/api/agents/{agent['id']}/pause"))["activity"] == "offline"


def test_every_template_has_a_robot_in_the_frontends_one_table() -> None:
    """The frontend maps templates to robots in ONE table (components/robots/roles.ts). A new
    template in the catalogue must be added there too — this test reads the file and checks."""
    import re

    from app.config import ROOT_DIR

    source = (ROOT_DIR / "frontend" / "src" / "components" / "robots" / "roles.ts").read_text(encoding="utf-8")
    table = source[source.index("TEMPLATE_ROBOTS") : source.index("};", source.index("TEMPLATE_ROBOTS"))]
    mapped = dict(re.findall(r"^\s*([a-z_]+):\s*\"([a-z]+)\",", table, flags=re.M))
    assert set(mapped) == {template.key for template in AGENT_TEMPLATES}
    assert set(mapped.values()) == {"manager", "pion", "doctor", "technician", "researcher", "sales"}
    assert mapped["doctor_wellness"] == "doctor" and mapped["repair_technician"] == "technician"

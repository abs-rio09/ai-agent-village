"""M5 Part A: the real overview numbers and the Recent Activity feed."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi.testclient import TestClient

from app.config import get_settings
from app.providers import DEMO_APPROVAL_PHRASE
from app.task_runner import drain
from tests.conftest import BASE_URL
from tests.test_m2_org import api, make_upazila, ok, statements  # noqa: F401  (fixtures)
from tests.test_m3_agents import make_agent, rows
from tests.test_m3_tasks import EXAM_REQUEST, send
from tests.test_m4_approvals import ask, pending, support_agent
from tests.test_part_b_auth import API_KEY, PASSWORD, api_routes, do_setup

TASK_KEYS = ("running_tasks", "completed_tasks", "failed_tasks", "pending_approvals")


def stats(api: TestClient) -> dict[str, int]:  # noqa: F811
    return ok(api.get("/api/stats/overview"))


def feed(api: TestClient, limit: int | None = None) -> list[dict[str, Any]]:  # noqa: F811
    return ok(api.get("/api/activity/recent" + (f"?limit={limit}" if limit else "")))


def sql(statement: str, *params: Any) -> None:
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute(statement, params)


# ---------------------------------------------------------------- overview numbers


def test_empty_village_shows_zero_everywhere(api: TestClient) -> None:  # noqa: F811
    # a village right after setup: no structure, no task — only what the application itself needs
    assert stats(api) == {
        "upazilas": 0, "unions": 0, "wards": 0,
        "offices": 1, "ward_offices": 0,  # Central Administration
        "agents": 1, "active_agents": 1,  # the Central Manager
        "running_tasks": 0, "completed_tasks": 0, "failed_tasks": 0, "pending_approvals": 0,
    }


def test_overview_counts_match_the_rows(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)  # Study Upazila: 5 Unions, 45 Wards
    support_agent(api)  # Business Upazila with one Union and Ward
    paused = make_agent(api, name="Rafi")
    ok(api.post(f"/api/agents/{paused['id']}/pause"))
    before = stats(api)
    assert {key: before[key] for key in ("upazilas", "unions", "wards", "offices", "ward_offices", "agents", "active_agents")} == {
        "upazilas": 2, "unions": 6, "wards": 46, "offices": 47, "ward_offices": 46, "agents": 4, "active_agents": 3,
    }
    assert {key: before[key] for key in TASK_KEYS} == dict.fromkeys(TASK_KEYS, 0)

    send(api, EXAM_REQUEST), send(api, "hello there"), send(api, DEMO_APPROVAL_PHRASE), send(api, DEMO_APPROVAL_PHRASE)
    drain()
    # exam: request + child SUCCEEDED (2); hello: request FAILED (1); two approvals: 2 requests RUNNING, 2 children waiting
    assert {key: stats(api)[key] for key in TASK_KEYS} == {"running_tasks": 2, "completed_tasks": 2, "failed_tasks": 1, "pending_approvals": 2}
    first, second = sorted(pending(api), key=lambda item: item["id"])
    ok(api.post(f"/api/approvals/{first['id']}/reject"))
    assert stats(api)["pending_approvals"] == 1  # a decided request no longer counts
    drain()
    ok(api.post(f"/api/approvals/{second['id']}/approve"))
    assert stats(api)["pending_approvals"] == 0
    drain()
    after = stats(api)
    assert {key: after[key] for key in TASK_KEYS} == {"running_tasks": 0, "completed_tasks": 4, "failed_tasks": 3, "pending_approvals": 0}

    # the numbers are the database's: compare with plain SQL
    assert after["completed_tasks"] == rows("SELECT COUNT(*) FROM task WHERE status = 'SUCCEEDED'")[0][0]
    assert after["failed_tasks"] == rows("SELECT COUNT(*) FROM task WHERE status = 'FAILED'")[0][0]
    assert after["agents"] == rows("SELECT COUNT(*) FROM agent")[0][0] and mina["id"]

    # the scheduler's health checks are housekeeping: they are not counted as work
    now = "2026-01-01 00:00:00"
    for status in ("SUCCEEDED", "FAILED", "RUNNING"):
        sql(
            "INSERT INTO task (title, description, created_by, depth, kind, priority, input, status, created_at, updated_at) "
            "VALUES ('Agent health check', '', 'schedule:health_check', 0, 'health_check', 'high', '{}', ?, ?, ?)",
            status, now, now,
        )
    assert {key: stats(api)[key] for key in TASK_KEYS} == {key: after[key] for key in TASK_KEYS}
    # every other kind is counted
    sql("UPDATE task SET kind = 'scheduled', status = 'RUNNING' WHERE kind = 'health_check' AND status = 'RUNNING'")
    assert stats(api)["running_tasks"] == 1


def test_overview_is_one_statement(api: TestClient, statements: list[str]) -> None:  # noqa: F811
    make_agent(api)
    statements.clear()
    stats(api)
    selects = [item for item in statements if item.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2  # the session lookup and ONE statement for all eleven numbers


# ---------------------------------------------------------------- recent activity


def test_activity_feed_is_built_from_audit_log_and_tasks(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    sumi = support_agent(api)
    send(api, EXAM_REQUEST)
    drain()
    result, child = ask(api)  # waits for approval
    events = feed(api, 100)

    assert [event["time"] for event in events] == sorted((event["time"] for event in events), reverse=True)  # newest first
    assert len({event["id"] for event in events}) == len(events)
    for event in events:
        assert set(event) == {"id", "time", "source", "action", "actor", "agent_id", "task_id", "text", "link", "tone"}
        assert event["text"] and event["actor"] and event["time"].endswith(("Z", "+00:00"))
        assert event["link"] is None or event["link"].startswith("/")  # a path inside the app, never an outside address
    by_action: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_action.setdefault(event["action"], []).append(event)

    # from the audit log
    created = by_action["agent.created"]
    assert {(event["actor"], event["link"]) for event in created} >= {("Chairman (chairman)", f"/agents/profile?id={mina['id']}")}
    request = by_action["approval.created"][0]
    assert request["actor"] == "Sumi" and request["tone"] == "warn" and request["source"] == "audit"
    assert request["link"] == f"/approvals?id={pending(api)[0]['id']}" and request["agent_id"] == sumi["id"]
    assert by_action["settings.setup_completed"][0]["link"] == "/settings"
    # the Central Manager's delegation is one event (the delegated task), not also a tool line
    assert "tool.allowed" not in by_action

    # from the tasks themselves
    texts = [event["text"] for event in by_action["task.created"]]
    assert f"Request #1 “{EXAM_REQUEST}” was sent to the Central Manager." in texts
    assert f"Task #2 “{EXAM_REQUEST}” was delegated to Mina." in texts
    sent = next(event for event in by_action["task.created"] if event["task_id"] == 1)
    assert (sent["actor"], sent["link"], sent["source"], sent["tone"]) == ("Chairman (chairman)", "/tasks?id=1", "task", "info")
    delegated = next(event for event in by_action["task.created"] if event["task_id"] == 2)
    assert delegated["actor"] == "Central Manager"  # the agent that handed it on
    done = {event["task_id"]: event for event in by_action["task.succeeded"]}
    assert set(done) == {1, 2} and done[2]["actor"] == "Mina" and done[2]["tone"] == "good"
    assert done[2]["text"] == f"Task #2 “{EXAM_REQUEST}” succeeded."
    assert "task.failed" not in by_action and child["id"] not in done  # the waiting task has not finished

    ok(api.post(f"/api/approvals/{pending(api)[0]['id']}/reject"))
    drain()
    later = feed(api, 100)
    failed = [event for event in later if event["action"] == "task.failed"]
    assert {event["task_id"] for event in failed} == {result["id"], child["id"]} and failed[0]["tone"] == "bad"
    rejected = next(event for event in later if event["action"] == "approval.rejected")
    assert rejected["actor"] == "Chairman (chairman)" and rejected["tone"] == "bad"

    # limit
    assert [event["id"] for event in feed(api, 3)] == [event["id"] for event in later[:3]]
    assert len(feed(api)) == min(20, len(later))
    for bad in ("0", "101", "x"):
        assert api.get(f"/api/activity/recent?limit={bad}").status_code == 422


def test_activity_feed_shows_tool_refusals_but_not_health_checks(api: TestClient) -> None:  # noqa: F811
    support_agent(api, allowed_tools=["product.read"])  # may not send messages
    ask(api)
    now = "2026-01-01 00:00:00"
    sql(
        "INSERT INTO task (title, description, created_by, depth, kind, priority, input, status, created_at, updated_at, completed_at) "
        "VALUES ('Agent health check', '', 'schedule:health_check', 0, 'health_check', 'high', '{}', 'SUCCEEDED', ?, ?, ?)",
        now, now, now,
    )
    events = feed(api, 100)
    denied = next(event for event in events if event["action"] == "tool.denied")
    assert denied["actor"] == "Sumi" and denied["tone"] == "bad" and denied["link"] == f"/tasks?id={denied['task_id']}"
    assert not [event for event in events if "health check" in event["text"].lower()]


def test_activity_feed_has_no_secrets(client: TestClient) -> None:
    do_setup(client, anthropic_api_key=API_KEY, ai_mode="anthropic")
    token = client.cookies.get("village_session")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "my-other-secret-password", "password": "wrong-password-1"})
    assert client.post("/api/auth/login", json={"username": "chairman", "password": PASSWORD}).status_code == 200
    key_like = "sk-ant-api03-ANOTHERKEY_abcdefghijklmnopqrstuvwxyz"
    ok(client.post("/api/tasks", json={"title": f"remember the key {key_like} for me", "description": PASSWORD}), 201)
    served = json.dumps(feed(client, 100))
    assert "Request #1" in served and "[redacted]" in served  # the task is listed, the key-like text is masked
    for secret in (PASSWORD, API_KEY, key_like, "wrong-password-1", "my-other-secret-password", token, client.cookies.get("village_session")):
        assert secret and secret not in served
    assert {event["action"] for event in feed(client, 100)} >= {"settings.setup_completed", "auth.logout", "auth.login_failed", "auth.login", "task.created"}


def test_activity_needs_a_session(api: TestClient) -> None:  # noqa: F811
    make_agent(api)
    assert {route for route in api_routes(api.app) if route[1].startswith("/api/activity")} == {("GET", "/api/activity/recent")}
    with TestClient(api.app, base_url=BASE_URL) as stranger:
        for path in ("/api/activity/recent", "/api/stats/overview"):
            response = stranger.get(path)
            assert response.status_code == 401 and response.json() == {"detail": "Not authenticated"}
    assert make_upazila  # (imported helper)

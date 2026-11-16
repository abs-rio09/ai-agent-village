"""M4 Part C: memory scopes (and the temporary task context), schedules and the scheduler."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from fastapi.testclient import TestClient

from app import memory, scheduler
from app.config import get_settings
from app.db import get_session_factory, utcnow
from app.dbcheck import alembic_config, check
from app.models import Agent, Memory, Schedule, Task
from app.providers import DEMO_RECALL_PHRASE, DEMO_REMEMBER_PHRASE, ToolRequest
from app.task_runner import drain, run_once
from tests.conftest import BASE_URL
from tests.test_m2_org import api, make_upazila, ok  # noqa: F401  (api is a fixture)
from tests.test_m3_agents import central_manager, make_agent, rows, study_office
from tests.test_m3_tasks import agent_in, detail, send
from tests.test_m4_approvals import ask, pending, support_agent
from tests.test_m4_tools import ScriptedProvider, audit_rows, scripted, scripted_agent, use_tool  # noqa: F401
from tests.test_part_b_auth import api_routes, do_setup

ALL_MEMORY = ["read_village_memory", "read_upazila_memory", "write_agent_memory", "write_upazila_memory", "write_village_memory"]
MEMORY_TOOLS = ["memory.read", "memory.write"]


def add_memory(api: TestClient, scope: str, title: str, content: str = "x", **owner: Any) -> dict[str, Any]:  # noqa: F811
    return ok(api.post("/api/memory", json={"scope": scope, "title": title, "content": content, **owner}), 201)


def read(who: int, /, **args: Any) -> Any:
    return use_tool(who, "memory.read", args)


def titles(outcome: Any) -> list[str]:
    return sorted(entry["title"] for entry in outcome.data["entries"])


# ---------------------------------------------------------------- migration 0009


def test_0009_up_and_down_keeps_tasks_and_their_messages(env: Path) -> None:
    config = alembic_config()
    command.upgrade(config, "0008")
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for parent in (None, 1):
            connection.execute(
                "INSERT INTO task (title, description, created_by, assigned_agent_id, parent_task_id, depth, priority, input, status, created_at, updated_at) "
                "VALUES ('t', '', 'chairman', 1, ?, ?, 'normal', '{}', 'SUCCEEDED', ?, ?)",
                (parent, 0 if parent is None else 1, now, now),
            )
        connection.execute(
            "INSERT INTO agent_message (sender_agent_id, receiver_agent_id, task_id, type, payload, created_at) VALUES (1, 1, 2, 'delegation', '{}', ?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO approval (agent_id, task_id, tool_key, args, action, reason, expected_changes, risk_info, status, created_at, continuation) "
            "VALUES (1, 2, 'money.spend', '{}', 'a', 'r', 'e', 'k', 'REJECTED', ?, '[]')",
            (now,),
        )

    def tables() -> set[str]:
        return {row[0] for row in rows("SELECT name FROM sqlite_master WHERE type = 'table'")}

    new_tables = {"memory", "task_context", "schedule", "schedule_run", "apscheduler_jobs"}
    command.upgrade(config, "0009")
    assert check()["current"] == "0009" and rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("9",)]
    assert new_tables <= tables()
    assert rows("SELECT id, kind FROM task ORDER BY id") == [(1, "request"), (2, "delegated")]
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute(
            "INSERT INTO task (title, description, created_by, depth, kind, priority, input, status, created_at, updated_at) "
            "VALUES ('Agent health check', '', 'schedule:health_check', 0, 'health_check', 'high', '{}', 'QUEUED', ?, ?)",
            (now, now),
        )
        for bad in (
            "INSERT INTO memory (scope, title, content, contains_customer_data, created_by, updated_by, created_at, updated_at) VALUES ('VILLAGE', 't', 'c', 1, 'x', 'x', '2026', '2026')",
            "INSERT INTO memory (scope, agent_id, title, content, contains_customer_data, created_by, updated_by, created_at, updated_at) VALUES ('VILLAGE', 1, 't', 'c', 0, 'x', 'x', '2026', '2026')",
            "INSERT INTO memory (scope, title, content, contains_customer_data, created_by, updated_by, created_at, updated_at) VALUES ('AGENT', 't', 'c', 0, 'x', 'x', '2026', '2026')",
            "INSERT INTO memory (scope, title, content, contains_customer_data, created_by, updated_by, created_at, updated_at) VALUES ('TEAM', 't', 'c', 0, 'x', 'x', '2026', '2026')",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(bad)

    command.downgrade(config, "0008")
    assert not new_tables & tables() and rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("8",)]
    assert "kind" not in {row[1] for row in rows("PRAGMA table_info(task)")}
    # dropping the column did not rebuild the table: the tasks' messages and approvals are still there
    assert rows("SELECT COUNT(*) FROM task") == [(3,)]
    assert rows("SELECT COUNT(*) FROM agent_message") == [(1,)] and rows("SELECT COUNT(*) FROM approval") == [(1,)]
    assert rows("SELECT status FROM task WHERE title = 'Agent health check'") == [("CANCELLED",)]  # nobody could run it now
    assert {row[0] for row in rows("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'task'")} >= {"ix_task_status"}

    command.upgrade(config, "head")
    assert rows("SELECT id, kind FROM task ORDER BY id") == [(1, "request"), (2, "delegated"), (3, "request")]


# ---------------------------------------------------------------- memory: scope rules for agents


@pytest.fixture
def village(api: TestClient) -> dict[str, Any]:  # noqa: F811
    """Two Upazilas with an agent each (all memory tools, no memory permission yet), one agent in
    Central Administration, and one memory in every scope and for every owner."""
    study_ward = study_office(api)
    business = make_upazila(api, "Business Upazila", template_key="business")
    study_id = next(item["id"] for item in ok(api.get("/api/upazilas")) if item["template_key"] == "study")
    mina = make_agent(api, name="Mina", office_id=study_ward["office"]["id"], allowed_tools=MEMORY_TOOLS, permissions=[])
    tara = make_agent(api, key="teacher_tutor", name="Tara", office_id=study_ward["office"]["id"], allowed_tools=MEMORY_TOOLS, permissions=ALL_MEMORY)
    sumi = agent_in(api, business, "customer_support", "Sumi")
    sumi = ok(api.patch(f"/api/agents/{sumi['id']}", json={"allowed_tools": MEMORY_TOOLS, "permissions": ALL_MEMORY}))
    manager = central_manager(api)
    add_memory(api, "VILLAGE", "village rule")
    add_memory(api, "UPAZILA", "study plan", upazila_id=study_id)
    add_memory(api, "UPAZILA", "price list", upazila_id=business["id"])
    add_memory(api, "AGENT", "mina note", agent_id=mina["id"])
    add_memory(api, "AGENT", "tara note", agent_id=tara["id"])
    add_memory(api, "AGENT", "sumi note", agent_id=sumi["id"])
    return {"mina": mina, "tara": tara, "sumi": sumi, "manager": manager, "study_id": study_id, "business_id": business["id"]}


def test_agent_reads_only_what_its_permissions_and_its_place_allow(api: TestClient, village: dict[str, Any]) -> None:  # noqa: F811
    mina, tara, sumi = village["mina"]["id"], village["tara"]["id"], village["sumi"]["id"]

    # no permission at all: its own notes, nothing else
    assert titles(read(mina)) == ["mina note"]
    assert titles(read(mina, scope="agent")) == ["mina note"]
    for scope, permission in (("village", "Read village memory"), ("upazila", "Read Upazila memory")):
        refused = read(mina, scope=scope)
        assert refused.status == "denied" and refused.summary == f"'Mina' does not have the permission '{permission}'."
    assert [row["decision"] for row in audit_rows("agent_name = 'Mina' AND tool_key = 'memory.read'")] == ["allowed", "allowed", "denied", "denied"]

    # every permission: village, its OWN Upazila, its OWN notes — never another Upazila or another agent
    assert titles(read(tara)) == ["study plan", "tara note", "village rule"]
    assert titles(read(tara, scope="village")) == ["village rule"]
    assert titles(read(tara, scope="upazila")) == ["study plan"]
    assert titles(read(tara, scope="agent")) == ["tara note"]
    assert titles(read(sumi)) == ["price list", "sumi note", "village rule"]
    assert titles(read(sumi, scope="upazila")) == ["price list"]
    assert titles(read(tara, query="price")) == [] and titles(read(tara, query="PLAN")) == ["study plan"]

    # one permission at a time
    ok(api.patch(f"/api/agents/{mina}", json={"permissions": ["read_village_memory"]}))
    assert titles(read(mina)) == ["mina note", "village rule"] and read(mina, scope="upazila").status == "denied"
    ok(api.patch(f"/api/agents/{mina}", json={"permissions": ["read_upazila_memory"]}))
    assert titles(read(mina)) == ["mina note", "study plan"] and read(mina, scope="village").status == "denied"

    # there is no way to name another owner
    for extra in ({"agent_id": tara}, {"upazila_id": village["business_id"]}, {"scope": "everything"}):
        assert read(mina, **extra).status == "error"


def test_central_agent_has_no_upazila_memory(api: TestClient, village: dict[str, Any]) -> None:  # noqa: F811
    manager = village["manager"]["id"]
    ok(api.patch(f"/api/agents/{manager}", json={"permissions": [*village["manager"]["permissions"], "read_upazila_memory", "write_upazila_memory"]}))
    assert titles(read(manager)) == ["village rule"]  # the village's, nobody's Upazila
    refused = read(manager, scope="upazila")
    assert refused.status == "denied" and "does not work in an Upazila" in refused.summary
    assert use_tool(manager, "memory.write", {"scope": "upazila", "title": "t", "content": "c"}).status == "denied"


def test_agent_writes_only_where_it_is_permitted(api: TestClient, village: dict[str, Any]) -> None:  # noqa: F811
    mina, tara, sumi = village["mina"]["id"], village["tara"]["id"], village["sumi"]["id"]

    def write(who: int, scope: str, title: str = "new", /, **extra: Any) -> Any:
        return use_tool(who, "memory.write", {"scope": scope, "title": title, "content": "something to keep", **extra})

    # no permission: every scope is refused, nothing is stored
    for scope, permission in (("agent", "Keep its own notes"), ("upazila", "Write Upazila memory"), ("village", "Write village memory")):
        refused = write(mina, scope)
        assert refused.status == "denied" and refused.summary == f"'Mina' does not have the permission '{permission}'."
    assert rows("SELECT COUNT(*) FROM memory") == [(6,)]
    assert [row["decision"] for row in audit_rows("agent_name = 'Mina' AND tool_key = 'memory.write'")] == ["denied"] * 3

    # each permission opens exactly its scope
    ok(api.patch(f"/api/agents/{mina}", json={"permissions": ["write_agent_memory"]}))
    saved = write(mina, "agent", "exam date")
    assert saved.ok and saved.summary.startswith("Saved 'exam date' to agent memory (entry #")
    assert write(mina, "upazila").status == "denied" and write(mina, "village").status == "denied"
    assert rows("SELECT scope, agent_id, upazila_id, created_by FROM memory WHERE title = 'exam date'") == [("AGENT", mina, None, f"agent:{mina}")]

    assert write(tara, "upazila", "tara for study").ok and write(sumi, "upazila", "sumi for business").ok
    assert write(tara, "village", "tara for all").ok
    assert rows("SELECT upazila_id FROM memory WHERE title = 'tara for study'") == [(village["study_id"],)]  # always its OWN Upazila
    assert rows("SELECT upazila_id FROM memory WHERE title = 'sumi for business'") == [(village["business_id"],)]
    assert "sumi for business" not in titles(read(tara)) and "tara for study" not in titles(read(sumi))
    assert "tara for all" in titles(read(sumi)) and "exam date" not in titles(read(tara))

    # an agent cannot write into another agent's notes or another Upazila: there is no such argument
    for extra in ({"agent_id": tara}, {"upazila_id": village["business_id"]}):
        assert write(mina, "agent", **extra).status == "error"
    for bad in ({"scope": "agent", "title": "", "content": "c"}, {"scope": "agent", "title": "t"}, {"scope": "shared", "title": "t", "content": "c"}, {"title": "t", "content": "c"}):
        assert use_tool(mina, "memory.write", bad).status == "error"


def test_customer_data_never_goes_into_village_memory(api: TestClient, village: dict[str, Any]) -> None:  # noqa: F811
    tara = village["tara"]["id"]
    before = rows("SELECT COUNT(*) FROM memory WHERE scope = 'VILLAGE'")
    refusals = (
        {"content": "Rahim, call 01712-345678", "title": "customer"},
        {"content": "write to rahim.customer@example.com", "title": "customer"},
        {"content": "prefers evening delivery", "title": "customer", "contains_customer_data": True},
        {"content": "nothing private", "title": "+880 1712 345678"},
    )
    for args in refusals:
        refused = use_tool(tara, "memory.write", {"scope": "village", **args})
        assert refused.status == "error" and "Customer data cannot be stored in Village memory" in refused.summary, args
        response = api.post("/api/memory", json={"scope": "VILLAGE", **args})  # the Chairman is bound by it too
        assert response.status_code == 422 and "Customer data cannot be stored in Village memory" in response.text
    assert rows("SELECT COUNT(*) FROM memory WHERE scope = 'VILLAGE'") == before

    # the same text is fine in the Upazila's or the agent's own memory, and is marked there
    for scope in ("upazila", "agent"):
        saved = use_tool(tara, "memory.write", {"scope": scope, "title": "customer", "content": "Rahim, call 01712-345678"})
        assert saved.ok and saved.summary.endswith("It is marked as customer data.")
    assert rows("SELECT scope, contains_customer_data FROM memory WHERE title = 'customer' ORDER BY scope") == [("AGENT", 1), ("UPAZILA", 1)]
    # ordinary numbers are not mistaken for phone numbers
    assert use_tool(tara, "memory.write", {"scope": "village", "title": "exam", "content": "Exam on 2026-11-20 in room 204, 25 questions"}).ok
    assert not memory.looks_like_customer_data("Order 12345, 3 pieces, 1500 BDT", "version 3.14.1")
    assert memory.looks_like_customer_data("017 1234 5678") and memory.looks_like_customer_data("a@b.co")

    # editing cannot smuggle it in either
    entry = add_memory(api, "VILLAGE", "office hours", "9 to 5")
    for patch in ({"content": "ask 01712-345678"}, {"contains_customer_data": True}):
        response = api.patch(f"/api/memory/{entry['id']}", json=patch)
        assert response.status_code == 422 and "Customer data cannot be stored" in response.text
    assert ok(api.get(f"/api/memory/{entry['id']}"))["content"] == "9 to 5"


def test_demo_phrases_write_and_read_the_agents_own_notes(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)  # the template's defaults: memory tools + "Keep its own notes"
    assert set(MEMORY_TOOLS) <= set(mina["allowed_tools"]) and "write_agent_memory" in mina["permissions"]
    task = send(api, DEMO_REMEMBER_PHRASE)
    drain()
    child = detail(api, task["id"])["children"][0]
    assert child["status"] == "SUCCEEDED"
    assert "[Tool] Write memory: Saved 'my exam is on Friday' to agent memory (entry #1)." in child["output"]
    assert rows("SELECT scope, agent_id, title, content FROM memory") == [("AGENT", mina["id"], "my exam is on Friday", "my exam is on Friday")]

    task = send(api, DEMO_RECALL_PHRASE)
    drain()
    child = detail(api, task["id"])["children"][0]
    assert child["status"] == "SUCCEEDED"
    assert "[Tool] Read memory: Found 1 memory entry (agent + upazila): [agent] my exam is on Friday: my exam is on Friday" in child["output"]

    # without the tool the same request is refused — and that is in the audit log
    ok(api.patch(f"/api/agents/{mina['id']}", json={"allowed_tools": ["document.read"]}))
    task = send(api, DEMO_REMEMBER_PHRASE)
    drain()
    child = detail(api, task["id"])["children"][0]
    assert child["status"] == "FAILED" and child["error"] == "Tool call refused. The tool 'Write memory' is not assigned to 'Mina'."
    assert rows("SELECT COUNT(*) FROM memory") == [(1,)]


# ---------------------------------------------------------------- temporary task context


def test_task_context_lives_only_as_long_as_the_task(api: TestClient, scripted: ScriptedProvider) -> None:  # noqa: F811
    sumi = support_agent(api, allowed_tools=[*MEMORY_TOOLS, "message.send_external"], provider="scripted")
    scripted.script["Sumi"] = [
        ToolRequest("memory.write", {"scope": "task", "title": "order", "content": "order 12, two shirts"}),
        ToolRequest("memory.write", {"scope": "task", "title": "order", "content": "order 12, three shirts"}),  # same key: replaced
        ToolRequest("memory.write", {"scope": "task", "title": "customer", "content": "Rahim 01712-345678"}),
        ToolRequest("memory.read", {"scope": "task"}),
        ToolRequest("message.send_external", {"recipient": "Rahim", "body": "Your order is ready."}),
    ]
    result, child = ask(api)
    assert child["status"] == "WAITING_APPROVAL"
    assert "[Tool] Read memory: This task has 2 context note(s)." in child["output"]
    # while the task is open (here: waiting for the Chairman) its context is kept …
    assert rows("SELECT task_id, agent_id, key, value FROM task_context ORDER BY id") == [
        (child["id"], sumi["id"], "order", "order 12, three shirts"),
        (child["id"], sumi["id"], "customer", "Rahim 01712-345678"),
    ]
    assert rows("SELECT COUNT(*) FROM memory") == [(0,)]  # … and it never becomes a memory
    ok(api.post(f"/api/approvals/{pending(api)[0]['id']}/approve"))
    drain()
    assert detail(api, child["id"])["status"] == "SUCCEEDED" and detail(api, result["id"])["status"] == "SUCCEEDED"
    assert rows("SELECT COUNT(*) FROM task_context") == [(0,)]  # the task finished: the context is gone

    # the same when the task fails or is cancelled
    for ending in ("reject", "cancel"):
        result, child = ask(api)
        assert rows("SELECT COUNT(*) FROM task_context") == [(2,)]
        if ending == "reject":
            ok(api.post(f"/api/approvals/{pending(api)[0]['id']}/reject"))
        else:
            ok(api.post(f"/api/tasks/{result['id']}/cancel"))
        assert detail(api, child["id"])["status"] in ("FAILED", "CANCELLED")
        assert rows("SELECT COUNT(*) FROM task_context") == [(0,)], ending

    # an agent only reaches the context of its own task
    other = agent_in(api, ok(api.get("/api/upazilas"))[0], "pion_helper", "Babu")
    ok(api.patch(f"/api/agents/{other['id']}", json={"allowed_tools": MEMORY_TOOLS}))
    _result, open_child = ask(api)
    foreign = use_tool(other["id"], "memory.write", {"scope": "task", "title": "x", "content": "y"}, open_child["id"])
    assert foreign.status == "denied" and "its own task" in foreign.summary
    assert use_tool(other["id"], "memory.write", {"scope": "task", "title": "x", "content": "y"}).status == "error"  # no task at all


# ---------------------------------------------------------------- memory API (the Chairman)


def test_memory_api_lists_by_scope_edits_and_deletes(api: TestClient, village: dict[str, Any]) -> None:  # noqa: F811
    everything = ok(api.get("/api/memory"))
    assert len(everything) == 6 and [item["id"] for item in everything] == sorted((item["id"] for item in everything), reverse=True)
    assert [item["title"] for item in ok(api.get("/api/memory?scope=VILLAGE"))] == ["village rule"]
    upazila = ok(api.get("/api/memory?scope=UPAZILA"))
    assert {(item["title"], item["upazila_name"]) for item in upazila} == {("study plan", "Study Upazila"), ("price list", "Business Upazila")}
    assert [item["title"] for item in ok(api.get(f"/api/memory?scope=UPAZILA&upazila_id={village['business_id']}"))] == ["price list"]
    agent = ok(api.get(f"/api/memory?scope=AGENT&agent_id={village['mina']['id']}"))
    assert [(item["title"], item["agent_name"], item["created_by"]) for item in agent] == [("mina note", "Mina", "chairman:chairman")]
    assert [item["title"] for item in ok(api.get("/api/memory?q=PLAN"))] == ["study plan"]

    entry = agent[0]
    assert ok(api.get(f"/api/memory/{entry['id']}")) == entry
    edited = ok(api.patch(f"/api/memory/{entry['id']}", json={"title": "mina's note", "content": "call 01712-345678"}))
    assert edited["title"] == "mina's note" and edited["contains_customer_data"] is True  # recognised, and allowed in AGENT scope
    assert edited["scope"] == "AGENT" and edited["agent_id"] == village["mina"]["id"]  # scope and owner cannot be changed
    assert api.patch(f"/api/memory/{entry['id']}", json={"scope": "VILLAGE"}).status_code == 422
    ok(api.patch(f"/api/memory/{entry['id']}", json={"title": "mina's note"}))  # nothing changed: no audit entry
    assert ok(api.request("DELETE", f"/api/memory/{entry['id']}")) == {"deleted": True}
    assert api.get(f"/api/memory/{entry['id']}").status_code == 404
    assert api.request("DELETE", f"/api/memory/{entry['id']}").status_code == 404

    events = audit_rows("action LIKE 'memory.%' AND id > (SELECT MAX(id) FROM audit_log WHERE action = 'memory.created')")
    assert [(row["action"], row["actor"]) for row in events] == [("memory.updated", "chairman:chairman"), ("memory.deleted", "chairman:chairman")]
    assert events[0]["summary"] == f"Edited 'mina's note' in the notes of agent #{village['mina']['id']} (title, content, contains_customer_data)."
    assert events[1]["agent_name"] == "Mina"
    assert "01712" not in str(audit_rows("action LIKE 'memory.%'"))  # the content is never copied into the audit log

    # validation
    for body, code in (
        ({"scope": "UPAZILA", "title": "t", "content": "c"}, 422),
        ({"scope": "AGENT", "title": "t", "content": "c"}, 422),
        ({"scope": "UPAZILA", "title": "t", "content": "c", "upazila_id": 999}, 404),
        ({"scope": "AGENT", "title": "t", "content": "c", "agent_id": 999}, 404),
        ({"scope": "VILLAGE", "title": "", "content": "c"}, 422),
        ({"scope": "VILLAGE", "title": "t", "content": "c" * 4001}, 422),
        ({"scope": "TEAM", "title": "t", "content": "c"}, 422),
    ):
        assert api.post("/api/memory", json=body).status_code == code, body
    # a VILLAGE memory never gets an owner, whatever is sent
    odd = add_memory(api, "VILLAGE", "no owner", upazila_id=village["study_id"], agent_id=village["mina"]["id"])
    assert odd["upazila_id"] is None and odd["agent_id"] is None


def test_memory_follows_its_owner(api: TestClient, village: dict[str, Any]) -> None:  # noqa: F811
    study = next(item for item in ok(api.get("/api/upazilas")) if item["id"] == village["study_id"])
    ok(api.request("DELETE", f"/api/upazilas/{study['id']}", json={"confirm_name": study["name"]}))
    assert [item["title"] for item in ok(api.get("/api/memory?scope=UPAZILA"))] == ["price list"]  # the Upazila's memory went with it
    assert len(ok(api.get("/api/memory?scope=AGENT"))) == 3  # its agents (now disabled) keep their notes


MEMORY_ROUTES = {
    ("GET", "/api/memory"),
    ("POST", "/api/memory"),
    ("GET", "/api/memory/{memory_id}"),
    ("PATCH", "/api/memory/{memory_id}"),
    ("DELETE", "/api/memory/{memory_id}"),
}
SCHEDULE_ROUTES = {
    ("GET", "/api/schedules"),
    ("POST", "/api/schedules"),
    ("POST", "/api/schedules/{schedule_id}/pause"),
    ("POST", "/api/schedules/{schedule_id}/resume"),
    ("DELETE", "/api/schedules/{schedule_id}"),
}


def test_memory_and_schedule_routes_need_a_session(api: TestClient, village: dict[str, Any]) -> None:  # noqa: F811
    routes = api_routes(api.app)
    assert {route for route in routes if route[1].startswith("/api/memory")} == MEMORY_ROUTES
    assert {route for route in routes if route[1].startswith("/api/schedules")} == SCHEDULE_ROUTES
    with TestClient(api.app, base_url=BASE_URL) as stranger:
        for method, path in sorted(MEMORY_ROUTES | SCHEDULE_ROUTES):
            response = stranger.request(method, path.replace("{memory_id}", "1").replace("{schedule_id}", "1"))
            assert response.status_code == 401, (method, path)
            assert "village rule" not in response.text
    assert rows("SELECT COUNT(*) FROM memory") == [(6,)]


# ---------------------------------------------------------------- schedules


def schedules(api: TestClient) -> dict[str, dict[str, Any]]:  # noqa: F811
    return {item["name"]: item for item in ok(api.get("/api/schedules"))["schedules"]}


def new_schedule(api: TestClient, agent_id: int, text: str = "Summarise today's study progress", **trigger: Any) -> dict[str, Any]:  # noqa: F811
    body = {"agent_id": agent_id, "request_text": text, **(trigger or {"trigger_type": "interval", "interval_minutes": 1})}
    return ok(api.post("/api/schedules", json=body), 201)


def test_builtin_schedules_exist_and_cannot_be_deleted(api: TestClient) -> None:  # noqa: F811
    page = ok(api.get("/api/schedules"))
    assert page["scheduler_running"] is False and page["timezone"] == "Asia/Dhaka"  # (the thread is off in tests)
    listed = {item["name"]: item for item in page["schedules"]}
    assert set(listed) == {"Agent health check", "Daily report"}
    health, daily = listed["Agent health check"], listed["Daily report"]
    assert (health["kind"], health["builtin_key"], health["trigger_text"], health["agent"]) == ("builtin", "health_check", "every 10 minutes", None)
    assert (daily["kind"], daily["builtin_key"], daily["trigger_text"], daily["daily_time"]) == ("builtin", "daily_report", "every day at 21:00", "21:00")
    assert health["paused"] is False and health["last_run_at"] is None and health["next_run_at"] is None
    ok(api.get("/api/schedules"))
    assert rows("SELECT COUNT(*) FROM schedule") == [(2,)]  # listing twice does not add them twice
    response = api.request("DELETE", f"/api/schedules/{health['id']}")
    assert response.status_code == 409 and "Pause it instead" in response.text
    assert ok(api.post(f"/api/schedules/{health['id']}/pause"))["paused"] is True
    assert ok(api.post(f"/api/schedules/{health['id']}/resume"))["paused"] is False


def test_schedule_validation(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    manager = central_manager(api)
    base = {"agent_id": mina["id"], "request_text": "x"}
    for extra in (
        {"trigger_type": "interval"},
        {"trigger_type": "interval", "interval_minutes": 0},
        {"trigger_type": "interval", "interval_minutes": 10081},
        {"trigger_type": "daily"},
        {"trigger_type": "daily", "daily_time": "24:00"},
        {"trigger_type": "daily", "daily_time": "9:30"},
        {"trigger_type": "weekly", "interval_minutes": 5},
        {"trigger_type": "interval", "interval_minutes": 5, "command": "rm -rf /"},
    ):
        assert api.post("/api/schedules", json={**base, **extra}).status_code == 422, extra
    assert api.post("/api/schedules", json={"agent_id": mina["id"], "request_text": " ", "trigger_type": "interval", "interval_minutes": 5}).status_code == 422
    assert api.post("/api/schedules", json={**base, "agent_id": 999, "trigger_type": "interval", "interval_minutes": 5}).status_code == 404
    response = api.post("/api/schedules", json={**base, "agent_id": manager["id"], "trigger_type": "interval", "interval_minutes": 5})
    assert response.status_code == 409 and "only routes requests" in response.text
    created = new_schedule(api, mina["id"], "Plan tomorrow\nwith breaks", trigger_type="daily", daily_time="07:30")
    assert (created["name"], created["trigger_text"], created["interval_minutes"]) == ("Plan tomorrow", "every day at 07:30", None)
    assert created["agent"]["display_name"] == "Mina" and created["kind"] == "custom"
    hourly = new_schedule(api, mina["id"], trigger_type="interval", interval_minutes=120, name="Two-hourly")
    assert (hourly["name"], hourly["trigger_text"]) == ("Two-hourly", "every 2 hours")
    for action in ("pause", "resume"):
        assert api.post(f"/api/schedules/999/{action}").status_code == 404
    assert api.request("DELETE", "/api/schedules/999").status_code == 404


def test_one_run_creates_exactly_one_task_and_the_runner_does_the_work(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    schedule = new_schedule(api, mina["id"], "Summarise today's study progress\nshort please")
    anchor = datetime.fromisoformat(rows("SELECT anchor_at FROM schedule WHERE id = ?", schedule["id"])[0][0])
    first = anchor + timedelta(minutes=1, seconds=2)  # the first run, fired two seconds late

    task_id = scheduler.run_schedule(schedule["id"], now=first)
    assert task_id is not None
    # the same run fires again (a second thread, a restart before the job store was updated …): nothing
    assert scheduler.run_schedule(schedule["id"], now=first) is None
    assert scheduler.run_schedule(schedule["id"], now=first + timedelta(seconds=20)) is None
    assert rows("SELECT COUNT(*) FROM task") == [(1,)]
    assert rows("SELECT run_key, task_id FROM schedule_run") == [(f"{schedule['id']}:{anchor + timedelta(minutes=1):%Y-%m-%dT%H:%M:%S}", task_id)]

    # the job only created the task; nothing has run yet
    task = detail(api, task_id)
    assert (task["status"], task["kind"], task["created_by"], task["parent_task_id"]) == ("ASSIGNED", "scheduled", f"schedule:{schedule['id']}", None)
    assert (task["title"], task["description"]) == ("Summarise today's study progress", "short please")
    assert task["assigned_agent"]["id"] == mina["id"] and task["output"] is None
    drain()
    task = detail(api, task_id)
    assert task["status"] == "SUCCEEDED" and task["output"].startswith("[Demo] Mina (Study Assistant")
    assert task["children"] == []  # it went straight to its agent: the Central Manager did not route it

    # the next run is a new run: one more task, and only one
    second = anchor + timedelta(minutes=2)
    assert scheduler.run_schedule(schedule["id"], now=second) is not None
    assert scheduler.run_schedule(schedule["id"], now=second) is None
    assert rows("SELECT COUNT(*) FROM task") == [(2,)]
    listed = schedules(api)[schedule["name"]]
    assert listed["last_task_id"] and listed["last_task_status"] == "ASSIGNED" and listed["last_run_at"]

    # after downtime the missed runs are one run (coalesce), not one task per missed minute
    late = anchor + timedelta(hours=3, seconds=30)
    assert scheduler.run_schedule(schedule["id"], now=late) is not None
    assert scheduler.run_schedule(schedule["id"], now=late) is None
    assert rows("SELECT COUNT(*) FROM task") == [(3,)]


def test_parallel_firings_of_one_run_create_one_task(api: TestClient) -> None:  # noqa: F811
    from concurrent.futures import ThreadPoolExecutor

    mina = make_agent(api)
    schedule = new_schedule(api, mina["id"])
    moment = utcnow() + timedelta(minutes=5)
    with ThreadPoolExecutor(max_workers=8) as pool:
        created = [item for item in pool.map(lambda _i: scheduler.run_schedule(schedule["id"], now=moment), range(8)) if item is not None]
    assert len(created) == 1 and rows("SELECT COUNT(*) FROM task") == [(1,)] and rows("SELECT COUNT(*) FROM schedule_run") == [(1,)]


def test_paused_schedule_creates_nothing_and_resumes(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    schedule = new_schedule(api, mina["id"])
    now = utcnow()
    assert ok(api.post(f"/api/schedules/{schedule['id']}/pause"))["paused"] is True
    for minutes in (1, 2, 30):
        assert scheduler.run_schedule(schedule["id"], now=now + timedelta(minutes=minutes)) is None
    assert rows("SELECT COUNT(*) FROM task") == [(0,)] and rows("SELECT COUNT(*) FROM schedule_run") == [(0,)]
    assert schedules(api)[schedule["name"]]["next_run_at"] is None
    assert ok(api.post(f"/api/schedules/{schedule['id']}/resume"))["paused"] is False
    assert scheduler.run_schedule(schedule["id"], now=now + timedelta(minutes=31)) is not None
    assert rows("SELECT COUNT(*) FROM task") == [(1,)]
    assert [row["action"] for row in audit_rows("action LIKE 'schedule.%'")] == ["schedule.created", "schedule.paused", "schedule.resumed"]

    # deleting: no more tasks, the ones it created stay
    assert ok(api.request("DELETE", f"/api/schedules/{schedule['id']}")) == {"deleted": True}
    assert scheduler.run_schedule(schedule["id"], now=now + timedelta(minutes=40)) is None
    assert rows("SELECT COUNT(*) FROM task") == [(1,)] and rows("SELECT COUNT(*) FROM schedule_run") == [(0,)]
    assert audit_rows("action = 'schedule.deleted'")[0]["agent_name"] == "Mina"


def test_scheduled_task_for_a_paused_agent_fails_with_the_reason(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    schedule = new_schedule(api, mina["id"])
    ok(api.post(f"/api/agents/{mina['id']}/pause"))
    task_id = scheduler.run_schedule(schedule["id"], now=utcnow() + timedelta(minutes=1))
    drain()
    task = detail(api, task_id)
    assert task["status"] == "FAILED" and "is paused, so it did not receive this task" in task["error"]
    assert audit_rows("action = 'agent.work_denied'")[0]["task_id"] == task_id


def test_daily_schedule_runs_once_per_day_in_the_village_timezone(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    schedule = new_schedule(api, mina["id"], trigger_type="daily", daily_time="07:30")
    dhaka = ZoneInfo("Asia/Dhaka")

    def at(day: int, hour: int, minute: int) -> datetime:  # a Dhaka wall-clock time as naive UTC
        return datetime(2026, 11, day, hour, minute, tzinfo=dhaka).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    with get_session_factory()() as db:
        row = db.get(Schedule, schedule["id"])
        assert scheduler.scheduled_time(row, at(17, 7, 30), dhaka) == at(17, 7, 30)
        assert scheduler.scheduled_time(row, at(17, 23, 0), dhaka) == at(17, 7, 30)
        assert scheduler.scheduled_time(row, at(18, 7, 29), dhaka) == at(17, 7, 30)  # a very late firing still belongs to the 17th
        assert scheduler.next_run_time(row, at(17, 7, 30), dhaka) == at(18, 7, 30)
        assert scheduler.next_run_time(row, at(17, 6, 0), dhaka) == at(17, 7, 30)
    assert scheduler.run_schedule(schedule["id"], now=at(17, 7, 30)) is not None
    assert scheduler.run_schedule(schedule["id"], now=at(17, 9, 0)) is None
    assert scheduler.run_schedule(schedule["id"], now=at(18, 7, 31)) is not None
    assert rows("SELECT COUNT(*) FROM task") == [(2,)]
    assert rows("SELECT run_key FROM schedule_run ORDER BY id")[0] == (f"{schedule['id']}:2026-11-17T01:30:00",)  # 07:30 Dhaka = 01:30 UTC


# ---------------------------------------------------------------- built-in jobs


def builtin_id(api: TestClient, key: str) -> int:  # noqa: F811
    return next(item["id"] for item in ok(api.get("/api/schedules"))["schedules"] if item["builtin_key"] == key)


def make_running(task_id: int, minutes_ago: int) -> None:
    stamp = (utcnow() - timedelta(minutes=minutes_ago)).isoformat(sep=" ")
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("UPDATE task SET status = 'RUNNING', started_at = ?, updated_at = ?, completed_at = NULL, output = NULL WHERE id = ?", (stamp, stamp, task_id))
        connection.execute("UPDATE agent SET runtime_state = 'working' WHERE id = (SELECT assigned_agent_id FROM task WHERE id = ?)", (task_id,))


def test_health_check_fails_stuck_tasks_and_nothing_else(api: TestClient) -> None:  # noqa: F811
    mina = make_agent(api)
    support_agent(api)
    done = [send(api, "help me prepare for my exam") for _ in range(3)]
    drain()
    stuck_child, fresh_child, parent_with_open_child = (detail(api, task["id"])["children"][0]["id"] for task in done)
    make_running(stuck_child, 45)  # RUNNING for 45 minutes: stuck
    make_running(fresh_child, 5)  # RUNNING for 5 minutes: fine
    make_running(done[0]["id"], 300)  # its child is open (the stuck one): it is waiting, not stuck
    make_running(done[2]["id"], 300)
    make_running(parent_with_open_child, 300)  # a parent whose child is still open
    grandchild = send(api, "placeholder")  # becomes that open child
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("UPDATE task SET parent_task_id = ?, kind = 'delegated', status = 'ASSIGNED', assigned_agent_id = NULL WHERE id = ?", (parent_with_open_child, grandchild["id"]))
        connection.execute("UPDATE task SET status = 'CANCELLED' WHERE id = ?", (grandchild["id"],))
        connection.execute("UPDATE task SET status = 'QUEUED', assigned_agent_id = NULL, parent_task_id = ?, kind = 'delegated' WHERE id = ?", (parent_with_open_child, grandchild["id"]))
        connection.execute("UPDATE task SET status = 'WAITING_APPROVAL' WHERE id = ?", (grandchild["id"],))
    _result, waiting = ask(api)  # WAITING_APPROVAL since "long ago": never failed by the health check
    with sqlite3.connect(get_settings().db_file) as connection:
        old = (utcnow() - timedelta(days=3)).isoformat(sep=" ")
        connection.execute("UPDATE task SET updated_at = ?, started_at = ? WHERE id = ?", (old, old, waiting["id"]))

    job = builtin_id(api, "health_check")
    check_id = scheduler.run_schedule(job)
    assert check_id is not None
    assert scheduler.run_schedule(job, now=utcnow() + timedelta(minutes=10)) is None  # the previous check is still queued
    assert rows("SELECT status, kind, priority FROM task WHERE id = ?", check_id) == [("QUEUED", "health_check", "high")]
    assert detail(api, stuck_child)["status"] == "RUNNING"  # the job itself changed nothing: it only created a task
    assert run_once() is True  # high priority: the health check is the next step

    stuck = detail(api, stuck_child)
    assert stuck["status"] == "FAILED"
    assert stuck["error"] == "Marked as failed by the agent health check: RUNNING for more than 30 minutes without progress."
    assert detail(api, fresh_child)["status"] == "RUNNING"
    assert detail(api, parent_with_open_child)["status"] == "RUNNING"
    assert detail(api, waiting["id"])["status"] == "WAITING_APPROVAL"
    report = detail(api, check_id)
    assert report["status"] == "SUCCEEDED" and f"marked FAILED: #{stuck_child}." in report["output"]
    assert [(row["action"], row["task_id"], row["agent_name"]) for row in audit_rows("action = 'task.stuck_failed'")] == [("task.stuck_failed", stuck_child, "Mina")]
    assert mina["id"]
    # the failure is reported upwards like any other, and the parent finishes
    drain()
    assert detail(api, done[0]["id"])["status"] == "FAILED"
    # health checks do not fill the Task Center
    assert check_id not in [item["id"] for item in ok(api.get("/api/tasks?top_level=true"))]
    assert check_id in [item["id"] for item in ok(api.get("/api/tasks?top_level=true&system=true"))]

    # a second check finds nothing; and the limit is a setting
    second = scheduler.run_schedule(job, now=utcnow() + timedelta(minutes=10))
    drain()
    assert "None was stuck (limit: 30 minutes without progress)." in detail(api, second)["output"]


def test_stuck_limit_is_configurable(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    make_agent(api)
    task = send(api, "help me prepare for my exam")
    drain()
    child = detail(api, task["id"])["children"][0]["id"]
    make_running(child, 5)
    monkeypatch.setenv("VILLAGE_STUCK_TASK_MINUTES", "2")
    get_settings.cache_clear()
    scheduler.run_schedule(builtin_id(api, "health_check"))
    drain()
    assert "more than 2 minutes" in detail(api, child)["error"]
    assert rows("SELECT runtime_state FROM agent WHERE display_name = 'Mina'") == [("idle",)]


def test_daily_report_counts_the_day_from_the_database(api: TestClient) -> None:  # noqa: F811
    make_agent(api)
    support_agent(api)
    for title in ("help me prepare for my exam", "hello there", "send message to customer"):
        send(api, title)
    drain()
    job = builtin_id(api, "daily_report")
    now = utcnow()
    report_id = scheduler.run_schedule(job, now=now)
    assert scheduler.run_schedule(job, now=now) is None  # one report per day
    assert report_id is not None
    drain()
    report = detail(api, report_id)
    day = scheduler.scheduled_time(_row(job), now, ZoneInfo("Asia/Dhaka")).replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Dhaka")).date().isoformat()
    assert report["status"] == "SUCCEEDED" and report["kind"] == "daily_report" and report["title"] == f"Daily report {day}"
    assert report["assigned_agent"]["is_central_manager"] is True
    output = report["output"]
    assert output.startswith(f"Daily report for {day} (Asia/Dhaka)")
    assert output.endswith("Counted from the village's database. No AI model wrote this report.") and "[Demo]" not in output
    if day == datetime.now(ZoneInfo("Asia/Dhaka")).date().isoformat():  # (not in the hours before 21:00 Dhaka: then it is yesterday's report)
        assert "Requests and scheduled tasks created: 3" in output
        assert "  SUCCEEDED: 1" in output and "  FAILED: 1" in output and "  RUNNING: 1" in output
        assert "Delegated tasks created: 2" in output and "#2 hello there" in output.replace("#3", "#2").replace("#4", "#2")
    assert "Waiting for your approval right now: 1" in output
    assert "Agents: 3 active, 0 paused, 0 disabled" in output
    assert rows("SELECT runtime_state FROM agent WHERE is_central_manager = 1") == [("waiting",)]  # it still waits for the approval's task


def _row(schedule_id: int) -> Schedule:
    with get_session_factory()() as db:
        row = db.get(Schedule, schedule_id)
        assert row is not None
        db.expunge(row)
        return row


# ---------------------------------------------------------------- the real APScheduler


@pytest.fixture
def live(migrated: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Starts the application WITH its scheduler and task worker; restart() stops and starts it."""
    monkeypatch.setenv("VILLAGE_SCHEDULER", "1")
    monkeypatch.setenv("VILLAGE_TASK_WORKER", "1")
    get_settings.cache_clear()
    from app.main import create_app

    class Live:
        def __init__(self) -> None:
            self.client: TestClient | None = None
            self.cookies: dict[str, str] = {}

        def start(self) -> TestClient:
            self.client = TestClient(create_app(), base_url=BASE_URL, cookies=self.cookies)
            self.client.__enter__()
            return self.client

        def stop(self) -> None:
            if self.client is not None:
                self.cookies = dict(self.client.cookies)
                self.client.__exit__(None, None, None)
                self.client = None

        def restart(self) -> TestClient:
            self.stop()
            return self.start()

    app = Live()
    yield app
    app.stop()


def wait_until(condition: Any, seconds: float = 15.0) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("timed out")


def test_scheduler_runs_with_the_app_creates_tasks_and_survives_a_restart_without_duplicates(live: Any) -> None:
    client = live.start()
    do_setup(client)
    engine = scheduler.get_scheduler()
    assert engine.running and engine.timezone == "Asia/Dhaka"
    assert ok(client.get("/api/health"))["scheduler"] == "running" and ok(client.get("/api/health"))["scheduler_jobs"] == 2
    mina = make_agent(client)
    schedule = new_schedule(client, mina["id"], "Summarise today's study progress")
    job = scheduler.job_id(schedule["id"])
    assert engine.job_ids() == sorted([job, *[scheduler.job_id(item["id"]) for item in ok(client.get("/api/schedules"))["schedules"] if item["kind"] == "builtin"]])
    assert rows("SELECT COUNT(*) FROM apscheduler_jobs") == [(3,)]  # the jobs are stored in the same SQLite database
    listed = schedules(client)[schedule["name"]]
    assert listed["next_run_at"] and ok(client.get("/api/schedules"))["scheduler_running"] is True
    upcoming = datetime.fromisoformat(listed["next_run_at"]).replace(tzinfo=None)
    assert timedelta(0) < upcoming - utcnow() <= timedelta(minutes=1)  # a 1-minute schedule: due within the minute

    # the real APScheduler thread fires the job → one task → the worker thread runs it
    engine.run_now(schedule["id"])
    task_id = wait_until(lambda: rows("SELECT id FROM task WHERE kind = 'scheduled'"))[0][0]
    wait_until(lambda: rows("SELECT 1 FROM task WHERE id = ? AND status = 'SUCCEEDED'", task_id))
    assert rows("SELECT COUNT(*) FROM task WHERE kind = 'scheduled'") == [(1,)]
    runs_before = rows("SELECT run_key FROM schedule_run WHERE schedule_id = ?", schedule["id"])
    assert len(runs_before) == 1

    # pause: APScheduler has no next run for it, and a firing creates nothing
    ok(client.post(f"/api/schedules/{schedule['id']}/pause"))
    assert engine.job_next_run(schedule["id"]) is None and schedules(client)[schedule["name"]]["next_run_at"] is None
    ok(client.post(f"/api/schedules/{schedule['id']}/resume"))
    assert engine.job_next_run(schedule["id"]) is not None
    next_before = engine.job_next_run(schedule["id"])

    # restart: same jobs, same next run, no second task for a run that already happened
    client = live.restart()
    engine = scheduler.get_scheduler()
    assert engine.running and len(engine.job_ids()) == 3 and rows("SELECT COUNT(*) FROM apscheduler_jobs") == [(3,)]
    assert rows("SELECT COUNT(*) FROM schedule") == [(3,)]
    assert engine.job_next_run(schedule["id"]) == next_before  # the job was kept, not re-created
    time.sleep(1.2)
    assert rows("SELECT COUNT(*) FROM task WHERE kind = 'scheduled'") == [(1,)]
    assert rows("SELECT run_key FROM schedule_run WHERE schedule_id = ?", schedule["id"]) == runs_before
    assert scheduler.run_schedule(schedule["id"], now=datetime.fromisoformat(runs_before[0][0].split(":", 1)[1])) is None

    # a paused schedule stays paused across a restart; a deleted one loses its job
    ok(client.post(f"/api/schedules/{schedule['id']}/pause"))
    client = live.restart()
    engine = scheduler.get_scheduler()
    assert engine.job_next_run(schedule["id"]) is None and schedules(client)[schedule["name"]]["paused"] is True
    ok(client.request("DELETE", f"/api/schedules/{schedule['id']}"))
    assert job not in engine.job_ids() and rows("SELECT COUNT(*) FROM apscheduler_jobs") == [(2,)]
    live.stop()
    assert scheduler.get_scheduler().running is False


def test_scheduler_is_off_in_tests_and_not_started_without_its_tables(client: TestClient) -> None:
    assert scheduler.get_scheduler().running is False
    assert client.get("/api/health").json()["scheduler"] == "stopped"


def test_task_and_memory_models_have_no_stray_agent(api: TestClient) -> None:  # noqa: F811
    """An agent without history can be deleted; its notes and schedules go with it."""
    mina = make_agent(api)
    add_memory(api, "AGENT", "note", agent_id=mina["id"])
    new_schedule(api, mina["id"])
    ok(api.request("DELETE", f"/api/agents/{mina['id']}", json={"confirm_name": "Mina"}))
    with get_session_factory()() as db:
        assert db.get(Agent, mina["id"]) is None
        assert db.query(Memory).count() == 0 and db.query(Schedule).filter(Schedule.kind == "custom").count() == 0
        assert db.query(Task).count() == 0


# ---------------------------------------------------------------- ./village doctor


def test_doctor_has_a_scheduler_line(migrated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import schedcheck
    from tests.test_app01_remote import run_doctor

    monkeypatch.delenv("VILLAGE_SCHEDULER", raising=False)  # as on the owner's PC
    lines = [line for line in run_doctor(monkeypatch).splitlines() if "scheduler:" in line]
    assert len(lines) == 1
    assert lines[0].startswith("PASS  scheduler: APScheduler 3.") and "it starts with the Village" in lines[0]
    assert "the built-in schedules are added at the first start" in lines[0]

    off = [line for line in run_doctor(monkeypatch, VILLAGE_SCHEDULER="0").splitlines() if "scheduler:" in line]
    assert off == ["WARN  scheduler: switched off (VILLAGE_SCHEDULER=0) — no schedule will run"]

    # a database from before M4 Part C has no schedule tables
    command.downgrade(alembic_config(), "0008")
    get_settings.cache_clear()
    assert schedcheck.check() == ("FAIL", "scheduler: the database has no schedule tables (run ./village setup)")


def test_doctor_sees_the_running_scheduler(live: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import schedcheck

    live.start()
    health = {"scheduler": "running", "scheduler_jobs": 2}
    monkeypatch.setattr(schedcheck, "_health", lambda _url: health)
    assert schedcheck.check() == ("PASS", "scheduler: running inside the Village — 2 job(s), 2 schedule(s), 0 paused, timezone Asia/Dhaka")
    health["scheduler"] = "stopped"
    assert schedcheck.check() == ("FAIL", "scheduler: the Village is running but its scheduler is not (see ./village logs)")

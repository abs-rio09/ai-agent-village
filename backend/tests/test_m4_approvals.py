"""M4 Part B: approvals — a SENSITIVE tool call waits for the Chairman (docs/SPEC.md §8F)."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from alembic import command
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_session_factory
from app.dbcheck import alembic_config, check
from app.providers import DEMO_APPROVAL_PHRASE, ToolRequest
from app.task_runner import drain, recover_interrupted, run_once
from app.tools.builtin import NO_CONNECTOR
from tests.conftest import BASE_URL
from tests.test_m2_org import api, make_upazila, ok  # noqa: F401  (api is a fixture)
from tests.test_m3_agents import rows
from tests.test_m3_tasks import agent_in, detail, send
from tests.test_m4_tools import ScriptedProvider, audit_rows, scripted, scripted_agent  # noqa: F401  (scripted is a fixture)
from tests.test_part_b_auth import api_routes

SEND = ["message.send_external"]
MAY_SEND = ["send_external_messages"]


def support_agent(api: TestClient, name: str = "Sumi", **extra: Any) -> dict[str, Any]:  # noqa: F811
    """A Customer Support Agent in a Business Upazila that may ask to send external messages."""
    upazilas = [row for row in ok(api.get("/api/upazilas")) if row["template_key"] == "business"]
    upazila = upazilas[0] if upazilas else make_upazila(api, "Business Upazila", template_key="business")
    agent = agent_in(api, upazila, "customer_support", name)
    body = {"allowed_tools": [*agent["allowed_tools"], *SEND], "permissions": [*agent["permissions"], *MAY_SEND], **extra}
    return ok(api.patch(f"/api/agents/{agent['id']}", json=body))


def ask(api: TestClient, title: str = DEMO_APPROVAL_PHRASE) -> tuple[dict[str, Any], dict[str, Any]]:  # noqa: F811
    """Send the request and run the queue: (the Chairman's task, the agent's child task)."""
    task = send(api, title)
    drain()
    result = detail(api, task["id"])
    return result, result["children"][0]


def pending(api: TestClient) -> list[dict[str, Any]]:  # noqa: F811
    return ok(api.get("/api/approvals?status=PENDING"))


# ---------------------------------------------------------------- migration 0008


def test_0008_adds_approvals_and_the_downgrade_fails_waiting_tasks(env: Path) -> None:
    config = alembic_config()
    command.upgrade(config, "0008")
    assert check()["current"] == "0008" and rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("8",)]
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for status in ("WAITING_APPROVAL", "SUCCEEDED"):
            connection.execute(
                "INSERT INTO task (title, description, created_by, assigned_agent_id, depth, priority, input, status, created_at, updated_at) "
                "VALUES ('t', '', 'chairman', 1, 0, 'normal', '{}', ?, ?, ?)",
                (status, now, now),
            )
        connection.execute(
            "INSERT INTO approval (agent_id, task_id, tool_key, args, action, reason, expected_changes, risk_info, status, created_at, continuation) "
            "VALUES (1, 1, 'money.spend', '{}', 'a', 'r', 'e', 'k', 'PENDING', ?, '[]')",
            (now,),
        )
        try:
            connection.execute(
                "INSERT INTO approval (agent_id, task_id, tool_key, args, action, reason, expected_changes, risk_info, status, created_at, continuation) "
                "VALUES (1, 1, 'money.spend', '{}', 'a', 'r', 'e', 'k', 'MAYBE', ?, '[]')",
                (now,),
            )
            raise AssertionError("an unknown approval status was accepted")
        except sqlite3.IntegrityError:
            pass
    command.downgrade(config, "0007")
    assert not rows("SELECT name FROM sqlite_master WHERE name = 'approval'")
    assert rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("7",)]
    statuses = rows("SELECT status, error FROM task ORDER BY id")
    assert statuses[0][0] == "FAILED" and "approval system was removed" in statuses[0][1]
    assert statuses[1] == ("SUCCEEDED", None)
    command.upgrade(config, "head")
    assert rows("SELECT COUNT(*) FROM approval") == [(0,)]


# ---------------------------------------------------------------- the Demo path


def test_demo_phrase_creates_an_approval_and_the_task_waits(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api)
    assert DEMO_APPROVAL_PHRASE == "send message to customer"
    result, child = ask(api)

    assert child["status"] == "WAITING_APPROVAL" and child["assigned_agent"]["id"] == sumi["id"]
    assert result["status"] == "RUNNING"  # the Central Manager waits for its agent
    assert child["output"].startswith("[Demo] Sumi (Customer Support Agent")
    assert "always needs the Chairman's approval" in child["output"]
    assert "[Approval] Waiting for the Chairman's approval (request #1): Send a message to customer" in child["output"]
    assert child["completed_at"] is None and child["error"] is None
    assert rows("SELECT runtime_state FROM agent WHERE id = ?", sumi["id"]) == [("waiting",)]
    assert run_once() is False  # nothing more happens until the Chairman decides

    approvals = pending(api)
    assert len(approvals) == 1
    approval = approvals[0]
    # every field of docs/SPEC.md §8F
    assert approval["agent"]["display_name"] == "Sumi" and approval["agent"]["role"] == "Customer Support Agent"
    assert approval["action"] == "Send a message to customer: “[Demo] draft, not written by an AI model: send message to customer”"
    assert approval["reason"] == "The request says: “send message to customer”"
    assert (approval["tool_key"], approval["tool_name"], approval["risk"]) == ("message.send_external", "Send external message", "SENSITIVE")
    assert "Today nothing leaves this PC" in approval["expected_changes"]
    assert approval["risk_info"].startswith("External message. It cannot be taken back")
    assert approval["status"] == "PENDING" and approval["decided_at"] is None and approval["decided_by"] is None
    assert approval["executed_at"] is None and approval["result"] is None
    assert (approval["task_id"], approval["task_title"], approval["task_status"]) == (child["id"], child["title"], "WAITING_APPROVAL")
    assert approval["args"]["recipient"] == "customer" and approval["args"]["channel"] == "message"
    assert ok(api.get(f"/api/approvals/{approval['id']}")) == approval
    assert ok(api.get("/api/approvals/pending-count")) == {"pending": 1}

    # the Task Center can link to it: on the waiting task and on the request above it
    assert child["pending_approval_id"] == result["pending_approval_id"] == approval["id"]
    listed = ok(api.get("/api/tasks?top_level=true"))[0]
    assert listed["status"] == "RUNNING" and listed["pending_approval_id"] == approval["id"]
    assert [item["id"] for item in ok(api.get("/api/tasks?status=WAITING_APPROVAL"))] == [child["id"]]

    events = [(row["action"], row["decision"]) for row in audit_rows("task_id = ?", child["id"])]
    assert events == [("approval.created", "pending")]  # requested, not executed
    assert rows("SELECT COUNT(*) FROM audit_log WHERE action = 'tool.allowed' AND tool_key = 'message.send_external'") == [(0,)]


def test_other_wordings_and_ordinary_requests(api: TestClient) -> None:  # noqa: F811
    support_agent(api)
    for title, channel, recipient in (
        ("Please send an email to the supplier about the invoice", "email", "supplier"),
        ("send a reply to our client", "message", "client"),
    ):
        _result, child = ask(api, title)
        assert child["status"] == "WAITING_APPROVAL", title
        approval = pending(api)[0]
        assert (approval["args"]["channel"], approval["args"]["recipient"]) == (channel, recipient)
    _result, child = ask(api, "what is the price of this product for a customer")
    assert child["status"] == "SUCCEEDED" and "[Approval]" not in child["output"]  # no tool was asked for
    assert len(pending(api)) == 2


def test_approve_lets_the_task_continue_and_only_records_the_approval(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api)
    result, child = ask(api)
    approval = pending(api)[0]

    decided = ok(api.post(f"/api/approvals/{approval['id']}/approve", json={"note": "ok, go"}))
    assert decided["status"] == "APPROVED" and decided["decided_by"] == "chairman:chairman" and decided["decided_at"]
    assert decided["decision_note"] == "ok, go" and decided["executed_at"] is None  # the worker has not run yet
    assert detail(api, child["id"])["status"] == "RUNNING"
    assert ok(api.get("/api/approvals/pending-count")) == {"pending": 0}

    drain()
    child = detail(api, child["id"])
    result = detail(api, result["id"])
    assert child["status"] == "SUCCEEDED" and result["status"] == "SUCCEEDED"
    assert child["output"].endswith(f"[Tool] Send external message: {NO_CONNECTOR}. Nothing was sent.")
    assert child["pending_approval_id"] is None and result["pending_approval_id"] is None
    assert NO_CONNECTOR in result["output"]  # the Central Manager's report carries it too
    done = ok(api.get(f"/api/approvals/{approval['id']}"))
    assert done["status"] == "APPROVED" and done["executed_at"] and done["result"] == f"{NO_CONNECTOR}. Nothing was sent."
    assert rows("SELECT runtime_state FROM agent WHERE id = ?", sumi["id"]) == [("idle",)]

    events = [(row["action"], row["actor"], row["decision"]) for row in audit_rows("task_id = ?", child["id"])]
    assert events == [
        ("approval.created", f"agent:{sumi['id']}", "pending"),
        ("approval.approved", "chairman:chairman", "approved"),
        ("tool.allowed", f"agent:{sumi['id']}", "approved"),
    ]
    assert json.loads(audit_rows("action = 'approval.approved'")[0]["details"]) == {"approval_id": approval["id"], "note": "ok, go"}
    assert run_once() is False  # an approval is used exactly once


def test_reject_fails_the_task_with_rejected_by_chairman(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api)
    result, child = ask(api)
    approval = pending(api)[0]

    decided = ok(api.post(f"/api/approvals/{approval['id']}/reject", json={"note": "not now"}))
    assert decided["status"] == "REJECTED" and decided["decided_by"] == "chairman:chairman" and decided["result"] is None
    child = detail(api, child["id"])
    assert child["status"] == "FAILED" and child["completed_at"]
    assert child["error"] == "'Send external message' was rejected by Chairman. Note: not now"
    drain()
    result = detail(api, result["id"])
    assert result["status"] == "FAILED" and "rejected by Chairman" in result["error"]
    assert rows("SELECT runtime_state FROM agent WHERE id = ?", sumi["id"]) == [("idle",)]
    assert ok(api.get("/api/approvals/pending-count")) == {"pending": 0}
    # the tool never ran
    assert rows("SELECT COUNT(*) FROM audit_log WHERE action = 'tool.allowed' AND tool_key = 'message.send_external'") == [(0,)]
    assert rows("SELECT executed_at, result FROM approval") == [(None, None)]
    events = [(row["action"], row["decision"]) for row in audit_rows("task_id = ?", child["id"])]
    assert events == [("approval.created", "pending"), ("approval.rejected", "rejected")]
    # the result message to the Central Manager carries the reason
    message = [item for item in result["messages"] if item["type"] == "result"][0]
    assert message["payload"]["status"] == "FAILED" and "rejected by Chairman" in message["payload"]["error"]

    without_note = ask(api)[1]
    ok(api.post(f"/api/approvals/{pending(api)[0]['id']}/reject"))
    assert detail(api, without_note["id"])["error"] == "'Send external message' was rejected by Chairman."


def test_a_decision_can_be_made_only_once(api: TestClient) -> None:  # noqa: F811
    support_agent(api)
    for first, second in (("approve", "approve"), ("approve", "reject"), ("reject", "approve"), ("reject", "reject")):
        _result, child = ask(api)
        approval = pending(api)[0]
        ok(api.post(f"/api/approvals/{approval['id']}/{first}"))
        before = (detail(api, child["id"])["status"], rows("SELECT COUNT(*) FROM audit_log")[0][0])
        again = api.post(f"/api/approvals/{approval['id']}/{second}")
        assert again.status_code == 409, (first, second)
        expected = "APPROVED" if first == "approve" else "REJECTED"
        assert again.json() == {"detail": f"This approval request is already {expected}. It cannot be decided again."}
        assert ok(api.get(f"/api/approvals/{approval['id']}"))["status"] == expected
        assert (detail(api, child["id"])["status"], rows("SELECT COUNT(*) FROM audit_log")[0][0]) == before  # nothing changed
        drain()
    statuses = [row[0] for row in rows("SELECT status FROM approval ORDER BY id")]
    assert statuses == ["APPROVED", "APPROVED", "REJECTED", "REJECTED"]


def test_parallel_decisions_have_exactly_one_winner(api: TestClient) -> None:  # noqa: F811
    support_agent(api)
    _result, child = ask(api)
    approval = pending(api)[0]
    cookies = dict(api.cookies)

    def decide(action: str) -> int:
        with TestClient(api.app, base_url=BASE_URL, cookies=cookies) as other:
            return other.post(f"/api/approvals/{approval['id']}/{action}").status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = sorted(pool.map(decide, ["approve", "reject"] * 3))
    assert codes == [200, 409, 409, 409, 409, 409]
    status = ok(api.get(f"/api/approvals/{approval['id']}"))["status"]
    assert status in ("APPROVED", "REJECTED")
    assert detail(api, child["id"])["status"] == ("RUNNING" if status == "APPROVED" else "FAILED")
    assert rows("SELECT COUNT(*) FROM audit_log WHERE action IN ('approval.approved', 'approval.rejected')") == [(1,)]


def test_only_a_logged_in_chairman_can_decide(api: TestClient) -> None:  # noqa: F811
    support_agent(api)
    _result, child = ask(api)
    approval = pending(api)[0]
    with TestClient(api.app, base_url=BASE_URL) as stranger:
        for action in ("approve", "reject"):
            response = stranger.post(f"/api/approvals/{approval['id']}/{action}")
            assert response.status_code == 401 and response.json() == {"detail": "Not authenticated"}
        stranger.cookies.set("village_session", "not-a-real-session-token")
        assert stranger.post(f"/api/approvals/{approval['id']}/approve").status_code == 401
    # a cross-origin page cannot decide either, even with the Chairman's cookie
    foreign = api.post(f"/api/approvals/{approval['id']}/approve", headers={"Origin": "http://evil.example"})
    assert foreign.status_code == 403
    assert ok(api.get(f"/api/approvals/{approval['id']}"))["status"] == "PENDING"
    assert detail(api, child["id"])["status"] == "WAITING_APPROVAL"


APPROVAL_ROUTES = {
    ("GET", "/api/approvals"),
    ("GET", "/api/approvals/pending-count"),
    ("GET", "/api/approvals/{approval_id}"),
    ("POST", "/api/approvals/{approval_id}/approve"),
    ("POST", "/api/approvals/{approval_id}/reject"),
}


def test_every_approval_route_needs_a_session(api: TestClient) -> None:  # noqa: F811
    support_agent(api)
    ask(api)
    assert {route for route in api_routes(api.app) if route[1].startswith("/api/approvals")} == APPROVAL_ROUTES
    with TestClient(api.app, base_url=BASE_URL) as stranger:
        for method, path in sorted(APPROVAL_ROUTES):
            response = stranger.request(method, path.replace("{approval_id}", "1"))
            assert response.status_code == 401, (method, path)
            assert "Sumi" not in response.text and "customer" not in response.text


# ---------------------------------------------------------------- permissions still decide


def test_without_the_tool_or_the_permission_there_is_no_approval_at_all(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api, permissions=["read_upazila_memory"])  # the tool, but not the permission
    _result, child = ask(api)
    assert child["status"] == "FAILED"
    assert child["error"] == "Tool call refused. 'Sumi' does not have the permission 'Send external messages' that 'Send external message' needs."
    ok(api.patch(f"/api/agents/{sumi['id']}", json={"allowed_tools": ["product.read"], "permissions": MAY_SEND}))  # the permission, not the tool
    _result, child = ask(api)
    assert child["status"] == "FAILED" and "is not assigned to 'Sumi'" in child["error"]
    assert rows("SELECT COUNT(*) FROM approval") == [(0,)] and ok(api.get("/api/approvals")) == []
    assert [row["action"] for row in audit_rows("tool_key = 'message.send_external'")] == ["tool.denied", "tool.denied"]


def test_agent_paused_after_asking_does_not_get_the_approved_action(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api)
    result, child = ask(api)
    approval = pending(api)[0]
    ok(api.post(f"/api/agents/{sumi['id']}/pause"))
    ok(api.post(f"/api/approvals/{approval['id']}/approve"))
    drain()
    child = detail(api, child["id"])
    assert child["status"] == "FAILED"
    assert child["error"] == "The approved action was not carried out. 'Sumi' is paused. Only an active agent may use tools."
    done = ok(api.get(f"/api/approvals/{approval['id']}"))
    assert done["status"] == "APPROVED" and done["result"].startswith("Not carried out.") and done["executed_at"]
    assert [(row["action"], row["decision"]) for row in audit_rows("task_id = ?", child["id"])][-1] == ("tool.denied", "denied")
    assert detail(api, result["id"])["status"] == "FAILED"
    assert run_once() is False


def test_cancelling_a_waiting_task_withdraws_its_request(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api)
    result, child = ask(api)
    approval = pending(api)[0]
    ok(api.post(f"/api/tasks/{result['id']}/cancel"))  # the Chairman cancels the whole request
    assert detail(api, child["id"])["status"] == "CANCELLED"
    withdrawn = ok(api.get(f"/api/approvals/{approval['id']}"))
    assert withdrawn["status"] == "CANCELLED" and withdrawn["decided_by"] == "system"
    assert withdrawn["decision_note"] == "its task was cancelled before a decision."
    assert ok(api.get("/api/approvals/pending-count")) == {"pending": 0}
    for action in ("approve", "reject"):
        response = api.post(f"/api/approvals/{approval['id']}/{action}")
        assert response.status_code == 409 and "already CANCELLED" in response.json()["detail"]
    assert [row["action"] for row in audit_rows("task_id = ?", child["id"])] == ["approval.created", "approval.cancelled"]
    assert rows("SELECT runtime_state FROM agent WHERE id = ?", sumi["id"]) == [("idle",)]
    assert detail(api, child["id"])["pending_approval_id"] is None


# ---------------------------------------------------------------- more than one tool in a reply


def test_what_the_reply_asked_for_after_the_sensitive_call_runs_after_the_approval(
    api: TestClient, scripted: ScriptedProvider  # noqa: F811
) -> None:
    sumi = support_agent(api, allowed_tools=["org.read", *SEND], provider="scripted")
    send_it = ToolRequest("message.send_external", {"recipient": "Rahim", "body": "Your order is ready."}, reason="order 12 is packed")
    scripted.script["Sumi"] = [ToolRequest("org.read"), send_it, ToolRequest("org.read"), send_it]
    result, child = ask(api)
    assert child["status"] == "WAITING_APPROVAL"
    assert child["output"].count("[Tool] Read the organisation") == 1  # what came before it already ran
    first = pending(api)[0]
    assert first["reason"] == "order 12 is packed" and first["action"] == "Send a message to Rahim: “Your order is ready.”"
    assert json.loads(rows("SELECT continuation FROM approval WHERE id = ?", first["id"])[0][0]) == [
        {"tool": "org.read", "args": {}, "reason": ""},
        {"tool": "message.send_external", "args": {"recipient": "Rahim", "body": "Your order is ready."}, "reason": "order 12 is packed"},
    ]

    ok(api.post(f"/api/approvals/{first['id']}/approve"))
    drain()
    child = detail(api, child["id"])
    assert child["status"] == "WAITING_APPROVAL"  # the second sensitive call asks again
    assert child["output"].count("[Tool] Read the organisation") == 2 and child["output"].count(NO_CONNECTOR) == 1
    second = pending(api)[0]
    assert second["id"] != first["id"]
    ok(api.post(f"/api/approvals/{second['id']}/approve"))
    drain()
    child = detail(api, child["id"])
    assert child["status"] == "SUCCEEDED" and child["output"].count(NO_CONNECTOR) == 2
    assert scripted.calls == ["Sumi"]  # the provider was asked once; nothing was replayed
    assert detail(api, result["id"])["status"] == "SUCCEEDED"
    assert sumi["id"]


def test_bad_arguments_fail_the_task_without_an_approval(api: TestClient, scripted: ScriptedProvider) -> None:  # noqa: F811
    support_agent(api, allowed_tools=["money.spend", *SEND], permissions=["spend_money", *MAY_SEND], provider="scripted")
    for call, problem in (
        (ToolRequest("message.send_external", {"recipient": "Rahim"}), "'body' is required"),
        (ToolRequest("message.send_external", {"recipient": "Rahim", "body": "x", "attach": "/etc/passwd"}), "Unknown argument: attach"),
        (ToolRequest("money.spend", {"amount": -5, "purpose": "x"}), "'amount' must be a positive number"),
    ):
        scripted.script["Sumi"] = [call]
        _result, child = ask(api)
        assert child["status"] == "FAILED" and problem in child["error"], call
    assert rows("SELECT COUNT(*) FROM approval") == [(0,)]

    scripted.script["Sumi"] = [ToolRequest("money.spend", {"amount": 1500, "currency": "BDT", "purpose": "packaging"})]
    ask(api)
    approval = pending(api)[0]
    assert approval["action"] == "Spend 1500 BDT for: packaging" and approval["tool_name"] == "Spend money"
    assert "No money moves" in approval["expected_changes"].replace("no money moves", "No money moves")


def test_child_tasks_that_finished_while_the_parent_waited_are_reported(api: TestClient, scripted: ScriptedProvider) -> None:  # noqa: F811
    sumi = support_agent(
        api,
        allowed_tools=["task.create_child", *SEND],
        permissions=["delegate_tasks", *MAY_SEND],
        provider="scripted",
    )
    helper = agent_in(api, ok(api.get("/api/upazilas"))[0], "pion_helper", "Babu")
    scripted.script["Sumi"] = [
        ToolRequest("task.create_child", {"agent_id": helper["id"], "title": "Find the order"}),
        ToolRequest("message.send_external", {"recipient": "Rahim", "body": "We are looking."}),
    ]
    result, child = ask(api)  # Babu (Demo provider) has finished; Sumi waits for the Chairman
    assert child["status"] == "WAITING_APPROVAL"
    grandchild = detail(api, child["id"])["children"][0]
    assert grandchild["status"] == "SUCCEEDED"
    ok(api.post(f"/api/approvals/{pending(api)[0]['id']}/approve"))
    drain()
    child = detail(api, child["id"])
    assert child["status"] == "SUCCEEDED"
    assert NO_CONNECTOR in child["output"] and "--- Result from Babu (task #" in child["output"]
    assert detail(api, result["id"])["status"] == "SUCCEEDED" and sumi["id"]

    # rejecting stops the work the agent had handed on
    ok(api.post(f"/api/agents/{helper['id']}/pause"))  # so that its child task stays open
    ok(api.post(f"/api/agents/{helper['id']}/activate"))
    task = send(api, DEMO_APPROVAL_PHRASE)
    run_once(), run_once()  # routed; Sumi replied: child task created, approval requested
    waiting = detail(api, task["id"])["children"][0]
    assert waiting["status"] == "WAITING_APPROVAL"
    open_child = detail(api, waiting["id"])["children"][0]
    assert open_child["status"] == "ASSIGNED"
    ok(api.post(f"/api/approvals/{pending(api)[0]['id']}/reject"))
    assert detail(api, open_child["id"])["status"] == "CANCELLED"
    drain()
    assert detail(api, task["id"])["status"] == "FAILED"


# ---------------------------------------------------------------- restart


def test_waiting_and_approved_tasks_survive_a_restart(api: TestClient) -> None:  # noqa: F811
    support_agent(api)
    _result, waiting = ask(api)
    _result, approved = ask(api)
    approvals = sorted(pending(api), key=lambda item: item["id"])
    ok(api.post(f"/api/approvals/{approvals[1]['id']}/approve"))  # approved, but the server stops before the worker runs
    with get_session_factory()() as db:
        recovered = recover_interrupted(db)
    # only the Central Manager's two parent tasks are queued again; the approved task keeps its approval
    assert recovered == 2
    assert detail(api, waiting["id"])["status"] == "WAITING_APPROVAL"
    assert detail(api, approved["id"])["status"] == "RUNNING"
    drain()
    assert detail(api, approved["id"])["status"] == "SUCCEEDED"
    assert detail(api, waiting["id"])["status"] == "WAITING_APPROVAL"
    assert [item["id"] for item in pending(api)] == [approvals[0]["id"]]
    assert rows("SELECT COUNT(*) FROM approval") == [(2,)]  # nothing was asked twice


# ---------------------------------------------------------------- list


def test_list_filter_validation_and_404(api: TestClient) -> None:  # noqa: F811
    support_agent(api)
    for _ in range(3):
        ask(api)
    first, second, third = sorted(pending(api), key=lambda item: item["id"])
    ok(api.post(f"/api/approvals/{first['id']}/approve"))
    ok(api.post(f"/api/approvals/{second['id']}/reject"))
    assert [item["id"] for item in ok(api.get("/api/approvals"))] == [third["id"], second["id"], first["id"]]  # newest first
    for status, expected in (("PENDING", third), ("APPROVED", first), ("REJECTED", second)):
        assert [item["id"] for item in ok(api.get(f"/api/approvals?status={status}"))] == [expected["id"]]
    assert ok(api.get("/api/approvals?status=CANCELLED")) == []
    assert len(ok(api.get("/api/approvals?limit=2"))) == 2
    assert api.get("/api/approvals?status=MAYBE").status_code == 422
    assert api.get("/api/approvals/999").status_code == 404
    for action in ("approve", "reject"):
        assert api.post(f"/api/approvals/999/{action}").status_code == 404
    assert api.post(f"/api/approvals/{third['id']}/approve", json={"note": "x" * 501}).status_code == 422
    assert api.post(f"/api/approvals/{third['id']}/approve", json={"status": "APPROVED"}).status_code == 422
    assert ok(api.get(f"/api/approvals/{third['id']}"))["status"] == "PENDING"

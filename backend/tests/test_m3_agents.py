"""M3 Part A: agent templates, agent registry, lifecycle, Central Manager protection, Demo provider."""

from __future__ import annotations

import re
import socket
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient

from app.agent_catalog import AGENT_TEMPLATES, PERMISSION_KEYS
from app.config import get_settings
from app.db import get_engine
from app.dbcheck import alembic_config
from app.providers import (
    DEMO_PREFIX,
    AgentContext,
    DemoProvider,
    Provider,
    TaskContext,
    get_provider,
    provider_names,
    register_provider,
    unregister_provider,
)
from app.seed import seed_agents, seed_if_migrated
from app.tools import tool_keys
from tests.test_m2_org import api, delete, make_upazila, ok, study  # noqa: F401  (api is a fixture)
from tests.test_part_b_auth import api_routes

TOOL_KEYS = tool_keys()  # the central registry (app/tools) is the catalogue of tools since M4

# docs/SPEC.md §6, in the SPEC's order.
SPEC_AGENT_TEMPLATES = [
    "Village Manager",
    "Office Manager",
    "Pion / Helper",
    "Study Assistant",
    "Teacher / Tutor",
    "Research Librarian",
    "Business Manager",
    "Sales Assistant",
    "Customer Support Agent",
    "Accountant",
    "Daily Reporter",
    "Doctor / General Wellness Assistant",
    "Repair Technician",
    "Technical Support Agent",
    "Project Manager",
]


def rows(sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with sqlite3.connect(get_settings().db_file) as connection:
        return connection.execute(sql, params).fetchall()


def template(api: TestClient, key: str) -> dict[str, Any]:  # noqa: F811
    return next(item for item in ok(api.get("/api/agent-templates")) if item["key"] == key)


def study_office(api: TestClient, union: int = 0, ward: int = 0) -> dict[str, Any]:  # noqa: F811
    """A ward (with its office) of a generated Study Upazila; created on first use."""
    upazilas = [row for row in ok(api.get("/api/upazilas")) if row["template_key"] == "study"]
    upazila = upazilas[0] if upazilas else study(api)
    if not upazilas:
        ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    unions = ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))
    return ok(api.get(f"/api/unions/{unions[union]['id']}/wards"))[ward]


def make_agent(api: TestClient, key: str = "study_assistant", name: str = "Mina", **extra: Any) -> dict[str, Any]:  # noqa: F811
    office_id = extra.pop("office_id", None) or study_office(api)["office"]["id"]
    body = {"template_id": template(api, key)["id"], "display_name": name, "office_id": office_id, **extra}
    return ok(api.post("/api/agents", json=body), 201)


def central_manager(api: TestClient) -> dict[str, Any]:  # noqa: F811
    return next(agent for agent in ok(api.get("/api/agents")) if agent["is_central_manager"])


# ---------------------------------------------------------------- migration + seed


def test_0004_upgrade_keeps_existing_data_and_downgrade_removes_only_the_agent_tables(env: Path) -> None:
    config = alembic_config()
    command.upgrade(config, "0003")
    db_file = get_settings().db_file
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(db_file) as connection:  # a database shaped like a real M2 village
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
        connection.execute(
            "INSERT INTO ward (union_id, number, name, responsibility, created_at, updated_at) "
            "VALUES (1, 1, 'Class Routine', 'Class Routine', ?, ?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO office (kind, ward_id, name, description, created_at, updated_at) "
            "VALUES ('ward', 1, 'Class Routine Office', '', ?, ?)",
            (now, now),
        )
    snapshot_sql = (
        "SELECT (SELECT group_concat(name) FROM village), (SELECT group_concat(username) FROM admin_user), "
        "(SELECT group_concat(name) FROM upazila), (SELECT group_concat(name) FROM union_unit), "
        "(SELECT group_concat(name) FROM ward), (SELECT group_concat(name) FROM office), "
        "(SELECT COUNT(*) FROM upazila_template), (SELECT COUNT(*) FROM ward_template)"
    )
    before = rows(snapshot_sql)

    command.upgrade(config, "0004")
    assert rows(snapshot_sql) == before
    assert rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("4",)]
    assert rows("SELECT COUNT(*) FROM agent_template") == [(15,)]
    assert rows("SELECT display_name, lifecycle, is_central_manager FROM agent") == [("Central Manager", "active", 1)]

    command.downgrade(config, "0003")
    tables = {row[0] for row in rows("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not tables & {"agent", "agent_template"}
    assert rows(snapshot_sql) == before
    assert rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("3",)]

    command.upgrade(config, "0004")  # and up again: same result
    assert rows("SELECT COUNT(*) FROM agent_template") == [(15,)]
    assert rows("SELECT COUNT(*) FROM agent") == [(1,)]


def test_fifteen_templates_are_seeded_with_the_spec_names(api: TestClient) -> None:  # noqa: F811
    templates = ok(api.get("/api/agent-templates"))
    assert [item["name"] for item in templates] == SPEC_AGENT_TEMPLATES
    assert len({item["key"] for item in templates}) == 15
    for item in templates:
        assert item["role"] and item["description"] and item["avatar_key"] and item["default_instructions"]
        assert set(item["default_tools"]) <= TOOL_KEYS and item["default_tools"]
        assert set(item["default_permissions"]) <= PERMISSION_KEYS


def test_doctor_and_repair_templates_are_limited(api: TestClient) -> None:  # noqa: F811
    doctor = template(api, "doctor_wellness")
    text = (doctor["description"] + " " + doctor["default_instructions"]).lower()
    assert "general" in text and "wellness" in text
    assert "must not diagnose" in text and "must not prescribe" in text
    assert "qualified doctor" in text

    repair = template(api, "repair_technician")
    text = repair["default_instructions"].lower()
    assert "approved tools" in text and "no terminal access" in text
    # no tool anywhere in the catalogue gives a shell, a terminal or free file access
    assert not [key for key in TOOL_KEYS if re.search(r"shell|terminal|command|exec|filesystem", key)]
    options = ok(api.get("/api/agent-options"))
    assert {item["key"] for item in options["tools"]} == TOOL_KEYS
    assert {item["key"] for item in options["permissions"]} == PERMISSION_KEYS
    assert options["enforced"] is True and options["providers"] == ["demo"]  # enforced since M4
    # sensitive permissions are never a default
    sensitive = {item["key"] for item in options["permissions"] if item["sensitive"]}
    assert sensitive and not any(sensitive & set(item.default_permissions) for item in AGENT_TEMPLATES)


def test_seeding_is_idempotent_and_repairs_what_is_missing(api: TestClient) -> None:  # noqa: F811
    engine = get_engine()
    for _ in range(3):
        with engine.begin() as connection:
            assert seed_agents(connection) == (0, False)
    assert seed_if_migrated(engine) is True
    assert rows("SELECT COUNT(*) FROM agent_template") == [(15,)]
    assert rows("SELECT COUNT(*) FROM agent WHERE is_central_manager = 1") == [(1,)]

    with sqlite3.connect(get_settings().db_file) as connection:  # an owner's edit and two losses
        connection.execute("UPDATE agent_template SET name = 'Homework Helper' WHERE key = 'study_assistant'")
        connection.execute("DELETE FROM agent_template WHERE key = 'accountant'")
        connection.execute("DELETE FROM agent")
    with engine.begin() as connection:
        assert seed_agents(connection) == (1, True)
    assert rows("SELECT COUNT(*) FROM agent_template") == [(15,)]
    assert rows("SELECT name FROM agent_template WHERE key = 'study_assistant'") == [("Homework Helper",)]  # kept
    assert rows("SELECT COUNT(*) FROM agent WHERE is_central_manager = 1") == [(1,)]


def test_seed_at_startup_skips_a_database_without_the_agent_tables(env: Path) -> None:
    command.upgrade(alembic_config(), "0003")
    assert seed_if_migrated(get_engine()) is False


def test_database_allows_only_one_central_manager(api: TestClient) -> None:  # noqa: F811
    with sqlite3.connect(get_settings().db_file) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO agent (display_name, avatar_key, role, description, system_instructions, allowed_tools, "
            "permissions, provider, memory_config, working_schedule, lifecycle, runtime_state, is_central_manager, "
            "created_at, updated_at) VALUES ('Second', '', 'x', '', '', '[]', '[]', 'demo', '{}', '{}', 'active', "
            "'idle', 1, '2026-01-01', '2026-01-01')"
        )


# ---------------------------------------------------------------- central manager


def test_central_manager_is_seeded_in_central_administration(api: TestClient) -> None:  # noqa: F811
    agents = ok(api.get("/api/agents"))
    assert len(agents) == 1
    manager = agents[0]
    central = ok(api.get("/api/offices/central"))
    assert manager["display_name"] == "Central Manager" and manager["is_central_manager"] is True
    assert manager["template_key"] == "village_manager" and manager["role"] == "Village Manager"
    assert manager["office_id"] == central["id"]
    assert manager["location"]["office"] == {"id": central["id"], "name": "Central Administration", "kind": "central"}
    assert manager["location"]["upazila"] is None and manager["location"]["path"] == "Central Administration"
    assert (manager["lifecycle"], manager["runtime_state"], manager["provider"]) == ("active", "idle", "demo")
    assert ok(api.get("/api/stats/overview"))["agents"] == 1


def test_central_manager_cannot_be_paused_disabled_deleted_or_moved(api: TestClient) -> None:  # noqa: F811
    manager = central_manager(api)
    url = f"/api/agents/{manager['id']}"
    for action in ("pause", "disable"):
        response = api.post(f"{url}/{action}")
        assert response.status_code == 409
        assert "Central Manager cannot be" in response.json()["detail"]
    response = delete(api, url, {"confirm_name": "Central Manager"})
    assert response.status_code == 409 and "cannot be deleted" in response.json()["detail"]
    moved = api.patch(url, json={"office_id": study_office(api)["office"]["id"]})
    assert moved.status_code == 409 and "cannot be moved" in moved.json()["detail"]

    after = ok(api.get(url))
    assert (after["lifecycle"], after["office_id"]) == ("active", manager["office_id"])
    # it can still be renamed and re-instructed, and activating it is a harmless no-op
    edited = ok(api.patch(url, json={"display_name": "Chief of Staff", "system_instructions": "Route carefully."}))
    assert edited["display_name"] == "Chief of Staff" and edited["is_central_manager"] is True
    assert ok(api.post(f"{url}/activate"))["lifecycle"] == "active"


# ---------------------------------------------------------------- CRUD


def test_agent_is_created_from_a_template_with_its_defaults_and_derived_location(api: TestClient) -> None:  # noqa: F811
    ward = study_office(api)
    source = template(api, "study_assistant")
    agent = make_agent(api, name="  Mina  ")
    assert agent["display_name"] == "Mina"
    for field, default in (
        ("role", "role"),
        ("description", "description"),
        ("avatar_key", "avatar_key"),
        ("system_instructions", "default_instructions"),
        ("allowed_tools", "default_tools"),
        ("permissions", "default_permissions"),
    ):
        assert agent[field] == source[default], field
    assert (agent["template_id"], agent["template_key"], agent["template_name"]) == (source["id"], "study_assistant", "Study Assistant")
    assert (agent["lifecycle"], agent["runtime_state"], agent["provider"]) == ("active", "idle", "demo")
    assert agent["is_central_manager"] is False and agent["has_history"] is False and agent["disabled_at"] is None
    assert agent["memory_config"] == {} and agent["working_schedule"] == {}

    location = agent["location"]
    assert location["office"]["id"] == ward["office"]["id"] and location["office"]["kind"] == "ward"
    assert location["ward"] == {"id": ward["id"], "number": 1, "name": "Class Routine"}
    assert location["union"]["name"] == "Academic Management" and location["upazila"]["name"] == "Study Upazila"
    assert location["path"] == "Study Upazila › Academic Management › Ward 1: Class Routine"
    # the location is derived: nothing but the office is stored on the agent
    columns = {row[1] for row in rows("PRAGMA table_info(agent)")}
    assert "office_id" in columns and not columns & {"upazila_id", "union_id", "ward_id"}
    assert ok(api.get(f"/api/agents/{agent['id']}")) == agent


def test_create_accepts_overrides_and_can_start_paused(api: TestClient) -> None:  # noqa: F811
    agent = make_agent(
        api,
        key="teacher_tutor",
        name="Tutor Rahim",
        role="Maths Tutor",
        description="Algebra only",
        system_instructions="Teach algebra.",
        allowed_tools=["document.read", "document.read"],
        permissions=[],
        avatar_key="teacher",
        activate=False,
    )
    assert (agent["role"], agent["description"], agent["system_instructions"]) == ("Maths Tutor", "Algebra only", "Teach algebra.")
    assert agent["allowed_tools"] == ["document.read"] and agent["permissions"] == []
    assert (agent["lifecycle"], agent["runtime_state"]) == ("paused", "offline")


def test_create_validation(api: TestClient) -> None:  # noqa: F811
    office = study_office(api)["office"]["id"]
    study_template = template(api, "study_assistant")["id"]
    good = {"template_id": study_template, "display_name": "Mina", "office_id": office}
    assert api.post("/api/agents", json={**good, "template_id": 999}).status_code == 404
    assert api.post("/api/agents", json={**good, "office_id": 999}).status_code == 404
    assert api.post("/api/agents", json={**good, "display_name": "  "}).status_code == 422
    assert api.post("/api/agents", json={**good, "display_name": "x" * 81}).status_code == 422
    assert api.post("/api/agents", json={**good, "allowed_tools": ["run_shell"]}).status_code == 422
    assert api.post("/api/agents", json={**good, "permissions": ["root"]}).status_code == 422
    assert api.post("/api/agents", json={**good, "lifecycle": "active"}).status_code == 422  # unknown field
    assert api.post("/api/agents", json={"display_name": "Mina"}).status_code == 422
    assert len(ok(api.get("/api/agents"))) == 1  # only the Central Manager


def test_agent_can_be_edited_and_moved(api: TestClient) -> None:  # noqa: F811
    agent = make_agent(api)
    url = f"/api/agents/{agent['id']}"
    other = study_office(api, union=1, ward=2)
    edited = ok(
        api.patch(
            url,
            json={
                "display_name": "Mina Akter",
                "role": "Exam Coach",
                "description": "Exams",
                "system_instructions": "Coach for exams.",
                "allowed_tools": ["knowledge.search"],
                "permissions": ["read_upazila_memory"],
                "avatar_key": "teacher",
                "office_id": other["office"]["id"],
                "provider": "demo",
            },
        )
    )
    assert (edited["display_name"], edited["role"], edited["avatar_key"]) == ("Mina Akter", "Exam Coach", "teacher")
    assert edited["allowed_tools"] == ["knowledge.search"] and edited["permissions"] == ["read_upazila_memory"]
    assert edited["location"]["union"]["name"] == "Course Learning" and edited["location"]["ward"]["number"] == 3
    assert edited["template_key"] == "study_assistant"  # the template is where it came from; it does not change

    assert api.patch(url, json={"provider": "anthropic"}).status_code == 422  # no such provider in M3
    assert api.patch(url, json={"allowed_tools": ["nope"]}).status_code == 422
    assert api.patch(url, json={"office_id": 999}).status_code == 404
    assert api.patch(url, json={"lifecycle": "disabled"}).status_code == 422  # lifecycle has its own endpoints
    assert api.patch("/api/agents/999", json={"display_name": "X"}).status_code == 404
    assert ok(api.get(url)) == edited


def test_list_filters(api: TestClient) -> None:  # noqa: F811
    first = make_agent(api, name="Mina")
    second_office = study_office(api, union=1)["office"]["id"]
    second = make_agent(api, key="teacher_tutor", name="Rahim", office_id=second_office)
    garden = make_upazila(api, "Garden")
    union = ok(api.post(f"/api/upazilas/{garden['id']}/unions", json={"name": "North"}), 201)
    garden_ward = ok(api.post(f"/api/unions/{union['id']}/wards", json={}), 201)
    third = make_agent(api, key="pion_helper", name="Kamal", office_id=garden_ward["office"]["id"])
    ok(api.post(f"/api/agents/{second['id']}/pause"))
    manager = central_manager(api)

    def ids(query: str = "") -> list[int]:
        return [agent["id"] for agent in ok(api.get(f"/api/agents{query}"))]

    assert ids() == [manager["id"], first["id"], second["id"], third["id"]]  # the Central Manager first
    study_id = first["location"]["upazila"]["id"]
    assert ids(f"?upazila_id={study_id}") == [first["id"], second["id"]]
    assert ids(f"?upazila_id={garden['id']}") == [third["id"]]
    assert ids(f"?office_id={second_office}") == [second["id"]]
    assert ids(f"?office_id={manager['office_id']}") == [manager["id"]]
    assert ids("?lifecycle=paused") == [second["id"]]
    assert ids(f"?lifecycle=active&upazila_id={study_id}") == [first["id"]]
    assert ids("?upazila_id=999") == []
    assert api.get("/api/agents?lifecycle=sleeping").status_code == 422
    stats = ok(api.get("/api/stats/overview"))
    assert (stats["agents"], stats["active_agents"]) == (4, 3)


# ---------------------------------------------------------------- lifecycle + delete


def test_lifecycle_activate_pause_disable(api: TestClient) -> None:  # noqa: F811
    agent = make_agent(api)
    url = f"/api/agents/{agent['id']}"

    paused = ok(api.post(f"{url}/pause"))
    assert (paused["lifecycle"], paused["runtime_state"], paused["disabled_at"]) == ("paused", "offline", None)
    disabled = ok(api.post(f"{url}/disable"))
    assert (disabled["lifecycle"], disabled["runtime_state"]) == ("disabled", "offline")
    assert disabled["disabled_at"] is not None
    assert ok(api.post(f"{url}/disable"))["disabled_at"] == disabled["disabled_at"]  # repeating changes nothing
    active = ok(api.post(f"{url}/activate"))
    assert (active["lifecycle"], active["runtime_state"], active["disabled_at"]) == ("active", "idle", None)

    for action in ("activate", "pause", "disable"):
        assert api.post(f"/api/agents/999/{action}").status_code == 404


def test_delete_needs_the_exact_name_and_removes_an_agent_without_history(api: TestClient) -> None:  # noqa: F811
    agent = make_agent(api)
    url = f"/api/agents/{agent['id']}"
    for body in (None, {}, {"confirm_name": "mina"}):
        assert delete(api, url, body).status_code == 400
    assert ok(delete(api, url, {"confirm_name": "Mina"})) == {"deleted": True}
    assert api.get(url).status_code == 404
    assert delete(api, url, {"confirm_name": "Mina"}).status_code == 404
    assert len(ok(api.get("/api/agents"))) == 1


# ---------------------------------------------------------------- deleting an office


@pytest.mark.parametrize("level", ["ward", "union", "upazila"])
def test_deleting_an_office_keeps_its_agents_without_office_and_disabled(api: TestClient, level: str) -> None:  # noqa: F811
    ward = study_office(api)
    doomed = make_agent(api, name="Mina")
    paused = make_agent(api, key="teacher_tutor", name="Rahim")
    ok(api.post(f"/api/agents/{paused['id']}/pause"))
    garden = make_upazila(api, "Garden")
    union = ok(api.post(f"/api/upazilas/{garden['id']}/unions", json={"name": "North"}), 201)
    garden_ward = ok(api.post(f"/api/unions/{union['id']}/wards", json={}), 201)
    safe = make_agent(api, key="pion_helper", name="Kamal", office_id=garden_ward["office"]["id"])
    manager = central_manager(api)

    location = doomed["location"]
    target = {
        "ward": (f"/api/wards/{ward['id']}", ward["name"]),
        "union": (f"/api/unions/{location['union']['id']}", location["union"]["name"]),
        "upazila": (f"/api/upazilas/{location['upazila']['id']}", location["upazila"]["name"]),
    }[level]
    result = ok(delete(api, target[0], {"confirm_name": target[1]}))
    assert result["agents_disabled"] == 2

    for agent in (doomed, paused):
        after = ok(api.get(f"/api/agents/{agent['id']}"))
        assert (after["office_id"], after["location"]) == (None, None)
        assert (after["lifecycle"], after["runtime_state"]) == ("disabled", "offline")
        assert after["disabled_at"] is not None
        assert after["display_name"] == agent["display_name"]  # the agent itself is kept
    assert ok(api.get(f"/api/agents/{safe['id']}")) == safe
    assert ok(api.get(f"/api/agents/{manager['id']}")) == manager

    # without an office it cannot be activated; with a new office it can
    blocked = api.post(f"/api/agents/{doomed['id']}/activate")
    assert blocked.status_code == 409 and "Assign an Office" in blocked.json()["detail"]
    ok(api.patch(f"/api/agents/{doomed['id']}", json={"office_id": garden_ward["office"]["id"]}))
    revived = ok(api.post(f"/api/agents/{doomed['id']}/activate"))
    assert revived["lifecycle"] == "active" and revived["location"]["upazila"]["name"] == "Garden"


# ---------------------------------------------------------------- providers


def test_demo_provider_needs_no_key_and_no_network(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_settings().anthropic_api_key is None

    def no_network(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the Demo provider must not open a network connection")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)

    provider = get_provider("demo")
    assert isinstance(provider, DemoProvider) and provider.is_configured() and provider.name == "demo"
    agent = AgentContext(
        display_name="Mina",
        role="Study Assistant",
        template_key="study_assistant",
        location="Study Upazila › Academic Management › Ward 1: Class Routine",
    )
    reply = provider.reply(agent, TaskContext(title="Help me prepare for my exam", description="Physics, next week"))
    assert reply.startswith(DEMO_PREFIX) and DEMO_PREFIX == "[Demo]"
    assert "Mina (Study Assistant, Study Upazila" in reply
    assert "Help me prepare for my exam" in reply and "Physics, next week" in reply
    assert "no AI model was used" in reply
    assert "study plan" in reply  # the Study Assistant's playbook
    assert provider.reply(agent, TaskContext(title="Help me prepare for my exam", description="Physics, next week")) == reply


@pytest.mark.parametrize("seed", AGENT_TEMPLATES, ids=lambda seed: seed.key)
def test_demo_provider_has_a_labelled_reply_for_every_template(seed: Any) -> None:
    reply = DemoProvider().reply(
        AgentContext(display_name="Agent", role=seed.role, template_key=seed.key), TaskContext(title="Do the thing")
    )
    assert reply.startswith("[Demo] Agent (") and seed.role in reply and "1. " in reply and "3. " in reply
    if seed.key == "doctor_wellness":
        assert "not a diagnosis and not a prescription" in reply and "qualified doctor" in reply
    if seed.key == "repair_technician":
        assert "no terminal access" in reply and "No command was run" in reply


def test_demo_provider_handles_an_unknown_role() -> None:
    reply = DemoProvider().reply(AgentContext(display_name="Zed", role="Gardener"), TaskContext(title="Water the plants"))
    assert reply.startswith("[Demo] Zed (Gardener)") and "Water the plants" in reply


def test_registry_returns_demo_unless_a_provider_is_registered_and_configured() -> None:
    assert provider_names() == ["demo"]
    assert isinstance(get_provider(), DemoProvider)
    assert isinstance(get_provider(None), DemoProvider)
    assert isinstance(get_provider("anthropic"), DemoProvider)  # not implemented in M3 → Demo
    assert isinstance(get_provider("no-such-provider"), DemoProvider)

    class FakeProvider(Provider):
        name = "fake"
        configured = False

        def is_configured(self) -> bool:
            return self.configured

        def reply(self, agent: AgentContext, task: TaskContext) -> str:
            return "fake reply"

    fake = FakeProvider()
    register_provider(fake)
    try:
        assert isinstance(get_provider("fake"), DemoProvider)  # registered, but no key → Demo
        fake.configured = True
        assert get_provider("fake") is fake
    finally:
        unregister_provider("fake")
    assert provider_names() == ["demo"]


# ---------------------------------------------------------------- auth

AGENT_ROUTES = {
    ("GET", "/api/agent-templates"),
    ("GET", "/api/agent-options"),
    ("GET", "/api/agents"),
    ("POST", "/api/agents"),
    ("GET", "/api/agents/{agent_id}"),
    ("PATCH", "/api/agents/{agent_id}"),
    ("POST", "/api/agents/{agent_id}/activate"),
    ("POST", "/api/agents/{agent_id}/pause"),
    ("POST", "/api/agents/{agent_id}/disable"),
    ("DELETE", "/api/agents/{agent_id}"),
}


def test_every_agent_route_needs_a_session(api: TestClient) -> None:  # noqa: F811
    agent = make_agent(api)
    before = ok(api.get("/api/agents"))
    api.cookies.clear()

    routes = api_routes(api.app)
    assert {route for route in routes if route[1].startswith("/api/agent")} == AGENT_ROUTES
    for method, path_template in sorted(AGENT_ROUTES):
        path = re.sub(r"\{\w+\}", str(agent["id"]), path_template)  # a real id, so a missing guard would really act
        body = None if method == "GET" else {"display_name": "Hacked", "confirm_name": "Mina"}
        response = api.request(method, path, json=body)
        assert response.status_code == 401, (method, path, response.text)

    from tests.test_part_b_auth import PASSWORD

    ok(api.post("/api/auth/login", json={"username": "chairman", "password": PASSWORD}))
    assert ok(api.get("/api/agents")) == before

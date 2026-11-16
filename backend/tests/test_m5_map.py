"""M5 Part C: GET /api/map — one level of the village at a time."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.task_runner import drain
from tests.conftest import BASE_URL
from tests.test_m2_org import api, make_upazila, ok, statements  # noqa: F401  (fixtures)
from tests.test_m3_agents import central_manager, make_agent, study_office
from tests.test_m3_tasks import send
from tests.test_m4_approvals import ask, support_agent
from tests.test_part_b_auth import api_routes


def level(api: TestClient, name: str = "village", place: int | None = None) -> dict[str, Any]:  # noqa: F811
    return ok(api.get(f"/api/map?level={name}" + (f"&id={place}" if place is not None else "")))


def by_name(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {building["name"]: building for building in view["buildings"]}


def test_empty_village_has_only_central_administration(api: TestClient) -> None:  # noqa: F811
    manager = central_manager(api)
    view = level(api)
    assert (view["level"], view["id"], view["name"], view["parent"]) == ("village", None, "Shantipur", None)
    assert view["breadcrumb"] == [{"level": "village", "id": None, "label": "Shantipur"}]
    assert len(view["buildings"]) == 1
    central = view["buildings"][0]
    assert (central["type"], central["name"], central["target"]) == ("central", "Central Administration", None)
    assert (central["child_count"], central["child_label"], central["agent_count"], central["active_tasks"]) == (1, "Agents", 1, 0)
    assert central["agents"] == [
        {"id": manager["id"], "name": "Central Manager", "role": "Village Manager", "template_key": "village_manager", "activity": "idle", "current_task_id": None}
    ]
    assert (view["agent_count"], view["active_tasks"], view["agents"], view["office_name"]) == (1, 0, [], None)
    assert ok(api.get("/api/map")) == view  # village is the default level


def test_village_level_shows_one_building_per_upazila(api: TestClient) -> None:  # noqa: F811
    ok(api.post("/api/upazilas/standard"))
    view = level(api)
    assert [building["type"] for building in view["buildings"]] == ["central"] + ["upazila"] * 6
    study = by_name(view)["Study Upazila"]
    assert (study["child_count"], study["child_label"], study["agent_count"], study["agents"]) == (0, "Unions", 0, [])
    assert study["target"] == {"level": "upazila", "id": study["id"]}
    assert [building["name"] for building in view["buildings"][1:]] == [item["name"] for item in ok(api.get("/api/upazilas"))]  # the village's order


def test_drilling_down_a_full_study_upazila(api: TestClient) -> None:  # noqa: F811
    office = study_office(api)  # Study Upazila with its standard structure: 5 Unions × 9 Wards
    mina = make_agent(api, office_id=office["office"]["id"])
    others = [make_agent(api, key="teacher_tutor", name=f"Tutor {index}", office_id=office["office"]["id"]) for index in range(1, 6)]
    far = make_agent(api, name="Rafi", office_id=study_office(api, union=2, ward=4)["office"]["id"])
    ok(api.post(f"/api/agents/{far['id']}/pause"))

    village = level(api)
    study = by_name(village)["Study Upazila"]
    assert (study["child_count"], study["agent_count"], study["active_tasks"]) == (5, 7, 0)
    assert [agent["name"] for agent in study["agents"]] == ["Mina", "Tutor 1", "Tutor 2", "Tutor 3"]  # the first four; the count says the rest
    assert village["agent_count"] == 8  # with the Central Manager

    upazila = level(api, "upazila", study["id"])
    assert (upazila["level"], upazila["name"]) == ("upazila", "Study Upazila")
    assert upazila["parent"] == {"level": "village", "id": None}
    assert [crumb["label"] for crumb in upazila["breadcrumb"]] == ["Shantipur", "Study Upazila"]
    assert [building["name"] for building in upazila["buildings"]] == [
        "Academic Management", "Course Learning", "Exam Preparation", "Research Paper Learning", "Academic Documentation",
    ]
    assert {building["type"] for building in upazila["buildings"]} == {"union"}
    assert all((building["child_count"], building["child_label"]) == (9, "Wards") for building in upazila["buildings"])
    assert [building["agent_count"] for building in upazila["buildings"]] == [6, 0, 1, 0, 0]
    assert upazila["agent_count"] == 7  # the Central Manager is not in this Upazila

    academic = upazila["buildings"][0]
    union = level(api, "union", academic["id"])
    assert union["parent"] == {"level": "upazila", "id": study["id"]}
    assert [crumb["level"] for crumb in union["breadcrumb"]] == ["village", "upazila", "union"]
    assert len(union["buildings"]) == 9 and {building["type"] for building in union["buildings"]} == {"ward"}
    first = union["buildings"][0]
    assert (first["name"], first["detail"], first["child_count"], first["child_label"]) == ("Ward 1: Class Routine", "Class Routine Office", 6, "Agents")
    assert first["target"] == {"level": "ward", "id": first["id"]} and len(first["agents"]) == 4
    assert [building["agent_count"] for building in union["buildings"][1:]] == [0] * 8

    ward = level(api, "ward", first["id"])
    assert (ward["level"], ward["name"], ward["office_name"]) == ("ward", "Ward 1: Class Routine", "Class Routine Office")
    assert ward["parent"] == {"level": "union", "id": academic["id"]}
    assert [crumb["label"] for crumb in ward["breadcrumb"]] == ["Shantipur", "Study Upazila", "Academic Management", "Ward 1: Class Routine"]
    assert ward["buildings"] == []
    assert [agent["name"] for agent in ward["agents"]] == ["Mina", *[agent["display_name"] for agent in others]]  # every workspace, not only four
    assert ward["agents"][0] == {"id": mina["id"], "name": "Mina", "role": "Study Assistant", "template_key": "study_assistant", "activity": "idle", "current_task_id": None}

    exam = upazila["buildings"][2]
    paused = level(api, "ward", level(api, "union", exam["id"])["buildings"][4]["id"])
    assert [(agent["name"], agent["activity"]) for agent in paused["agents"]] == [("Rafi", "offline")]


def test_active_tasks_and_activity_on_the_map(api: TestClient) -> None:  # noqa: F811
    sumi = support_agent(api)
    make_agent(api)  # Mina, in Study Upazila
    result, child = ask(api)  # Sumi's task waits for approval; the Central Manager's request is still open
    send(api, "send message to customer")  # a second request, not started yet

    village = level(api)
    buildings = by_name(village)
    central = buildings["Central Administration"]
    assert central["active_tasks"] == 1 and central["agents"][0]["activity"] == "working"
    assert central["agents"][0]["current_task_id"] == result["id"]
    business = buildings["Business Upazila"]
    assert (business["agent_count"], business["active_tasks"]) == (1, 1)
    assert business["agents"] == [
        {"id": sumi["id"], "name": "Sumi", "role": "Customer Support Agent", "template_key": "customer_support", "activity": "waiting", "current_task_id": child["id"]}
    ]
    assert buildings["Study Upazila"]["active_tasks"] == 0
    assert village["active_tasks"] == 2  # tasks that have an agent; the queued request has none yet

    union = level(api, "upazila", business["id"])["buildings"][0]
    ward = level(api, "union", union["id"])["buildings"][0]
    assert (union["active_tasks"], ward["active_tasks"]) == (1, 1)
    office = level(api, "ward", ward["id"])
    assert office["active_tasks"] == 1 and office["agents"][0]["activity"] == "waiting"

    drain()  # the second request is delegated too: Sumi now has two open tasks
    assert by_name(level(api))["Business Upazila"]["active_tasks"] == 2


def test_missing_places_and_bad_parameters(api: TestClient) -> None:  # noqa: F811
    for name in ("upazila", "union", "ward"):
        response = api.get(f"/api/map?level={name}&id=999")
        assert response.status_code == 404 and response.json()["detail"].endswith("not found")
        assert api.get(f"/api/map?level={name}").status_code == 422  # a level below the village needs an id
    for bad in ("level=office", "level=ward&id=0", "level=ward&id=x", "level=everything"):
        assert api.get(f"/api/map?{bad}").status_code == 422, bad
    # an Upazila without Unions, a Union without Wards: empty, not an error
    garden = make_upazila(api, "Garden")
    assert level(api, "upazila", garden["id"])["buildings"] == []
    union = ok(api.post(f"/api/upazilas/{garden['id']}/unions", json={"name": "Beds"}), 201)
    empty = level(api, "union", union["id"])
    assert empty["buildings"] == [] and empty["agent_count"] == 0
    ward = ok(api.post(f"/api/unions/{union['id']}/wards", json={"name": "Roses"}), 201)
    office = level(api, "ward", ward["id"])
    assert office["agents"] == [] and office["office_name"] == "Roses Office"


def test_map_queries_do_not_grow_with_the_village(api: TestClient, statements: list[str]) -> None:  # noqa: F811
    def queries(path: str) -> int:
        statements.clear()
        ok(api.get(path))
        return len([item for item in statements if item.lstrip().upper().startswith("SELECT")])

    small = queries("/api/map")
    ok(api.post("/api/upazilas/standard"))
    upazilas = ok(api.get("/api/upazilas"))
    for upazila in upazilas:
        ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    for index in range(6):
        make_agent(api, name=f"Agent {index}", office_id=study_office(api, union=index % 5, ward=index)["office"]["id"])
    assert queries("/api/map") <= small + 1  # (+1: the open-task count, asked only when there are agents)
    assert queries("/api/map") <= 8
    study = next(item for item in upazilas if item["template_key"] == "study")
    assert queries(f"/api/map?level=upazila&id={study['id']}") <= 9


def test_map_needs_a_session(api: TestClient) -> None:  # noqa: F811
    make_agent(api)
    assert {route for route in api_routes(api.app) if route[1].startswith("/api/map")} == {("GET", "/api/map")}
    with TestClient(api.app, base_url=BASE_URL) as stranger:
        for path in ("/api/map", "/api/map?level=upazila&id=1", "/api/map?level=ward&id=1"):
            response = stranger.get(path)
            assert response.status_code == 401 and "Mina" not in response.text

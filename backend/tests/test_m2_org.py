"""M2 Part A: organization API — templates, Upazila/Union/Ward/Office CRUD, generation, tree, stats."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.config import get_settings
from app.db import get_engine
from app.dbcheck import alembic_config, check
from tests.test_part_b_auth import api_routes, do_setup

# docs/SPEC.md §5 (template names) and §11 (union names, Study ward responsibilities).
SPEC_TEMPLATES: dict[str, tuple[str, list[str]]] = {
    "study": (
        "Study Upazila",
        ["Academic Management", "Course Learning", "Exam Preparation", "Research Paper Learning", "Academic Documentation"],
    ),
    "business": (
        "Business Upazila",
        ["Business Strategy", "Product Management", "Marketing & Branding", "Customer & Sales", "Finance & Operations"],
    ),
    "career": (
        "Career & Job Preparation Upazila",
        ["Software Engineering Skills", "Competitive Programming", "Job Opportunities", "CV & Portfolio", "Interview Preparation"],
    ),
    "research": (
        "Research Upazila",
        ["Paper Discovery", "Literature Review", "Research Topic Discovery", "Data Analysis", "Research Documentation"],
    ),
    "project": (
        "Project Development Upazila",
        ["Project Planning", "Frontend Development", "Backend Development", "Database & API", "Testing & Deployment"],
    ),
    "personal": (
        "Personal Management Upazila",
        ["Daily Routine", "Task Management", "File Management", "Knowledge Management", "Daily Reporting"],
    ),
}
SPEC_STUDY_WARDS = [
    "Class Routine",
    "Assignment & Deadline",
    "Exam Preparation",
    "Learning Materials",
    "Note Making",
    "Course Tutor",
    "Academic Progress",
    "Study Planning",
    "Daily Academic Reporting",
]
ORG_TABLES = ("upazila", "union_unit", "ward", "office")


@pytest.fixture
def api(client: TestClient) -> TestClient:
    """A client that has completed setup and holds the admin session cookie."""
    do_setup(client)
    return client


def db_counts() -> dict[str, int]:
    with sqlite3.connect(get_settings().db_file) as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ORG_TABLES}


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def make_upazila(api: TestClient, name: str = "Garden", **extra: Any) -> dict[str, Any]:
    return ok(api.post("/api/upazilas", json={"name": name, **extra}), 201)


def study(api: TestClient) -> dict[str, Any]:
    return make_upazila(api, "Study Upazila", template_key="study")


def delete(api: TestClient, path: str, body: Any = None) -> Any:
    return api.request("DELETE", path, json=body)


@pytest.fixture
def statements(api: TestClient) -> Iterator[list[str]]:
    """Every SQL statement the app executes while the fixture is active."""
    seen: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _many) -> None:  # noqa: ANN001
        seen.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", record)
    yield seen
    event.remove(engine, "before_cursor_execute", record)


# ---------------------------------------------------------------- migration + seed


def test_templates_are_seeded_with_the_spec_names(api: TestClient) -> None:
    templates = ok(api.get("/api/templates"))
    assert [template["key"] for template in templates] == list(SPEC_TEMPLATES)
    for template in templates:
        name, unions = SPEC_TEMPLATES[template["key"]]
        assert template["name"] == name
        assert [union["name"] for union in template["unions"]] == unions
        assert [ward["number"] for ward in template["wards"]] == list(range(1, 10))
        if template["key"] == "study":
            assert [ward["name"] for ward in template["wards"]] == SPEC_STUDY_WARDS
            assert [ward["responsibility"] for ward in template["wards"]] == SPEC_STUDY_WARDS
        else:  # no ward list in the SPEC: placeholders until the owner supplies names
            assert [ward["name"] for ward in template["wards"]] == [f"Ward {n}" for n in range(1, 10)]
            assert {ward["responsibility"] for ward in template["wards"]} == {""}


def test_nothing_is_generated_at_setup_and_one_central_office_exists(api: TestClient) -> None:
    assert db_counts() == {"upazila": 0, "union_unit": 0, "ward": 0, "office": 1}
    central = ok(api.get("/api/offices/central"))
    assert central["kind"] == "central" and central["ward_id"] is None
    assert central["name"] == "Central Administration"
    assert ok(api.get("/api/upazilas")) == []


def test_database_allows_only_one_central_office_and_enforces_kind(api: TestClient) -> None:
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(get_settings().db_file) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO office (kind, ward_id, name, description, created_at, updated_at) "
                "VALUES ('central', NULL, 'Second centre', '', ?, ?)",
                (now, now),
            )
        with pytest.raises(sqlite3.IntegrityError):  # a ward office needs a ward
            connection.execute(
                "INSERT INTO office (kind, ward_id, name, description, created_at, updated_at) "
                "VALUES ('ward', NULL, 'Orphan', '', ?, ?)",
                (now, now),
            )
        with pytest.raises(sqlite3.IntegrityError):  # unknown kind
            connection.execute(
                "INSERT INTO office (kind, ward_id, name, description, created_at, updated_at) "
                "VALUES ('branch', NULL, 'Other', '', ?, ?)",
                (now, now),
            )


def test_schema_version_and_revision_are_at_0003(migrated: Path) -> None:
    with sqlite3.connect(get_settings().db_file) as connection:
        version = connection.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()[0]
    assert version == "3"
    assert check()["current"] == check()["head"] == "0003"


def test_upgrade_from_0002_keeps_existing_data_and_downgrade_removes_only_m2(env: Path) -> None:
    config = alembic_config()
    command.upgrade(config, "0002")
    db_file = get_settings().db_file
    with sqlite3.connect(db_file) as connection:
        connection.execute(
            "INSERT INTO village (name, chairman_name, timezone, ai_mode, default_structure, created_at) "
            "VALUES ('Old Village', 'Riyan', 'Asia/Dhaka', 'demo', 'standard', '2026-01-01 00:00:00')"
        )
        connection.execute(
            "INSERT INTO admin_user (username, password_hash, created_at) VALUES ('chairman', 'hash', '2026-01-01 00:00:00')"
        )
    command.upgrade(config, "head")
    with sqlite3.connect(db_file) as connection:
        assert connection.execute("SELECT name, chairman_name FROM village").fetchall() == [("Old Village", "Riyan")]
        assert connection.execute("SELECT username, password_hash FROM admin_user").fetchall() == [("chairman", "hash")]
        assert connection.execute("SELECT COUNT(*) FROM upazila_template").fetchone()[0] == len(SPEC_TEMPLATES)
        assert connection.execute("SELECT COUNT(*) FROM upazila").fetchone()[0] == 0
    command.downgrade(config, "0002")
    with sqlite3.connect(db_file) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not tables & {"upazila_template", "union_template", "ward_template", *ORG_TABLES}
        assert connection.execute("SELECT name FROM village").fetchall() == [("Old Village",)]
        assert connection.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()[0] == "2"


def test_models_match_the_migrations(migrated: Path) -> None:
    """The typed models and the hand-written migrations describe the same schema."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db import Base

    with get_engine().connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


# ---------------------------------------------------------------- upazila CRUD


def test_upazila_crud_happy_path(api: TestClient) -> None:
    created = make_upazila(api, "  Garden  ", description="  Plants and trees ", icon="store")
    assert created["name"] == "Garden"  # trimmed
    assert created["description"] == "Plants and trees"
    assert created["icon"] == "store"
    assert created["template_key"] is None
    assert created["counts"] == {"unions": 0, "wards": 0, "offices": 0}

    assert [row["name"] for row in ok(api.get("/api/upazilas"))] == ["Garden"]
    assert ok(api.get(f"/api/upazilas/{created['id']}"))["name"] == "Garden"

    patched = ok(api.patch(f"/api/upazilas/{created['id']}", json={"name": " Orchard ", "description": ""}))
    assert patched["name"] == "Orchard" and patched["description"] == "" and patched["icon"] == "store"

    removed = ok(delete(api, f"/api/upazilas/{created['id']}", {"confirm_name": "Orchard"}))
    assert removed["deleted"] is True
    assert ok(api.get("/api/upazilas")) == []
    assert api.get(f"/api/upazilas/{created['id']}").status_code == 404


def test_upazila_from_a_template_takes_the_template_icon(api: TestClient) -> None:
    upazila = make_upazila(api, "My studies", template_key="study")
    assert upazila["template_key"] == "study" and upazila["icon"] == "graduation-cap"
    assert api.post("/api/upazilas", json={"name": "X", "template_key": "nope"}).status_code == 404
    detached = ok(api.patch(f"/api/upazilas/{upazila['id']}", json={"template_key": None}))
    assert detached["template_key"] is None
    assert api.patch(f"/api/upazilas/{upazila['id']}", json={"template_key": "nope"}).status_code == 404


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_upazila_name_must_be_1_to_80_characters(api: TestClient, name: str) -> None:
    assert api.post("/api/upazilas", json={"name": name}).status_code == 422
    upazila = make_upazila(api)
    assert api.patch(f"/api/upazilas/{upazila['id']}", json={"name": name}).status_code == 422
    assert ok(api.get(f"/api/upazilas/{upazila['id']}"))["name"] == "Garden"


def test_upazila_accepts_exactly_80_characters_and_rejects_unknown_fields(api: TestClient) -> None:
    assert make_upazila(api, "x" * 80)["name"] == "x" * 80
    assert api.post("/api/upazilas", json={"name": "Y", "village_id": 9}).status_code == 422
    assert api.post("/api/upazilas", json={"name": "Y", "icon": "<script>"}).status_code == 422


def test_duplicate_upazila_name_is_409(api: TestClient) -> None:
    first = make_upazila(api, "Garden")
    assert api.post("/api/upazilas", json={"name": " Garden "}).status_code == 409
    second = make_upazila(api, "Orchard")
    assert api.patch(f"/api/upazilas/{second['id']}", json={"name": "Garden"}).status_code == 409
    # renaming to its own name is not a conflict
    assert ok(api.patch(f"/api/upazilas/{first['id']}", json={"name": "Garden"}))["name"] == "Garden"
    assert db_counts()["upazila"] == 2


def test_missing_upazila_is_404(api: TestClient) -> None:
    assert api.get("/api/upazilas/999").status_code == 404
    assert api.patch("/api/upazilas/999", json={"name": "X"}).status_code == 404
    assert delete(api, "/api/upazilas/999", {"confirm_name": "X"}).status_code == 404
    assert api.get("/api/upazilas/999/unions").status_code == 404
    assert api.post("/api/upazilas/999/unions", json={"name": "X"}).status_code == 404
    assert api.post("/api/upazilas/999/generate-standard").status_code == 404
    assert api.get("/api/upazilas/999/generate-standard/preview").status_code == 404


# ---------------------------------------------------------------- union CRUD


def test_union_crud_happy_path(api: TestClient) -> None:
    upazila = make_upazila(api)
    union = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": " North ", "description": "Top"}), 201)
    assert union["name"] == "North" and union["upazila_id"] == upazila["id"]
    assert union["counts"] == {"wards": 0, "offices": 0}

    ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "South"}), 201)
    assert [row["name"] for row in ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))] == ["North", "South"]

    patched = ok(api.patch(f"/api/unions/{union['id']}", json={"name": "Far North"}))
    assert patched["name"] == "Far North" and patched["description"] == "Top"
    assert ok(api.get(f"/api/unions/{union['id']}"))["name"] == "Far North"

    ok(delete(api, f"/api/unions/{union['id']}", {"confirm_name": "Far North"}))
    assert [row["name"] for row in ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))] == ["South"]


def test_duplicate_union_name_is_409_within_one_upazila_only(api: TestClient) -> None:
    first = make_upazila(api, "Garden")
    second = make_upazila(api, "Orchard")
    north = ok(api.post(f"/api/upazilas/{first['id']}/unions", json={"name": "North"}), 201)
    assert api.post(f"/api/upazilas/{first['id']}/unions", json={"name": "North"}).status_code == 409
    ok(api.post(f"/api/upazilas/{second['id']}/unions", json={"name": "North"}), 201)  # other Upazila: fine
    south = ok(api.post(f"/api/upazilas/{first['id']}/unions", json={"name": "South"}), 201)
    assert api.patch(f"/api/unions/{south['id']}", json={"name": "North"}).status_code == 409
    assert ok(api.patch(f"/api/unions/{north['id']}", json={"name": "North"}))["name"] == "North"
    assert api.post(f"/api/upazilas/{first['id']}/unions", json={"name": "x" * 81}).status_code == 422


def test_missing_union_is_404(api: TestClient) -> None:
    assert api.get("/api/unions/999").status_code == 404
    assert api.patch("/api/unions/999", json={"name": "X"}).status_code == 404
    assert delete(api, "/api/unions/999", {"confirm_name": "X"}).status_code == 404
    assert api.get("/api/unions/999/wards").status_code == 404
    assert api.post("/api/unions/999/wards", json={}).status_code == 404
    assert db_counts()["ward"] == 0


# ---------------------------------------------------------------- wards and offices


def test_adding_wards_uses_the_next_number_and_creates_an_office(api: TestClient) -> None:
    upazila = make_upazila(api)
    union = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "North"}), 201)
    wards_url = f"/api/unions/{union['id']}/wards"

    first = ok(api.post(wards_url), 201)  # no body at all
    assert (first["number"], first["name"], first["responsibility"]) == (1, "Ward 1", "")
    assert first["office"]["kind"] == "ward" and first["office"]["ward_id"] == first["id"]
    assert first["office"]["name"] == "Ward 1 Office"

    second = ok(api.post(wards_url, json={"name": " Seeds ", "responsibility": " Buy seeds "}), 201)
    assert (second["number"], second["name"], second["responsibility"]) == (2, "Seeds", "Buy seeds")
    assert second["office"]["name"] == "Seeds Office"

    # deleting ward 1 leaves a gap; the next ward still gets the number after the highest one
    ok(delete(api, f"/api/wards/{first['id']}", {"confirm_name": "Ward 1"}))
    third = ok(api.post(wards_url, json={}), 201)
    assert third["number"] == 3
    assert [ward["number"] for ward in ok(api.get(wards_url))] == [2, 3]
    assert ok(api.get(f"/api/unions/{union['id']}"))["counts"] == {"wards": 2, "offices": 2}
    assert ok(api.get(f"/api/upazilas/{upazila['id']}"))["counts"] == {"unions": 1, "wards": 2, "offices": 2}


def test_ward_and_office_can_be_edited(api: TestClient) -> None:
    upazila = make_upazila(api)
    union = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "North"}), 201)
    ward = ok(api.post(f"/api/unions/{union['id']}/wards", json={}), 201)

    # the automatic office name follows a ward rename ...
    renamed = ok(api.patch(f"/api/wards/{ward['id']}", json={"name": " Seeds ", "responsibility": "Buy seeds"}))
    assert (renamed["name"], renamed["responsibility"], renamed["number"]) == ("Seeds", "Buy seeds", 1)
    assert renamed["office"]["name"] == "Seeds Office"

    # ... but an office the owner renamed by hand keeps its name
    office_id = ward["office"]["id"]
    office = ok(api.patch(f"/api/offices/{office_id}", json={"name": " Seed Desk ", "description": "Room 2"}))
    assert (office["name"], office["description"]) == ("Seed Desk", "Room 2")
    again = ok(api.patch(f"/api/wards/{ward['id']}", json={"name": "Saplings"}))
    assert again["office"]["name"] == "Seed Desk"
    assert again["responsibility"] == "Buy seeds"  # untouched fields stay
    assert ok(api.get(f"/api/offices/{office_id}"))["name"] == "Seed Desk"
    assert ok(api.get(f"/api/wards/{ward['id']}"))["name"] == "Saplings"

    assert api.patch(f"/api/wards/{ward['id']}", json={"name": ""}).status_code == 422
    assert api.patch(f"/api/offices/{office_id}", json={"name": "x" * 81}).status_code == 422
    assert api.patch("/api/wards/999", json={"name": "X"}).status_code == 404
    assert api.patch("/api/offices/999", json={"name": "X"}).status_code == 404
    assert api.get("/api/offices/999").status_code == 404


def test_central_office_can_be_renamed(api: TestClient) -> None:
    central = ok(api.get("/api/offices/central"))
    ok(api.patch(f"/api/offices/{central['id']}", json={"name": "Chairman's Office", "description": "HQ"}))
    assert ok(api.get("/api/offices/central")) == {**central, "name": "Chairman's Office", "description": "HQ"}


# ---------------------------------------------------------------- deletes


@pytest.mark.parametrize("body", [None, {}, {"confirm_name": ""}, {"confirm_name": "study upazila"}, {"confirm_name": "Study"}])
def test_delete_needs_the_exact_name(api: TestClient, body: Any) -> None:
    upazila = study(api)
    ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    union = ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))[0]
    ward = ok(api.get(f"/api/unions/{union['id']}/wards"))[0]
    before = db_counts()
    for path in (f"/api/upazilas/{upazila['id']}", f"/api/unions/{union['id']}", f"/api/wards/{ward['id']}"):
        response = delete(api, path, body)
        assert response.status_code == 400, (path, response.text)
    assert db_counts() == before


def test_deletes_cascade_down_the_hierarchy(api: TestClient) -> None:
    upazila = study(api)
    other = make_upazila(api, "Garden")
    kept_union = ok(api.post(f"/api/upazilas/{other['id']}/unions", json={"name": "North"}), 201)
    ok(api.post(f"/api/unions/{kept_union['id']}/wards", json={}), 201)
    ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    assert db_counts() == {"upazila": 2, "union_unit": 6, "ward": 46, "office": 47}

    unions = ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))
    ward = ok(api.get(f"/api/unions/{unions[0]['id']}/wards"))[0]
    result = ok(delete(api, f"/api/wards/{ward['id']}", {"confirm_name": ward["name"]}))
    assert (result["wards"], result["offices"]) == (1, 1)
    assert db_counts() == {"upazila": 2, "union_unit": 6, "ward": 45, "office": 46}
    assert api.get(f"/api/offices/{ward['office']['id']}").status_code == 404

    result = ok(delete(api, f"/api/unions/{unions[0]['id']}", {"confirm_name": unions[0]["name"]}))
    assert (result["unions"], result["wards"], result["offices"]) == (1, 8, 8)
    assert db_counts() == {"upazila": 2, "union_unit": 5, "ward": 37, "office": 38}

    result = ok(delete(api, f"/api/upazilas/{upazila['id']}", {"confirm_name": "Study Upazila"}))
    assert (result["upazilas"], result["unions"], result["wards"], result["offices"]) == (1, 4, 36, 36)
    # the other Upazila and the central office are untouched
    assert db_counts() == {"upazila": 1, "union_unit": 1, "ward": 1, "office": 2}
    assert ok(api.get("/api/offices/central"))["kind"] == "central"


# ---------------------------------------------------------------- standard upazilas + generation


def test_standard_upazilas_are_created_once(api: TestClient) -> None:
    first = ok(api.post("/api/upazilas/standard"))
    assert [row["name"] for row in first["created"]] == [name for name, _unions in SPEC_TEMPLATES.values()]
    assert [row["template_key"] for row in first["created"]] == list(SPEC_TEMPLATES)
    assert first["skipped"] == []
    assert db_counts() == {"upazila": 6, "union_unit": 0, "ward": 0, "office": 1}  # no unions yet

    second = ok(api.post("/api/upazilas/standard"))
    assert second["created"] == []
    assert sorted(second["skipped"]) == sorted(name for name, _unions in SPEC_TEMPLATES.values())
    assert db_counts()["upazila"] == 6


def test_standard_upazilas_skip_names_that_already_exist(api: TestClient) -> None:
    mine = make_upazila(api, "Research Upazila")  # hand-made, no template
    result = ok(api.post("/api/upazilas/standard"))
    assert len(result["created"]) == 5 and result["skipped"] == ["Research Upazila"]
    assert ok(api.get(f"/api/upazilas/{mine['id']}"))["template_key"] is None


def test_generate_standard_structure_on_study(api: TestClient) -> None:
    upazila = study(api)
    url = f"/api/upazilas/{upazila['id']}/generate-standard"

    expected = {"unions_created": 5, "wards_created": 45, "offices_created": 45, "skipped": 0}
    assert ok(api.get(f"{url}/preview")) == expected
    assert db_counts() == {"upazila": 1, "union_unit": 0, "ward": 0, "office": 1}  # preview wrote nothing

    assert ok(api.post(url)) == expected
    assert db_counts() == {"upazila": 1, "union_unit": 5, "ward": 45, "office": 46}

    unions = ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))
    assert [union["name"] for union in unions] == SPEC_TEMPLATES["study"][1]
    for union in unions:
        assert union["counts"] == {"wards": 9, "offices": 9}
        wards = ok(api.get(f"/api/unions/{union['id']}/wards"))
        assert [ward["number"] for ward in wards] == list(range(1, 10))
        assert [ward["name"] for ward in wards] == SPEC_STUDY_WARDS
        assert [ward["responsibility"] for ward in wards] == SPEC_STUDY_WARDS
        assert [ward["office"]["name"] for ward in wards] == [f"{name} Office" for name in SPEC_STUDY_WARDS]
        assert {ward["office"]["kind"] for ward in wards} == {"ward"}

    # idempotent: the second run and its preview create nothing
    nothing = {"unions_created": 0, "wards_created": 0, "offices_created": 0, "skipped": 5}
    assert ok(api.get(f"{url}/preview")) == nothing
    assert ok(api.post(url)) == nothing
    assert db_counts() == {"upazila": 1, "union_unit": 5, "ward": 45, "office": 46}


def test_generate_only_adds_the_missing_unions(api: TestClient) -> None:
    upazila = study(api)
    mine = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "Course Learning"}), 201)
    ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "My own union"}), 201)
    result = ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    assert result == {"unions_created": 4, "wards_created": 36, "offices_created": 36, "skipped": 1}
    assert ok(api.get(f"/api/unions/{mine['id']}/wards")) == []  # the existing union was left untouched
    assert len(ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))) == 6


def test_generate_needs_a_template(api: TestClient) -> None:
    upazila = make_upazila(api, "Garden")
    assert api.post(f"/api/upazilas/{upazila['id']}/generate-standard").status_code == 400
    assert api.get(f"/api/upazilas/{upazila['id']}/generate-standard/preview").status_code == 400
    assert db_counts()["union_unit"] == 0


def test_generation_is_one_transaction(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure in the middle of a generation must leave nothing behind."""
    import app.api.org as org

    upazila = study(api)
    real = org.default_office_name
    calls = 0

    def explode_in_the_third_union(ward_name: str) -> str:
        nonlocal calls
        calls += 1
        if calls > 20:
            raise RuntimeError("boom")
        return real(ward_name)

    monkeypatch.setattr(org, "default_office_name", explode_in_the_third_union)
    with pytest.raises(RuntimeError, match="boom"):
        api.post(f"/api/upazilas/{upazila['id']}/generate-standard")
    assert calls > 20
    assert db_counts() == {"upazila": 1, "union_unit": 0, "ward": 0, "office": 1}

    monkeypatch.setattr(org, "default_office_name", real)
    assert ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))["unions_created"] == 5


# ---------------------------------------------------------------- template editing


def test_edited_templates_are_used_by_the_next_generation_only(api: TestClient) -> None:
    first = study(api)
    ok(api.post(f"/api/upazilas/{first['id']}/generate-standard"))

    template = next(item for item in ok(api.get("/api/templates")) if item["key"] == "study")
    union_template = template["unions"][0]
    ward_template = template["wards"][0]
    assert ok(api.patch(f"/api/templates/unions/{union_template['id']}", json={"name": " Campus Life "}))["name"] == "Campus Life"
    edited = ok(
        api.patch(f"/api/templates/wards/{ward_template['id']}", json={"name": "Timetable", "responsibility": "Weekly timetable"})
    )
    assert (edited["number"], edited["name"], edited["responsibility"]) == (1, "Timetable", "Weekly timetable")
    renamed = ok(api.patch("/api/templates/study", json={"name": "Learning Upazila", "description": "School work"}))
    assert renamed["name"] == "Learning Upazila" and renamed["description"] == "School work"
    assert renamed["unions"][0]["name"] == "Campus Life" and renamed["wards"][0]["name"] == "Timetable"

    # what already exists is unchanged
    old_unions = ok(api.get(f"/api/upazilas/{first['id']}/unions"))
    assert old_unions[0]["name"] == "Academic Management"
    assert ok(api.get(f"/api/unions/{old_unions[0]['id']}/wards"))[0]["name"] == "Class Routine"
    assert ok(api.get(f"/api/upazilas/{first['id']}"))["name"] == "Study Upazila"

    # a new Upazila generated from the template gets the new names
    second = make_upazila(api, "Second studies", template_key="study")
    ok(api.post(f"/api/upazilas/{second['id']}/generate-standard"))
    new_unions = ok(api.get(f"/api/upazilas/{second['id']}/unions"))
    assert [union["name"] for union in new_unions] == ["Campus Life", *SPEC_TEMPLATES["study"][1][1:]]
    first_ward = ok(api.get(f"/api/unions/{new_unions[0]['id']}/wards"))[0]
    assert (first_ward["name"], first_ward["responsibility"]) == ("Timetable", "Weekly timetable")
    assert first_ward["office"]["name"] == "Timetable Office"

    # and "create the standard Upazilas" uses the new template name
    created = ok(api.post("/api/upazilas/standard"))["created"]
    assert "Learning Upazila" in [row["name"] for row in created]


def test_template_edit_validation(api: TestClient) -> None:
    template = next(item for item in ok(api.get("/api/templates")) if item["key"] == "business")
    first, second = template["unions"][0], template["unions"][1]
    assert api.patch(f"/api/templates/unions/{second['id']}", json={"name": first["name"]}).status_code == 409
    assert api.patch("/api/templates/business", json={"name": "Study Upazila"}).status_code == 409
    assert api.patch("/api/templates/business", json={"name": "  "}).status_code == 422
    assert api.patch(f"/api/templates/unions/{first['id']}", json={"name": "x" * 81}).status_code == 422
    assert api.patch(f"/api/templates/wards/{template['wards'][0]['id']}", json={"name": ""}).status_code == 422
    assert api.patch("/api/templates/nope", json={"name": "X"}).status_code == 404
    assert api.patch("/api/templates/unions/999", json={"name": "X"}).status_code == 404
    assert api.patch("/api/templates/wards/999", json={"name": "X"}).status_code == 404
    unchanged = next(item for item in ok(api.get("/api/templates")) if item["key"] == "business")
    assert unchanged == template


# ---------------------------------------------------------------- stats + tree


def test_stats_overview_matches_the_database(api: TestClient) -> None:
    assert ok(api.get("/api/stats/overview")) == {"upazilas": 0, "unions": 0, "wards": 0, "offices": 1, "ward_offices": 0}
    ok(api.post("/api/upazilas/standard"))
    upazila = next(row for row in ok(api.get("/api/upazilas")) if row["template_key"] == "study")
    ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    extra = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "Extra"}), 201)
    ok(api.post(f"/api/unions/{extra['id']}/wards", json={}), 201)

    stats = ok(api.get("/api/stats/overview"))
    counts = db_counts()
    assert stats == {
        "upazilas": counts["upazila"],
        "unions": counts["union_unit"],
        "wards": counts["ward"],
        "offices": counts["office"],
        "ward_offices": counts["office"] - 1,
    }
    assert stats == {"upazilas": 6, "unions": 6, "wards": 46, "offices": 47, "ward_offices": 46}
    assert set(stats) == {"upazilas", "unions", "wards", "offices", "ward_offices"}  # no agent/task numbers yet


def test_org_tree_is_nested_with_correct_counts(api: TestClient) -> None:
    empty = ok(api.get("/api/org/tree"))
    assert empty["village"]["name"] == "Shantipur"
    assert empty["central_office"]["kind"] == "central"
    assert (empty["upazila_count"], empty["upazilas"]) == (0, [])
    assert empty["counts"] == {"unions": 0, "wards": 0, "offices": 0}

    ok(api.post("/api/upazilas/standard"))
    upazilas = ok(api.get("/api/upazilas"))
    study_id = next(row["id"] for row in upazilas if row["template_key"] == "study")
    business_id = next(row["id"] for row in upazilas if row["template_key"] == "business")
    ok(api.post(f"/api/upazilas/{study_id}/generate-standard"))
    union = ok(api.post(f"/api/upazilas/{business_id}/unions", json={"name": "Shop"}), 201)
    ok(api.post(f"/api/unions/{union['id']}/wards", json={"name": "Counter"}), 201)
    ok(api.post(f"/api/unions/{union['id']}/wards", json={}), 201)

    tree = ok(api.get("/api/org/tree"))
    assert tree["upazila_count"] == 6
    assert tree["counts"] == {"unions": 6, "wards": 47, "offices": 47}
    assert [node["name"] for node in tree["upazilas"]] == [name for name, _unions in SPEC_TEMPLATES.values()]
    by_id = {node["id"]: node for node in tree["upazilas"]}

    study_node = by_id[study_id]
    assert study_node["counts"] == {"unions": 5, "wards": 45, "offices": 45}
    assert [node["name"] for node in study_node["unions"]] == SPEC_TEMPLATES["study"][1]
    for union_node in study_node["unions"]:
        assert union_node["counts"] == {"wards": 9, "offices": 9}
        assert [ward["number"] for ward in union_node["wards"]] == list(range(1, 10))
        assert [ward["name"] for ward in union_node["wards"]] == SPEC_STUDY_WARDS
        assert all(ward["office"]["ward_id"] == ward["id"] for ward in union_node["wards"])

    business_node = by_id[business_id]
    assert business_node["counts"] == {"unions": 1, "wards": 2, "offices": 2}
    assert [ward["name"] for ward in business_node["unions"][0]["wards"]] == ["Counter", "Ward 2"]
    for node in tree["upazilas"]:
        if node["id"] not in (study_id, business_id):
            assert node["counts"] == {"unions": 0, "wards": 0, "offices": 0} and node["unions"] == []

    # the tree agrees with the flat endpoints
    assert {row["id"]: row["counts"] for row in upazilas} != {}  # sanity
    assert {row["id"]: row["counts"] for row in ok(api.get("/api/upazilas"))} == {
        node["id"]: node["counts"] for node in tree["upazilas"]
    }


def test_org_tree_and_lists_do_not_run_a_query_per_node(api: TestClient, statements: list[str]) -> None:
    def queries(path: str) -> int:
        statements.clear()
        ok(api.get(path))
        return len(statements)

    ok(api.post("/api/upazilas/standard"))
    upazilas = ok(api.get("/api/upazilas"))
    ok(api.post(f"/api/upazilas/{upazilas[0]['id']}/generate-standard"))
    small = {path: queries(path) for path in ("/api/org/tree", "/api/upazilas", "/api/templates", "/api/stats/overview")}

    for upazila in upazilas[1:]:
        ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    assert db_counts() == {"upazila": 6, "union_unit": 30, "ward": 270, "office": 271}
    large = {path: queries(path) for path in small}

    assert large == small  # six times the data, the same number of statements
    assert large["/api/org/tree"] <= 6  # 1 session lookup + 5
    assert large["/api/stats/overview"] == 2


# ---------------------------------------------------------------- auth


NEW_ROUTES = {
    ("GET", "/api/templates"),
    ("PATCH", "/api/templates/{key}"),
    ("PATCH", "/api/templates/unions/{union_template_id}"),
    ("PATCH", "/api/templates/wards/{ward_template_id}"),
    ("GET", "/api/upazilas"),
    ("POST", "/api/upazilas"),
    ("POST", "/api/upazilas/standard"),
    ("GET", "/api/upazilas/{upazila_id}"),
    ("PATCH", "/api/upazilas/{upazila_id}"),
    ("DELETE", "/api/upazilas/{upazila_id}"),
    ("GET", "/api/upazilas/{upazila_id}/generate-standard/preview"),
    ("POST", "/api/upazilas/{upazila_id}/generate-standard"),
    ("GET", "/api/upazilas/{upazila_id}/unions"),
    ("POST", "/api/upazilas/{upazila_id}/unions"),
    ("GET", "/api/unions/{union_id}"),
    ("PATCH", "/api/unions/{union_id}"),
    ("DELETE", "/api/unions/{union_id}"),
    ("GET", "/api/unions/{union_id}/wards"),
    ("POST", "/api/unions/{union_id}/wards"),
    ("GET", "/api/wards/{ward_id}"),
    ("PATCH", "/api/wards/{ward_id}"),
    ("DELETE", "/api/wards/{ward_id}"),
    ("GET", "/api/offices/central"),
    ("GET", "/api/offices/{office_id}"),
    ("PATCH", "/api/offices/{office_id}"),
    ("GET", "/api/org/tree"),
    ("GET", "/api/stats/overview"),
}


def test_every_m2_route_needs_a_session(api: TestClient) -> None:
    from app.security import PUBLIC_PATHS

    upazila = study(api)
    ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    before = db_counts()
    api.cookies.clear()

    routes = api_routes(api.app)
    assert NEW_ROUTES <= routes
    # nothing M2 added is public, and nothing was added that this test does not know about
    m1_routes = {("GET", "/api/village"), ("GET", "/api/auth/me"), ("POST", "/api/auth/logout")}
    assert {route for route in routes if route[1] not in PUBLIC_PATHS} == NEW_ROUTES | m1_routes
    for method, template in sorted(NEW_ROUTES):
        path = re.sub(r"\{key\}", "study", template)
        path = re.sub(r"\{\w+\}", "1", path)  # real ids, so a missing guard would really act
        body = None if method == "GET" else {"name": "Hacked", "confirm_name": "Study Upazila"}
        response = api.request(method, path, json=body)
        assert response.status_code == 401, (method, path, response.text)
    assert db_counts() == before


# ---------------------------------------------------------------- concurrency


def test_concurrent_generation_and_ward_adds_do_not_duplicate_or_fail(api: TestClient) -> None:
    """Parallel requests wait for SQLite's write lock instead of racing on the same state."""
    from concurrent.futures import ThreadPoolExecutor

    upazila = study(api)
    extra = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "Extra"}), 201)

    def generate(_index: int) -> Any:
        return api.post(f"/api/upazilas/{upazila['id']}/generate-standard")

    def add_ward(_index: int) -> Any:
        return api.post(f"/api/unions/{extra['id']}/wards", json={})

    with ThreadPoolExecutor(max_workers=6) as pool:
        generated = list(pool.map(generate, range(6)))
        added = list(pool.map(add_ward, range(6)))

    assert [response.status_code for response in generated] == [200] * 6
    assert sorted(response.json()["unions_created"] for response in generated) == [0, 0, 0, 0, 0, 5]
    assert [response.status_code for response in added] == [201] * 6
    assert sorted(response.json()["number"] for response in added) == [1, 2, 3, 4, 5, 6]
    assert db_counts() == {"upazila": 1, "union_unit": 6, "ward": 51, "office": 52}

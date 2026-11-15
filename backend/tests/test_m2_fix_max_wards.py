"""DEV-M2-FIX-01: a Union may hold at most MAX_WARDS_PER_UNION (9) wards."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.limits import MAX_WARDS_PER_UNION
from tests.test_m2_org import api, db_counts, delete, make_upazila, ok, study  # noqa: F401  (api is a fixture)


def union_with_wards(api: TestClient, count: int) -> tuple[dict[str, Any], str]:  # noqa: F811
    upazila = make_upazila(api)
    union = ok(api.post(f"/api/upazilas/{upazila['id']}/unions", json={"name": "North"}), 201)
    url = f"/api/unions/{union['id']}/wards"
    for _ in range(count):
        ok(api.post(url, json={}), 201)
    return union, url


def test_the_limit_is_nine_and_is_sent_to_the_frontend(api: TestClient) -> None:  # noqa: F811
    assert MAX_WARDS_PER_UNION == 9
    assert ok(api.get("/api/org/tree"))["max_wards_per_union"] == 9
    assert {template["max_wards"] for template in ok(api.get("/api/templates"))} == {9}


def test_ninth_ward_is_ok_and_tenth_is_409(api: TestClient) -> None:  # noqa: F811
    _union, url = union_with_wards(api, 8)
    ninth = ok(api.post(url, json={}), 201)
    assert ninth["number"] == 9
    response = api.post(url, json={"name": "Tenth"})
    assert response.status_code == 409
    assert response.json()["detail"] == "A Union can have at most 9 wards. Delete a ward before adding another."
    assert len(ok(api.get(url))) == 9
    assert db_counts()["ward"] == 9 and db_counts()["office"] == 10  # 9 ward offices + central


def test_delete_then_add_is_ok(api: TestClient) -> None:  # noqa: F811
    _union, url = union_with_wards(api, 9)
    wards = ok(api.get(url))
    ok(delete(api, f"/api/wards/{wards[3]['id']}", {"confirm_name": wards[3]["name"]}))
    added = ok(api.post(url, json={}), 201)
    assert added["number"] == 10  # numbers keep counting; the COUNT is what is limited
    assert len(ok(api.get(url))) == 9
    assert api.post(url, json={}).status_code == 409


def test_limit_applies_to_a_generated_union_too(api: TestClient) -> None:  # noqa: F811
    upazila = study(api)
    ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    union = ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))[0]
    assert api.post(f"/api/unions/{union['id']}/wards", json={}).status_code == 409


def test_template_with_ten_ward_names_is_422_and_nothing_changes(api: TestClient) -> None:  # noqa: F811
    before = next(item for item in ok(api.get("/api/templates")) if item["key"] == "study")
    ten = [{"name": f"Ward {number}"} for number in range(1, 11)]
    assert api.put("/api/templates/study/wards", json={"wards": ten}).status_code == 422
    assert api.put("/api/templates/study/wards", json={"wards": []}).status_code == 422
    assert api.put("/api/templates/study/wards", json={"wards": [{"name": " "}]}).status_code == 422
    assert api.put("/api/templates/nope/wards", json={"wards": [{"name": "X"}]}).status_code == 404
    assert next(item for item in ok(api.get("/api/templates")) if item["key"] == "study") == before


def test_template_ward_set_can_shrink_and_grow_up_to_nine(api: TestClient) -> None:  # noqa: F811
    before = next(item for item in ok(api.get("/api/templates")) if item["key"] == "study")
    names = [{"name": ward["name"], "responsibility": ward["responsibility"]} for ward in before["wards"]]

    shrunk = ok(api.put("/api/templates/study/wards", json={"wards": names[:8]}))
    assert [ward["number"] for ward in shrunk["wards"]] == list(range(1, 9))
    assert [ward["id"] for ward in shrunk["wards"]] == [ward["id"] for ward in before["wards"][:8]]  # kept in place

    grown = ok(api.put("/api/templates/study/wards", json={"wards": [*names[:8], {"name": " New Ninth "}]}))
    assert len(grown["wards"]) == 9 and grown["wards"][8]["name"] == "New Ninth"
    assert grown["wards"][8]["number"] == 9


def test_generation_never_exceeds_nine_wards_per_union(api: TestClient) -> None:  # noqa: F811
    # Even a template that somehow holds more than nine rows (inserted behind the API's back)
    # only gives each generated Union the first nine.
    import sqlite3

    from app.config import get_settings

    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute(
            "INSERT INTO ward_template (upazila_template_key, number, name, responsibility, created_at, updated_at)"
            " VALUES ('study', 10, 'Too Many', '', '2026-01-01', '2026-01-01')"
        )
    upazila = study(api)
    preview = ok(api.get(f"/api/upazilas/{upazila['id']}/generate-standard/preview"))
    assert preview["wards_created"] == 5 * 9
    result = ok(api.post(f"/api/upazilas/{upazila['id']}/generate-standard"))
    assert result["wards_created"] == 5 * 9
    for union in ok(api.get(f"/api/upazilas/{upazila['id']}/unions")):
        wards = ok(api.get(f"/api/unions/{union['id']}/wards"))
        assert len(wards) == 9 and "Too Many" not in [ward["name"] for ward in wards]
    assert max(union["counts"]["wards"] for union in ok(api.get(f"/api/upazilas/{upazila['id']}/unions"))) == 9

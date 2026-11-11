"""Part C: FastAPI serves the built frontend (static files + SPA fallback) from a tmp dist."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

INDEX_HTML = '<!doctype html><html><body><div id="root">village-test-index</div></body></html>'


@pytest.fixture
def dist(migrated: Path) -> Path:
    """A fake build in the temp dir that VILLAGE_FRONTEND_DIST points to."""
    dist_dir = migrated / "dist"
    (dist_dir / "assets").mkdir(parents=True)
    (dist_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist_dir / "assets" / "app-abc123.js").write_text("console.log('village');", encoding="utf-8")
    (dist_dir / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (migrated / "secret.txt").write_text("outside-dist-secret", encoding="utf-8")
    return dist_dir


def test_root_serves_index_html(dist: Path, client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "village-test-index" in response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("path", ["/setup", "/login", "/tasks", "/agents/profile", "/some/unknown/page"])
def test_spa_fallback_serves_index_for_client_routes(dist: Path, client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "village-test-index" in response.text


def test_static_assets_are_served_with_long_cache(dist: Path, client: TestClient) -> None:
    response = client.get("/assets/app-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log('village');"
    assert "javascript" in response.headers["content-type"]
    assert "immutable" in response.headers["cache-control"]

    favicon = client.get("/favicon.svg")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")


def test_missing_asset_is_404_not_index(dist: Path, client: TestClient) -> None:
    response = client.get("/assets/missing.js")
    assert response.status_code == 404
    assert "village-test-index" not in response.text


@pytest.mark.parametrize("path", ["/api/nope", "/api", "/api/setup/unknown"])
def test_unknown_api_paths_are_json_404_not_index(dist: Path, client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "village-test-index" not in response.text


def test_api_still_works_next_to_the_frontend(dist: Path, client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/village").status_code == 401


@pytest.mark.parametrize("path", ["/%2e%2e/secret.txt", "/assets/%2e%2e/%2e%2e/secret.txt", "/..%2fsecret.txt"])
def test_path_traversal_cannot_escape_dist(dist: Path, client: TestClient, path: str) -> None:
    response = client.get(path)
    assert "outside-dist-secret" not in response.text


def test_head_request_on_root(dist: Path, client: TestClient) -> None:
    assert client.head("/").status_code == 200


def test_missing_dist_shows_setup_hint(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 503
    assert "./village setup" in response.text
    assert client.get("/api/health").status_code == 200  # the API is unaffected

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


# ---------------------------------------------------------------- installable app (DEV-APP-01)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@pytest.fixture
def pwa_dist(dist: Path) -> Path:
    """The fake build plus the real PWA files from frontend/public."""
    import shutil

    for name in ("sw.js", "manifest.webmanifest", "offline.html"):
        shutil.copy(FRONTEND / "public" / name, dist / name)
    shutil.copytree(FRONTEND / "public" / "icons", dist / "icons")
    return dist


def test_service_worker_is_served_from_the_root_as_javascript_and_never_cached(pwa_dist: Path, client: TestClient) -> None:
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "text/javascript"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "village-shell-" in response.text
    assert "service-worker-allowed" not in response.headers  # served from the root: scope "/" needs no override


def test_manifest_is_served_from_the_root_with_the_manifest_type(pwa_dist: Path, client: TestClient) -> None:
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "application/manifest+json"
    assert response.headers["cache-control"] == "no-cache"
    manifest = response.json()
    assert (manifest["name"], manifest["short_name"]) == ("AI Agent Village", "Village")
    assert (manifest["start_url"], manifest["scope"], manifest["display"]) == ("/", "/", "standalone")
    sizes = {(icon["sizes"], icon["purpose"]) for icon in manifest["icons"]}
    assert sizes == {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")}
    for icon in manifest["icons"]:  # every icon the manifest names is really served, as a PNG of that size
        png = client.get(icon["src"])
        assert png.status_code == 200 and png.headers["content-type"] == "image/png"
        assert png.content[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = int.from_bytes(png.content[16:20], "big"), int.from_bytes(png.content[20:24], "big")
        assert f"{width}x{height}" == icon["sizes"]


def test_offline_page_and_apple_icon_are_served(pwa_dist: Path, client: TestClient) -> None:
    offline = client.get("/offline.html")
    assert offline.status_code == 200 and offline.headers["content-type"].startswith("text/html")
    assert "Village is unreachable" in offline.text and "Tailscale is connected" in offline.text
    assert offline.headers["cache-control"] == "no-cache"
    assert client.get("/icons/apple-touch-icon.png").headers["content-type"] == "image/png"


def test_pwa_files_need_no_session_but_the_api_still_does(pwa_dist: Path, client: TestClient) -> None:
    for path in ("/sw.js", "/manifest.webmanifest", "/offline.html", "/icons/icon-192.png"):
        assert client.get(path).status_code == 200
    assert client.get("/api/village").status_code == 401
    csp = client.get("/").headers["content-security-policy"]
    assert "worker-src 'self'" in csp and "manifest-src 'self'" in csp and "default-src 'self'" in csp


def test_service_worker_source_never_caches_the_api() -> None:
    """Reads frontend/public/sw.js: the API is skipped before any response is produced, and
    nothing is written to a cache at run time."""
    source = (FRONTEND / "public" / "sw.js").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith(("//", "*", "/*")))
    assert ".put(" not in code and ".add(" not in code
    assert code.count("addAll(") == 1 and 'credentials: "omit"' in code  # the precache, fetched without cookies
    guard = code.index("if (isApi(url.pathname)) return;")
    assert guard < code.index("event.respondWith(")
    assert 'pathname === "/api" || pathname.startsWith("/api/")' in code
    precache = source[source.index("/* BUILD:BEGIN") : source.index("/* BUILD:END */")]
    assert "/api" not in precache


def test_index_html_links_the_manifest_theme_colour_and_touch_icon() -> None:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert '<link rel="manifest" href="/manifest.webmanifest" />' in html
    assert '<meta name="theme-color" content="#060b0a" />' in html
    assert '<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />' in html
    assert "viewport-fit=cover" in html

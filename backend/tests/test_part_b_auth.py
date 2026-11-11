"""Part B: first-run setup API, admin auth, sessions, lockout, and secret hygiene."""

from __future__ import annotations

import hashlib
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import env_file_path, get_settings
from app.security import SESSION_COOKIE, LoginRateLimiter
from tests.conftest import BASE_URL, TEST_SECRET_KEY

PASSWORD = "correct horse battery"
API_KEY = "sk-ant-api03-TESTKEY_abcdefghijklmnopqrstuvwxyz-0123456789"


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "village_name": "Shantipur",
        "chairman_name": "Riyan",
        "username": "chairman",
        "password": PASSWORD,
        "timezone": "Asia/Dhaka",
        "ai_mode": "demo",
        "default_structure": "standard",
    }
    body.update(overrides)
    return body


def do_setup(client: TestClient, **overrides: Any) -> Any:
    response = client.post("/api/setup", json=payload(**overrides))
    assert response.status_code == 201, response.text
    return response


def api_routes(app: Any) -> set[tuple[str, str]]:
    """All registered (METHOD, /api path) pairs (newer FastAPI nests included routers)."""
    try:
        from fastapi.routing import iter_route_contexts

        items: list[Any] = list(iter_route_contexts(app.routes))
    except ImportError:
        items = list(app.routes)
    found: set[tuple[str, str]] = set()
    for item in items:
        path = getattr(item, "path", None) or ""
        if path.startswith("/api/"):
            found.update((method, path) for method in (getattr(item, "methods", None) or ()) if method != "HEAD")
    return found


def db_dump(db_file: Path) -> str:
    """Every value of every table plus the raw bytes of the database files."""
    parts: list[str] = []
    with sqlite3.connect(db_file) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for row in connection.execute(f'SELECT * FROM "{table}"'):
                parts.append(repr(row))
    for suffix in ("", "-wal"):
        candidate = Path(str(db_file) + suffix)
        if candidate.exists():
            parts.append(candidate.read_bytes().decode("latin-1"))
    return "\n".join(parts)


# ---------------------------------------------------------------- setup


def test_setup_status_starts_false(client: TestClient) -> None:
    assert client.get("/api/setup/status").json() == {"setup_completed": False}


def test_setup_success_creates_village_admin_and_session(client: TestClient) -> None:
    response = do_setup(client)
    body = response.json()
    assert body["setup_completed"] is True
    assert body["username"] == "chairman"
    assert body["anthropic_api_key"] == "not provided"
    assert body["village"]["name"] == "Shantipur"
    assert body["village"]["chairman_name"] == "Riyan"
    assert body["village"]["timezone"] == "Asia/Dhaka"
    assert body["village"]["ai_mode"] == "demo"
    assert body["village"]["default_structure"] == "standard"
    assert PASSWORD not in response.text

    cookie = response.headers["set-cookie"]
    lowered = cookie.lower()
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert "path=/" in lowered
    assert "max-age=604800" in lowered
    assert "secure" not in lowered

    assert client.get("/api/setup/status").json() == {"setup_completed": True}
    assert client.get("/api/health").json()["setup_completed"] is True
    # setup also logs the admin in
    assert client.get("/api/auth/me").json()["username"] == "chairman"
    assert client.get("/api/village").json()["name"] == "Shantipur"


def test_second_setup_is_rejected_with_409(client: TestClient) -> None:
    do_setup(client)
    response = client.post("/api/setup", json=payload(village_name="Other", username="intruder"))
    assert response.status_code == 409
    with sqlite3.connect(get_settings().db_file) as connection:
        assert connection.execute("SELECT count(*) FROM village").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM admin_user").fetchone()[0] == 1


def test_weak_password_is_rejected_and_not_echoed(client: TestClient) -> None:
    response = client.post("/api/setup", json=payload(password="short-pw9"))
    assert response.status_code == 422
    assert "short-pw9" not in response.text
    assert any(error["loc"] == ["body", "password"] for error in response.json()["detail"])
    assert client.get("/api/setup/status").json() == {"setup_completed": False}


@pytest.mark.parametrize("timezone", ["Mars/Olympus_Mons", "", "../../etc/passwd", "Asia/Dhaka; DROP"])
def test_bad_timezone_is_rejected(client: TestClient, timezone: str) -> None:
    response = client.post("/api/setup", json=payload(timezone=timezone))
    assert response.status_code == 422
    assert any(error["loc"] == ["body", "timezone"] for error in response.json()["detail"])


def test_timezone_defaults_to_asia_dhaka(client: TestClient) -> None:
    body = payload()
    del body["timezone"]
    response = client.post("/api/setup", json=body)
    assert response.status_code == 201
    assert response.json()["village"]["timezone"] == "Asia/Dhaka"


@pytest.mark.parametrize(
    "overrides",
    [
        {"village_name": "   "},
        {"chairman_name": ""},
        {"username": "a"},
        {"username": "has space"},
        {"ai_mode": "gpt"},
        {"default_structure": "huge"},
        {"ai_mode": "ollama"},  # no URL
        {"ai_mode": "ollama", "ollama_url": "http://example.com:11434"},
        {"ai_mode": "ollama", "ollama_url": "https://127.0.0.1:11434"},
        {"ai_mode": "ollama", "ollama_url": "http://user:pw@127.0.0.1:11434"},
        {"ai_mode": "ollama", "ollama_url": "http://127.0.0.1.evil.com:11434"},
        {"ai_mode": "anthropic"},  # no key anywhere
        {"unexpected_field": 1},
    ],
)
def test_invalid_setup_payloads_are_rejected(client: TestClient, overrides: dict[str, Any]) -> None:
    response = client.post("/api/setup", json=payload(**overrides))
    assert response.status_code == 422, response.text
    assert client.get("/api/setup/status").json() == {"setup_completed": False}


def test_setup_with_local_ollama_url_is_stored(client: TestClient) -> None:
    response = do_setup(client, ai_mode="ollama", ollama_url="http://localhost:11434/")
    assert response.json()["village"]["ai_mode"] == "ollama"
    assert client.get("/api/village").json()["ollama_url"] == "http://localhost:11434"


def test_username_is_normalised_to_lowercase(client: TestClient) -> None:
    assert do_setup(client, username="  Chairman ").json()["username"] == "chairman"


def test_failed_env_write_rolls_the_whole_setup_back(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_key: str, _value: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("app.api.setup.save_env_value", boom)
    response = client.post("/api/setup", json=payload(ai_mode="anthropic", anthropic_api_key=API_KEY))
    assert response.status_code == 500
    assert API_KEY not in response.text
    assert "set-cookie" not in response.headers
    assert client.get("/api/setup/status").json() == {"setup_completed": False}
    with sqlite3.connect(get_settings().db_file) as connection:
        assert connection.execute("SELECT count(*) FROM village").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM admin_user").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM session").fetchone()[0] == 0


# ---------------------------------------------------------------- login / logout


def test_login_ok_and_bad(client: TestClient) -> None:
    do_setup(client)
    client.cookies.clear()

    bad = client.post("/api/auth/login", json={"username": "chairman", "password": "wrong password!"})
    assert bad.status_code == 401
    assert "set-cookie" not in bad.headers

    unknown = client.post("/api/auth/login", json={"username": "nobody", "password": PASSWORD})
    assert unknown.status_code == 401
    assert unknown.json() == bad.json()  # same message: no username oracle

    ok = client.post("/api/auth/login", json={"username": "Chairman", "password": PASSWORD})
    assert ok.status_code == 200
    assert ok.json()["username"] == "chairman"
    assert PASSWORD not in ok.text
    assert client.get("/api/auth/me").status_code == 200


def test_lockout_after_five_failures_returns_429(client: TestClient) -> None:
    do_setup(client)
    client.cookies.clear()
    for _ in range(5):
        response = client.post("/api/auth/login", json={"username": "chairman", "password": "wrong password!"})
        assert response.status_code == 401
    locked = client.post("/api/auth/login", json={"username": "chairman", "password": "wrong password!"})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    # even the right password is refused while locked out
    assert client.post("/api/auth/login", json={"username": "chairman", "password": PASSWORD}).status_code == 429


def test_successful_login_resets_the_failure_counter(client: TestClient) -> None:
    do_setup(client)
    client.cookies.clear()
    for _ in range(4):
        client.post("/api/auth/login", json={"username": "chairman", "password": "wrong password!"})
    assert client.post("/api/auth/login", json={"username": "chairman", "password": PASSWORD}).status_code == 200
    for _ in range(4):
        response = client.post("/api/auth/login", json={"username": "chairman", "password": "wrong password!"})
        assert response.status_code == 401


def test_rate_limiter_window_expires() -> None:
    now = [1000.0]
    limiter = LoginRateLimiter(max_failures=5, window_seconds=300, clock=lambda: now[0])
    for _ in range(5):
        assert limiter.retry_after("chairman") == 0
        limiter.record_failure("chairman")
    assert limiter.retry_after("chairman") > 0
    assert limiter.retry_after("someone-else") == 0
    now[0] += 299
    assert limiter.retry_after("chairman") > 0
    now[0] += 2
    assert limiter.retry_after("chairman") == 0


def test_logout_revokes_the_session(client: TestClient) -> None:
    do_setup(client)
    token = client.cookies.get(SESSION_COOKIE)
    assert token

    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").status_code == 401

    # replaying the old cookie must not work: the session is revoked server-side
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/village").status_code == 401
    with sqlite3.connect(get_settings().db_file) as connection:
        assert connection.execute("SELECT revoked_at FROM session").fetchone()[0] is not None


def test_expired_session_is_rejected(client: TestClient) -> None:
    do_setup(client)
    assert client.get("/api/auth/me").status_code == 200
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("UPDATE session SET expires_at = '2000-01-01 00:00:00.000000'")
    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------- auth guard


def test_protected_routes_need_a_session(client: TestClient) -> None:
    do_setup(client)
    client.cookies.clear()
    assert client.get("/api/village").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 401
    client.cookies.set(SESSION_COOKIE, "not-a-real-token")
    assert client.get("/api/village").status_code == 401


def test_public_routes_work_without_a_session(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/setup/status").status_code == 200


def test_every_api_route_is_guarded_unless_allowlisted(client: TestClient) -> None:
    """Default-deny: any /api route that is not on the public allowlist answers 401."""
    from app.security import PUBLIC_PATHS

    do_setup(client)
    client.cookies.clear()
    routes = api_routes(client.app)
    assert PUBLIC_PATHS <= {path for _method, path in routes}
    protected = sorted(route for route in routes if route[1] not in PUBLIC_PATHS)
    assert ("GET", "/api/village") in protected
    for method, path in protected:
        response = client.request(method, path, json={} if method != "GET" else None)
        assert response.status_code == 401, (method, path)


def test_cross_origin_writes_and_foreign_hosts_are_rejected(client: TestClient) -> None:
    evil = client.post("/api/setup", json=payload(), headers={"Origin": "http://127.0.0.1:9999"})
    assert evil.status_code == 403
    assert client.get("/api/setup/status").json() == {"setup_completed": False}

    same = client.post("/api/setup", json=payload(), headers={"Origin": BASE_URL})
    assert same.status_code == 201

    rebind = client.get("/api/health", headers={"Host": "attacker.example:8000"})
    assert rebind.status_code == 400


# ---------------------------------------------------------------- secret hygiene


def test_api_key_is_saved_to_env_only_and_never_returned(client: TestClient) -> None:
    setup = do_setup(client, ai_mode="anthropic", anthropic_api_key=API_KEY)
    assert setup.json()["anthropic_api_key"] == "saved, not tested"

    responses = [
        setup,
        client.get("/api/village"),
        client.get("/api/auth/me"),
        client.get("/api/health"),
        client.get("/api/setup/status"),
        client.post("/api/setup", json=payload(anthropic_api_key=API_KEY)),  # 409
        client.post("/api/auth/logout"),
        client.post("/api/auth/login", json={"username": "chairman", "password": PASSWORD}),
    ]
    for response in responses:
        assert API_KEY not in response.text
        assert API_KEY not in str(response.headers)
        assert TEST_SECRET_KEY not in response.text

    village = client.get("/api/village").json()
    assert village["anthropic_key_configured"] is True
    assert not any("key" in name and name != "anthropic_key_configured" for name in village)

    # never in the database
    assert API_KEY not in db_dump(get_settings().db_file)

    # in the secrets file, which keeps mode 600 and its existing content
    env_file = env_file_path()
    content = env_file.read_text(encoding="utf-8")
    assert f"VILLAGE_ANTHROPIC_API_KEY={API_KEY}" in content.splitlines()
    assert f"VILLAGE_SECRET_KEY={TEST_SECRET_KEY}" in content.splitlines()
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    # the running app now reports that it is no longer in Demo Mode
    assert client.get("/api/health").json()["demo_mode"] is False


@pytest.mark.parametrize("bad_key", ["sk-ant with spaces 0123456789abcdef", "sk-ant-0123456789abcdef\nEVIL=1", "short"])
def test_malformed_api_key_is_rejected_and_not_echoed(client: TestClient, bad_key: str) -> None:
    before = env_file_path().read_text(encoding="utf-8")
    response = client.post("/api/setup", json=payload(ai_mode="anthropic", anthropic_api_key=bad_key))
    assert response.status_code == 422
    assert bad_key not in response.text
    assert "EVIL" not in response.text
    assert env_file_path().read_text(encoding="utf-8") == before


def test_password_is_stored_only_as_an_argon2_hash(client: TestClient) -> None:
    do_setup(client)
    with sqlite3.connect(get_settings().db_file) as connection:
        stored = connection.execute("SELECT password_hash FROM admin_user").fetchone()[0]
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in db_dump(get_settings().db_file)


def test_session_token_is_stored_only_as_sha256(client: TestClient) -> None:
    do_setup(client)
    token = client.cookies.get(SESSION_COOKIE)
    assert token and len(token) >= 43  # secrets.token_urlsafe(32)
    with sqlite3.connect(get_settings().db_file) as connection:
        stored = connection.execute("SELECT token_hash FROM session").fetchone()[0]
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert token not in db_dump(get_settings().db_file)

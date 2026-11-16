"""DEV-APP-01 Part B: allowed hosts, forwarded headers, Secure cookie, persistent lockout,
devices & sessions, the bind check of `./village doctor`.

Tailscale itself is not part of these tests: the proxy is imitated by a client whose TCP peer
is 127.0.0.1 and that sends the headers a local reverse proxy adds.
"""

from __future__ import annotations

import logging
import socket
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import bindcheck
from app.config import ROOT_DIR, get_settings, normalise_allowed_host
from app.db import reset_engine
from app.dbcheck import alembic_config, check
from app.security import SESSION_COOKIE, device_label
from tests.conftest import BASE_URL
from tests.test_part_b_auth import PASSWORD, api_routes, do_setup, payload

TAILNET_HOST = "my-pc.tail1234.ts.net"
TAILNET_ORIGIN = f"https://{TAILNET_HOST}"
ANDROID_CHROME = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
LINUX_CHROME = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
LOGIN = {"username": "chairman", "password": PASSWORD}
WRONG = {"username": "chairman", "password": "wrong password!"}


def rows(sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with sqlite3.connect(get_settings().db_file) as connection:
        return connection.execute(sql, params).fetchall()


def allow(monkeypatch: pytest.MonkeyPatch, hosts: str) -> None:
    monkeypatch.setenv("VILLAGE_ALLOWED_HOSTS", hosts)
    get_settings.cache_clear()


def proxied(app: Any, **headers: str) -> TestClient:
    """A client that looks like the local Tailscale proxy: its TCP peer is 127.0.0.1."""
    return TestClient(app, base_url=BASE_URL, client=("127.0.0.1", 40123), headers=headers)


def device(app: Any, user_agent: str) -> TestClient:
    """Another browser talking to the same app (direct, on this PC)."""
    return TestClient(app, base_url=BASE_URL, headers={"User-Agent": user_agent})


def cookie_flags(response: Any) -> set[str]:
    header = response.headers["set-cookie"]
    assert header.startswith(f"{SESSION_COOKIE}=")
    return {part.strip().split("=")[0].lower() for part in header.split(";")[1:]} | {
        part.strip().lower() for part in header.split(";")[1:] if "samesite" in part.lower()
    }


# ---------------------------------------------------------------- VILLAGE_ALLOWED_HOSTS


def test_default_allows_loopback_names_only(client: TestClient) -> None:
    assert get_settings().allowed_hosts == "127.0.0.1,localhost"
    assert get_settings().allowed_hostnames == {"127.0.0.1", "localhost", "[::1]"}
    for host in ("127.0.0.1:8000", "localhost:8000", "LOCALHOST", "[::1]:8000", "127.0.0.1"):
        assert client.get("/api/health", headers={"Host": host}).status_code == 200, host
    for host in (f"{TAILNET_HOST}", "attacker.example:8000", "127.0.0.1.evil.example", "evil.localhost", "192.168.1.20:8000", ""):
        response = client.get("/api/health", headers={"Host": host})
        assert response.status_code == 400, host
        assert response.json() == {"detail": "Invalid Host header"}
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400  # the frontend too


def test_allowlisted_tailscale_host_is_accepted_and_everything_else_still_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    allow(monkeypatch, f"127.0.0.1,localhost,{TAILNET_HOST}")
    assert client.get("/api/health", headers={"Host": TAILNET_HOST}).status_code == 200
    assert client.get("/api/health", headers={"Host": f"{TAILNET_HOST.upper()}:443"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200
    for host in ("other-pc.tail1234.ts.net", f"evil.{TAILNET_HOST}", f"{TAILNET_HOST}.evil.example", "attacker.example"):
        assert client.get("/api/health", headers={"Host": host}).status_code == 400, host


def test_loopback_stays_allowed_even_when_the_setting_names_only_the_remote_host(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    allow(monkeypatch, TAILNET_HOST)  # the owner forgot to keep localhost in the list
    assert get_settings().allowed_hostnames == {TAILNET_HOST, "127.0.0.1", "localhost", "[::1]"}
    assert client.get("/api/health").status_code == 200  # still not locked out of the PC itself


@pytest.mark.parametrize(
    ("written", "meant"),
    [
        ("my-pc.tail1234.ts.net", "my-pc.tail1234.ts.net"),
        ("  My-PC.Tail1234.ts.net  ", "my-pc.tail1234.ts.net"),
        ("https://my-pc.tail1234.ts.net/", "my-pc.tail1234.ts.net"),
        ("my-pc.tail1234.ts.net:443", "my-pc.tail1234.ts.net"),
        ("[my-pc.tail1234.ts.net]", "my-pc.tail1234.ts.net"),  # brackets copied from an example
        ("my-pc.tail1234.ts.net.", "my-pc.tail1234.ts.net"),
        ("[::1]:8000", "[::1]"),
        ("100.101.102.103", "100.101.102.103"),
    ],
)
def test_allowed_host_entries_are_normalised(written: str, meant: str) -> None:
    assert normalise_allowed_host(written) == meant


@pytest.mark.parametrize("bad", ["*", "*.ts.net", "my pc.ts.net", "https://", "-bad-.ts.net", "a..b", "[not-ipv6::zz]"])
def test_bad_allowed_hosts_are_a_configuration_error(env: Path, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv("VILLAGE_ALLOWED_HOSTS", f"127.0.0.1,{bad}")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_allowed_hosts_can_come_from_the_env_file(env: Path) -> None:
    env_file = env / ".env"
    env_file.write_text(env_file.read_text() + f"VILLAGE_ALLOWED_HOSTS=127.0.0.1,localhost,{TAILNET_HOST},{TAILNET_HOST}\n")
    get_settings.cache_clear()
    assert get_settings().allowed_hosts == f"127.0.0.1,localhost,{TAILNET_HOST}"  # the duplicate is dropped


# ---------------------------------------------------------------- forwarded headers


def test_forwarded_headers_are_ignored_when_the_peer_is_not_this_pc(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    allow(monkeypatch, f"127.0.0.1,localhost,{TAILNET_HOST}")
    # this client's TCP peer is "testclient", not 127.0.0.1
    lying = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": TAILNET_HOST}
    created = client.post("/api/setup", json=payload(), headers=lying)
    assert created.status_code == 201
    assert "secure" not in cookie_flags(created)  # X-Forwarded-Proto was not believed
    # X-Forwarded-Host was not believed either: the origin is still compared with Host
    assert client.post("/api/auth/logout", headers={**lying, "Origin": TAILNET_ORIGIN}).status_code == 403
    # and a forwarded host that is not allowed does not even matter from such a peer
    assert client.get("/api/health", headers={"X-Forwarded-Host": "attacker.example"}).status_code == 200


def test_forwarded_proto_from_the_local_proxy_sets_the_secure_cookie(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    allow(monkeypatch, f"127.0.0.1,localhost,{TAILNET_HOST}")
    do_setup(client)

    # the way `tailscale serve` is expected to arrive: Host = the public name, proto = https
    phone = proxied(client.app, **{"Host": TAILNET_HOST, "X-Forwarded-Proto": "https", "X-Forwarded-For": "100.101.102.103", "User-Agent": ANDROID_CHROME})
    logged_in = phone.post("/api/auth/login", json=LOGIN, headers={"Origin": TAILNET_ORIGIN})
    assert logged_in.status_code == 200
    assert {"secure", "httponly", "samesite=strict"} <= cookie_flags(logged_in)

    token = logged_in.cookies.get(SESSION_COOKIE)
    assert token
    auth = {"Cookie": f"{SESSION_COOKIE}={token}"}  # (httpx will not send a Secure cookie over http itself)
    assert phone.get("/api/auth/me", headers=auth).json()["username"] == "chairman"
    logout = phone.post("/api/auth/logout", headers={**auth, "Origin": TAILNET_ORIGIN})
    assert logout.status_code == 200 and "secure" in cookie_flags(logout)  # the cookie is cleared with the same flags

    # the same proxy peer over plain http (no forwarded proto): not Secure
    plain = proxied(client.app).post("/api/auth/login", json=LOGIN)
    assert plain.status_code == 200 and "secure" not in cookie_flags(plain)
    assert {"httponly", "samesite=strict"} <= cookie_flags(plain)
    odd = proxied(client.app, **{"X-Forwarded-Proto": "gopher"}).post("/api/auth/login", json=LOGIN)
    assert odd.status_code == 200 and "secure" not in cookie_flags(odd)


def test_forwarded_host_is_trusted_only_from_the_local_proxy_and_only_when_allowlisted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    allow(monkeypatch, f"127.0.0.1,localhost,{TAILNET_HOST}")
    do_setup(client)
    # a proxy that keeps Host = 127.0.0.1:8000 and reports the public name in X-Forwarded-Host
    proxy = proxied(client.app, **{"X-Forwarded-Host": TAILNET_HOST, "X-Forwarded-Proto": "https"})
    ok = proxy.post("/api/auth/login", json=LOGIN, headers={"Origin": TAILNET_ORIGIN})
    assert ok.status_code == 200 and "secure" in cookie_flags(ok)
    # another site cannot write, whatever it claims
    assert proxy.post("/api/auth/login", json=LOGIN, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert proxy.post("/api/auth/login", json=LOGIN, headers={"Origin": "http://127.0.0.1:9999"}).status_code == 403

    # a forwarded host that is not on the allowlist is refused outright, https claim or not
    foreign = proxied(client.app, **{"X-Forwarded-Host": "attacker.example", "X-Forwarded-Proto": "https"})
    assert foreign.get("/api/health").status_code == 400
    assert foreign.post("/api/auth/login", json=LOGIN).status_code == 400
    listed = proxied(client.app, **{"X-Forwarded-Host": f"{TAILNET_HOST}, attacker.example"})
    assert listed.get("/api/health").status_code == 200  # the first entry is the one the browser used


def test_tailscale_name_is_refused_until_it_is_added_to_the_allowlist(client: TestClient) -> None:
    do_setup(client)
    phone = proxied(client.app, **{"Host": TAILNET_HOST, "X-Forwarded-Proto": "https"})
    assert phone.get("/api/health").status_code == 400
    assert phone.post("/api/auth/login", json=LOGIN, headers={"Origin": TAILNET_ORIGIN}).status_code == 400


def test_server_never_lets_uvicorn_rewrite_the_client_address(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    from app import main

    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.update(kwargs))
    main.run()
    assert seen["host"] == "127.0.0.1" and seen["workers"] == 1
    assert seen["proxy_headers"] is False  # the middleware must see the real TCP peer
    assert seen["log_config"]["loggers"]["village"]["level"] == "INFO"  # revokes and lockouts reach the app log


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::", "my-pc.tail1234.ts.net"])
def test_server_still_refuses_to_bind_anything_but_loopback(env: Path, monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("VILLAGE_HOST", host)
    monkeypatch.setenv("VILLAGE_ALLOWED_HOSTS", f"127.0.0.1,{TAILNET_HOST}")  # allowing a name is not binding to it
    get_settings.cache_clear()
    with pytest.raises(ValidationError, match="loopback"):
        get_settings()


# ---------------------------------------------------------------- lockout in SQLite


def test_lockout_survives_a_restart_of_the_app(migrated: Path) -> None:
    from app.main import create_app

    with TestClient(create_app(), base_url=BASE_URL) as first:
        do_setup(first)
        first.cookies.clear()
        for _ in range(5):
            assert first.post("/api/auth/login", json=WRONG).status_code == 401
        assert first.post("/api/auth/login", json=LOGIN).status_code == 429
    assert rows("SELECT username, COUNT(*) FROM login_failure GROUP BY username") == [("chairman", 5)]

    reset_engine()  # a new process: nothing is left in memory
    with TestClient(create_app(), base_url=BASE_URL) as second:
        locked = second.post("/api/auth/login", json=LOGIN)
        assert locked.status_code == 429  # even with the right password
        assert 0 < int(locked.headers["retry-after"]) <= 301
        assert "Too many failed login attempts" in locked.json()["detail"]
        assert rows("SELECT COUNT(*) FROM login_failure") == [(5,)]  # a refused attempt is not counted

        # five minutes later the window is over
        with sqlite3.connect(get_settings().db_file) as connection:
            connection.execute("UPDATE login_failure SET failed_at = datetime(failed_at, '-301 seconds')")
        assert second.post("/api/auth/login", json=LOGIN).status_code == 200
        assert rows("SELECT COUNT(*) FROM login_failure") == [(0,)]  # success forgives, and old rows are pruned


def test_lockout_is_per_username_and_a_success_gives_the_attempts_back(client: TestClient) -> None:
    do_setup(client)
    client.cookies.clear()
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "nobody", "password": "wrong password!"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "Nobody ", "password": "x"}).status_code == 429  # same name
    assert client.post("/api/auth/login", json=WRONG).status_code == 401  # another name is not locked
    assert rows("SELECT username, COUNT(*) FROM login_failure GROUP BY username ORDER BY username") == [("chairman", 1), ("nobody", 5)]
    assert client.post("/api/auth/login", json=LOGIN).status_code == 200
    assert rows("SELECT username, COUNT(*) FROM login_failure GROUP BY username") == [("nobody", 5)]
    assert "password" not in {row[1] for row in rows("PRAGMA table_info(login_failure)")}  # only name and time


def test_parallel_guesses_cannot_pass_the_limit_together(client: TestClient) -> None:
    do_setup(client)
    client.cookies.clear()

    def guess(_index: int) -> int:
        return TestClient(client.app, base_url=BASE_URL).post("/api/auth/login", json=WRONG).status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = sorted(pool.map(guess, range(12)))
    assert codes == [401] * 5 + [429] * 7  # exactly five passwords were looked at
    assert rows("SELECT COUNT(*) FROM login_failure") == [(5,)]


# ---------------------------------------------------------------- migration 0006


def test_0006_adds_lockout_and_device_columns_and_keeps_existing_sessions(env: Path) -> None:
    config = alembic_config()
    command.upgrade(config, "0005")
    now = "2026-01-01 00:00:00"
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("INSERT INTO admin_user (username, password_hash, created_at) VALUES ('chairman', 'hash', ?)", (now,))
        connection.execute(
            "INSERT INTO session (token_hash, user_id, created_at, expires_at) VALUES ('abc', 1, ?, '2099-01-01 00:00:00')", (now,)
        )
    command.upgrade(config, "0006")  # (later revisions have their own tests)
    assert check()["current"] == "0006"
    assert rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("6",)]
    assert rows("SELECT token_hash, user_id, device_label, last_seen_at, revoked_at FROM session") == [("abc", 1, "", None, None)]
    assert rows("SELECT COUNT(*) FROM login_failure") == [(0,)]

    command.downgrade(config, "0005")
    columns = {row[1] for row in rows("PRAGMA table_info(session)")}
    assert columns == {"id", "token_hash", "user_id", "created_at", "expires_at", "revoked_at"}
    assert rows("SELECT token_hash, user_id, expires_at FROM session") == [("abc", 1, "2099-01-01 00:00:00")]  # kept
    assert not rows("SELECT name FROM sqlite_master WHERE name = 'login_failure'")
    assert rows("SELECT name FROM sqlite_master WHERE name = 'ix_session_user_id'") == [("ix_session_user_id",)]
    assert rows("SELECT value FROM app_meta WHERE key = 'schema_version'") == [("5",)]

    command.upgrade(config, "head")
    assert rows("SELECT token_hash, device_label FROM session") == [("abc", "")]


def test_models_match_the_migrations_at_0006(migrated: Path) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db import Base, get_engine

    with get_engine().connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


# ---------------------------------------------------------------- devices & sessions


@pytest.mark.parametrize(
    ("user_agent", "label"),
    [
        (ANDROID_CHROME, "Chrome on Android"),
        (LINUX_CHROME, "Chrome on Linux"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0", "Edge on Windows"),
        ("Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0", "Firefox on Linux"),
        ("Mozilla/5.0 (Android 14; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0", "Firefox on Android"),
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1", "Safari on iPhone"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15", "Safari on macOS"),
        ("Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36", "Samsung Internet on Android"),
        ("curl/8.5.0", "Unknown device"),
        ("", "Unknown device"),
        (None, "Unknown device"),
        ("x" * 5000, "Unknown device"),
    ],
)
def test_device_label_from_user_agent(user_agent: str | None, label: str) -> None:
    assert device_label(user_agent) == label
    assert len(device_label(user_agent)) <= 80


def test_sessions_are_listed_with_device_created_last_seen_and_this_device(client: TestClient) -> None:
    desktop = device(client.app, LINUX_CHROME)
    do_setup(desktop)
    phone = device(client.app, ANDROID_CHROME)
    assert phone.post("/api/auth/login", json=LOGIN).status_code == 200

    from_desktop = desktop.get("/api/auth/sessions").json()
    assert [(item["device"], item["current"]) for item in from_desktop] == [("Chrome on Linux", True), ("Chrome on Android", False)]
    for item in from_desktop:
        assert set(item) == {"id", "device", "created_at", "last_seen_at", "expires_at", "current"}  # no token, no hash
        assert item["created_at"].endswith("Z") and item["last_seen_at"] is not None
    from_phone = phone.get("/api/auth/sessions").json()
    assert [(item["device"], item["current"]) for item in from_phone] == [("Chrome on Android", True), ("Chrome on Linux", False)]

    # only the label is stored, never the User-Agent
    stored = " ".join(str(value) for row in rows("SELECT * FROM session") for value in row)
    assert "Mozilla" not in stored and "Pixel" not in stored and "AppleWebKit" not in stored


def test_last_seen_is_updated_at_most_once_a_minute(client: TestClient) -> None:
    do_setup(client)
    first = rows("SELECT last_seen_at FROM session")[0][0]
    assert first is not None
    for _ in range(3):
        assert client.get("/api/auth/me").status_code == 200
    assert rows("SELECT last_seen_at FROM session")[0][0] == first  # no write for a session seen seconds ago

    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("UPDATE session SET last_seen_at = '2026-01-01 00:00:00.000000'")
    assert client.get("/api/auth/me").status_code == 200
    updated = rows("SELECT last_seen_at FROM session")[0][0]
    assert updated > "2026-01-01 00:00:01"
    assert client.get("/api/auth/sessions").json()[0]["last_seen_at"].startswith(updated[:10])

    with sqlite3.connect(get_settings().db_file) as connection:  # a session from before this feature
        connection.execute("UPDATE session SET last_seen_at = NULL, device_label = ''")
    listed = client.get("/api/auth/sessions").json()
    assert listed[0]["device"] == "Unknown device" and listed[0]["last_seen_at"] is not None


def test_revoking_a_session_logs_that_device_out_at_once(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    desktop = device(client.app, LINUX_CHROME)
    do_setup(desktop)
    phone = device(client.app, ANDROID_CHROME)
    phone.post("/api/auth/login", json=LOGIN)
    phone_token = phone.cookies.get(SESSION_COOKIE)
    assert phone.get("/api/village").status_code == 200
    phone_id = next(item["id"] for item in desktop.get("/api/auth/sessions").json() if not item["current"])

    with caplog.at_level(logging.INFO, logger="village.security"):
        assert desktop.post(f"/api/auth/sessions/{phone_id}/revoke").json() == {"revoked": 1}

    # the very next request of the phone is refused — on every route
    assert phone.get("/api/village").status_code == 401
    assert phone.get("/api/auth/me").status_code == 401
    assert phone.get("/api/auth/sessions").status_code == 401
    assert phone.post("/api/tasks", json={"title": "from a revoked phone"}).status_code == 401
    assert desktop.get("/api/village").status_code == 200  # this device is untouched
    assert [item["device"] for item in desktop.get("/api/auth/sessions").json()] == ["Chrome on Linux"]

    # revoking again, or something that does not exist, is a 404
    assert desktop.post(f"/api/auth/sessions/{phone_id}/revoke").status_code == 404
    assert desktop.post("/api/auth/sessions/999/revoke").status_code == 404

    # written to the application log — without the token or its hash
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [f"session {phone_id} (Chrome on Android) revoked by chairman"]
    token_hash = rows("SELECT token_hash FROM session WHERE id = ?", phone_id)[0][0]
    assert phone_token not in caplog.text and token_hash not in caplog.text
    # the row is kept, marked revoked
    assert rows("SELECT revoked_at IS NOT NULL FROM session WHERE id = ?", phone_id) == [(1,)]


def test_log_out_all_other_devices(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    desktop = device(client.app, LINUX_CHROME)
    do_setup(desktop)
    others = [device(client.app, ANDROID_CHROME), device(client.app, ANDROID_CHROME), device(client.app, "curl/8.5.0")]
    for other in others:
        assert other.post("/api/auth/login", json=LOGIN).status_code == 200
    assert len(desktop.get("/api/auth/sessions").json()) == 4

    with caplog.at_level(logging.INFO, logger="village.security"):
        assert desktop.post("/api/auth/sessions/revoke-others").json() == {"revoked": 3}
    for other in others:
        assert other.get("/api/auth/me").status_code == 401
    remaining = desktop.get("/api/auth/sessions").json()
    assert [(item["device"], item["current"]) for item in remaining] == [("Chrome on Linux", True)]
    assert desktop.get("/api/auth/me").status_code == 200
    assert len(caplog.records) == 3 and all("log out all other devices" in record.getMessage() for record in caplog.records)
    assert desktop.post("/api/auth/sessions/revoke-others").json() == {"revoked": 0}  # nothing left to revoke


def test_revoking_this_device_logs_it_out_and_clears_the_cookie(client: TestClient) -> None:
    do_setup(client)
    own = client.get("/api/auth/sessions").json()[0]
    assert own["current"] is True
    response = client.post(f"/api/auth/sessions/{own['id']}/revoke")
    assert response.status_code == 200 and "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").status_code == 401


def test_expired_and_revoked_sessions_are_not_listed(client: TestClient) -> None:
    do_setup(client)
    other = device(client.app, ANDROID_CHROME)
    other.post("/api/auth/login", json=LOGIN)
    gone = device(client.app, ANDROID_CHROME)
    gone.post("/api/auth/login", json=LOGIN)
    gone.post("/api/auth/logout")
    other_id = next(item["id"] for item in client.get("/api/auth/sessions").json() if not item["current"])
    with sqlite3.connect(get_settings().db_file) as connection:
        connection.execute("UPDATE session SET expires_at = '2000-01-01 00:00:00.000000' WHERE id = ?", (other_id,))
    assert [item["current"] for item in client.get("/api/auth/sessions").json()] == [True]
    assert client.post(f"/api/auth/sessions/{other_id}/revoke").status_code == 404  # expired: nothing to revoke
    assert client.post("/api/auth/sessions/revoke-others").json() == {"revoked": 0}


SESSION_ROUTES = {
    ("GET", "/api/auth/sessions"),
    ("POST", "/api/auth/sessions/revoke-others"),
    ("POST", "/api/auth/sessions/{session_id}/revoke"),
}


def test_every_session_route_needs_a_session(client: TestClient) -> None:
    do_setup(client)
    other = device(client.app, ANDROID_CHROME)
    other.post("/api/auth/login", json=LOGIN)
    session_id = client.get("/api/auth/sessions").json()[1]["id"]
    client.cookies.clear()
    assert {route for route in api_routes(client.app) if route[1].startswith("/api/auth/sessions")} == SESSION_ROUTES
    for method, template in sorted(SESSION_ROUTES):
        response = client.request(method, template.replace("{session_id}", str(session_id)))
        assert response.status_code == 401, (method, template)
    assert other.get("/api/auth/me").status_code == 200  # nothing was revoked by the anonymous requests


# ---------------------------------------------------------------- doctor: bind check

PROC_TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F40 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 111 1 0000000000000000 100 0 0 10 0
   1: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 222 1 0000000000000000 100 0 0 10 0
   2: 0100007F:1F40 0100007F:D431 01 00000000:00000000 00:00000000 00000000  1000        0 333 1 0000000000000000 20 4 30 10 -1
   3: 00000000:2328 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 444 1 0000000000000000 100 0 0 10 0
"""
PROC_TCP6 = """  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000001000000:1F41 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 555 1 0000000000000000 100 0 0 10 0
   1: 00000000000000000000000000000000:2329 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 666 1 0000000000000000 100 0 0 10 0
"""


def test_bindcheck_reads_the_listening_addresses_of_a_port(tmp_path: Path) -> None:
    (tmp_path / "tcp").write_text(PROC_TCP)
    (tmp_path / "tcp6").write_text(PROC_TCP6)
    assert bindcheck.listening_addresses(8000, tmp_path) == ["127.0.0.1"]  # the established connection is not a listener
    assert bindcheck.listening_addresses(8001, tmp_path) == ["::1"]
    assert bindcheck.listening_addresses(9000, tmp_path) == ["0.0.0.0"]
    assert bindcheck.listening_addresses(9001, tmp_path) == ["::"]
    assert bindcheck.listening_addresses(22, tmp_path) == ["0.0.0.0"]
    assert bindcheck.listening_addresses(12345, tmp_path) == []
    assert bindcheck.listening_addresses(8000, tmp_path / "missing") is None


def test_bindcheck_verdicts() -> None:
    assert bindcheck.verdict(["127.0.0.1"], 8000, "127.0.0.1") == (
        "PASS",
        "bind: port 8000 is listening on 127.0.0.1 only (not reachable from the network)",
    )
    assert bindcheck.verdict(["::1"], 8000, "::1")[0] == "PASS"
    assert bindcheck.verdict([], 8000, "127.0.0.1")[0] == "PASS"
    assert "nothing is listening" in bindcheck.verdict([], 8000, "127.0.0.1")[1]
    assert bindcheck.verdict(None, 8000, "127.0.0.1")[0] == "WARN"
    for exposed in (["0.0.0.0"], ["::"], ["127.0.0.1", "192.168.1.20"], ["100.101.102.103"]):
        status, message = bindcheck.verdict(exposed, 8000, "127.0.0.1")
        assert status == "FAIL" and "reachable from the network" in message and "127.0.0.1 only" in message


def test_bindcheck_sees_a_real_loopback_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert bindcheck.listening_addresses(port) == ["127.0.0.1"]
        assert bindcheck.verdict(bindcheck.listening_addresses(port), port, "127.0.0.1")[0] == "PASS"
    assert bindcheck.listening_addresses(port) == []


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run_doctor(monkeypatch: pytest.MonkeyPatch, **extra: str) -> str:
    port = free_port()
    monkeypatch.setenv("VILLAGE_PORT", str(port))
    for name, value in extra.items():
        monkeypatch.setenv(name, value)
    result = subprocess.run([str(ROOT_DIR / "village"), "doctor"], capture_output=True, text=True, timeout=60)
    assert "Traceback" not in result.stdout + result.stderr
    return result.stdout.replace(str(port), "PORT")


def test_doctor_reports_bind_address_allowed_hosts_and_tailscale(migrated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = run_doctor(monkeypatch)
    lines = output.splitlines()
    assert "PASS  bind: nothing is listening on port PORT; configured host is 127.0.0.1 (loopback only)" in lines
    assert "PASS  hosts: VILLAGE_ALLOWED_HOSTS allows 127.0.0.1,[::1],localhost (this PC only)" in lines
    tailscale = [line for line in lines if line.startswith("INFO  tailscale:")]
    assert len(tailscale) == 1 and ("not installed" in tailscale[0] or "command found (not run" in tailscale[0])
    assert f"PASS  migration: at head ({check()['head']})" in lines

    remote = run_doctor(monkeypatch, VILLAGE_ALLOWED_HOSTS=f"https://{TAILNET_HOST}/")
    assert f"PASS  hosts: VILLAGE_ALLOWED_HOSTS allows 127.0.0.1,[::1],localhost,{TAILNET_HOST} (remote name: {TAILNET_HOST})" in remote.splitlines()


def test_doctor_fails_on_a_non_loopback_host_setting(migrated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = run_doctor(monkeypatch, VILLAGE_HOST="0.0.0.0")
    assert "FAIL  bind: cannot check the listening address (run ./village setup)" in output.splitlines()
    assert "FAIL  hosts: cannot read VILLAGE_ALLOWED_HOSTS — configuration missing or invalid" in output.splitlines()


def test_doctor_never_runs_tailscale() -> None:
    script = (ROOT_DIR / "village").read_text(encoding="utf-8")
    code = [line.split("#", 1)[0] for line in script.splitlines()]
    uses = [line.strip() for line in code if "tailscale" in line]
    assert uses and all(line.startswith(("report ", "if command -v tailscale")) for line in uses), uses


# ---------------------------------------------------------------- start refuses an old database


def test_start_refuses_to_run_new_code_on_an_unmigrated_database(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`./village restart` after an update, without `./village setup`, must not start the server."""
    command.upgrade(alembic_config(), "0005")  # the database of the previous version
    reset_engine()
    port = free_port()
    pid_file = env / "village.pid"
    monkeypatch.setenv("VILLAGE_PORT", str(port))
    monkeypatch.setenv("VILLAGE_PID_FILE", str(pid_file))  # never the live village's PID file
    monkeypatch.setenv("VILLAGE_LOG_DIR", str(env / "logs"))
    try:
        result = subprocess.run([str(ROOT_DIR / "village"), "start"], capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        assert result.returncode != 0
        head = check()["head"]
        assert f"The database is at revision 0005 but this version of the Village needs {head}. Run: ./village setup" in output
        assert not pid_file.exists()  # nothing was started
        assert bindcheck.listening_addresses(port) == []
    finally:
        if pid_file.exists():  # only if the guard failed: stop what was started
            subprocess.run(["kill", pid_file.read_text().strip()], check=False)

"""Part A: config, database pragmas, migration 0001, health endpoint."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.config import Settings, get_settings
from app.db import get_engine
from app.dbcheck import alembic_config, check
from tests.conftest import BASE_URL, TEST_SECRET_KEY


def test_health_ok_wal_and_demo_mode(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "version": body["version"],
        "db_ok": True,
        "journal_mode": "wal",
        "demo_mode": True,
        "setup_completed": False,
    }
    assert TEST_SECRET_KEY not in response.text


def test_health_reports_non_demo_without_leaking_key(
    migrated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VILLAGE_ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app(), base_url=BASE_URL) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["demo_mode"] is False
    assert "sk-ant-test" not in response.text


def test_health_degraded_when_database_not_migrated(env: Path) -> None:
    from app.main import create_app

    with TestClient(create_app(), base_url=BASE_URL) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["db_ok"] is False


def test_migration_on_temp_db_seeds_app_meta(migrated: Path) -> None:
    db_file = get_settings().db_file
    assert db_file.parent == migrated  # the temp dir, not data/
    with sqlite3.connect(db_file) as connection:
        rows = dict(connection.execute("SELECT key, value FROM app_meta").fetchall())
    assert rows["setup_completed"] == "false"
    assert rows["schema_version"].isdigit()
    state = check()
    assert state["current"] == state["head"] != "none"
    assert state["journal_mode"] == "wal"


def test_migration_downgrade_to_base_and_back(migrated: Path) -> None:
    command.downgrade(alembic_config(), "base")
    with sqlite3.connect(get_settings().db_file) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "app_meta" not in tables
    command.upgrade(alembic_config(), "head")
    assert check()["current"] == check()["head"]


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "::"])
def test_non_loopback_host_rejected(host: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key=TEST_SECRET_KEY, host=host)  # type: ignore[call-arg]


def test_non_loopback_host_rejected_from_environment(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VILLAGE_HOST", "0.0.0.0")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_hosts_accepted(host: str) -> None:
    settings = Settings(_env_file=None, secret_key=TEST_SECRET_KEY, host=host)  # type: ignore[call-arg]
    assert settings.host == host


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VILLAGE_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_defaults(env: Path) -> None:
    settings = get_settings()
    assert (settings.host, settings.port) == ("127.0.0.1", 8000)
    assert settings.demo_mode is True
    assert TEST_SECRET_KEY not in repr(settings)


def test_connection_pragmas(env: Path) -> None:
    with get_engine().connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000

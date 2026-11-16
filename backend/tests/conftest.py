"""Shared fixtures. Every test runs against a temp database and a temp secrets file —
never data/village.db or data/.env."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient

from app.config import ROOT_DIR, get_settings
from app.db import reset_engine
from app.dbcheck import alembic_config

TEST_SECRET_KEY = "test-secret-key-0123456789abcdef"
BASE_URL = "http://127.0.0.1:8000"
_ENV_VARS = (
    "VILLAGE_HOST",
    "VILLAGE_PORT",
    "VILLAGE_LOG_DIR",
    "VILLAGE_SECRET_KEY",
    "VILLAGE_ANTHROPIC_API_KEY",
)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolated settings: temp .env, temp DB, temp frontend dist."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"VILLAGE_SECRET_KEY={TEST_SECRET_KEY}\n", encoding="utf-8")
    env_file.chmod(0o600)
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VILLAGE_ENV_FILE", str(env_file))
    monkeypatch.setenv("VILLAGE_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("VILLAGE_FRONTEND_DIST", str(tmp_path / "dist"))
    # No background task worker: tests run the queue themselves (app.task_runner.run_once / drain),
    # so nothing depends on timing. test_m3_tasks.py switches it on for the tests that need it.
    monkeypatch.setenv("VILLAGE_TASK_WORKER", "0")
    # No scheduler thread either: tests fire schedules themselves (app.scheduler.run_schedule);
    # test_m4_memory_schedules.py switches it on where the real APScheduler is under test.
    monkeypatch.setenv("VILLAGE_SCHEDULER", "0")
    monkeypatch.delenv("VILLAGE_STUCK_TASK_MINUTES", raising=False)
    get_settings.cache_clear()
    reset_engine()
    assert get_settings().db_file != ROOT_DIR / "data" / "village.db"
    yield tmp_path
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def migrated(env: Path) -> Path:
    command.upgrade(alembic_config(), "head")
    return env


@pytest.fixture
def client(migrated: Path) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app(), base_url=BASE_URL) as test_client:
        yield test_client

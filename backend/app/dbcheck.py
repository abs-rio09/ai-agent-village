"""Database facts for `./village doctor`: migration revision vs head, and journal mode.

Usage: python -m app.dbcheck   (prints key=value lines; never creates the database)
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def check() -> dict[str, str]:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head() or "none"
    if not get_settings().db_file.exists():
        return {"db_exists": "no", "current": "none", "head": head, "journal_mode": "none"}
    with get_engine().connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision() or "none"
        journal_mode = str(connection.execute(text("PRAGMA journal_mode")).scalar_one())
    return {"db_exists": "yes", "current": current, "head": head, "journal_mode": journal_mode}


if __name__ == "__main__":
    for key, value in check().items():
        print(f"{key}={value}")

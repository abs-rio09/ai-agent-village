"""Alembic environment: uses the application's settings, engine and Base.metadata."""

from __future__ import annotations

from alembic import context

from app import models  # noqa: F401  (registers all tables on Base.metadata)
from app.config import get_settings
from app.db import Base, get_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=f"sqlite:///{get_settings().db_file}",
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

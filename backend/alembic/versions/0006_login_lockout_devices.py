"""login lockout in the database, device label and last-seen on sessions

Revision ID: 0006
Revises: 0005

- `login_failure`: the counted login attempts. The lockout (5 per 5 minutes per username) used
  to live in memory and was forgotten at every restart.
- `session.device_label` ("Chrome on Android", from the User-Agent at login — the User-Agent
  itself is not stored) and `session.last_seen_at`, for the "Devices & sessions" page.
  Sessions that exist already get an empty label (shown as "Unknown device") and no last-seen.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _set_schema_version(version: str) -> None:
    op.execute(
        sa.text("UPDATE app_meta SET value = :v, updated_at = CURRENT_TIMESTAMP WHERE key = 'schema_version'").bindparams(
            v=version
        )
    )


def upgrade() -> None:
    op.create_table(
        "login_failure",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("failed_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_login_failure_username", "login_failure", ["username"])
    op.add_column("session", sa.Column("device_label", sa.String(80), nullable=False, server_default=""))
    op.add_column("session", sa.Column("last_seen_at", sa.DateTime, nullable=True))
    _set_schema_version("6")


def downgrade() -> None:
    with op.batch_alter_table("session") as batch:  # SQLite: rebuilds the table without the columns
        batch.drop_column("last_seen_at")
        batch.drop_column("device_label")
    op.drop_index("ix_login_failure_username", table_name="login_failure")
    op.drop_table("login_failure")
    _set_schema_version("5")

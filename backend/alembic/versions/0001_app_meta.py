"""app_meta key/value table, seeded with schema_version and setup_completed

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    app_meta = op.create_table(
        "app_meta",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    op.bulk_insert(
        app_meta,
        [
            {"key": "schema_version", "value": "1", "updated_at": now},
            {"key": "setup_completed", "value": "false", "updated_at": now},
        ],
    )


def downgrade() -> None:
    op.drop_table("app_meta")

"""village, admin_user and session tables

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
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
        "village",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("chairman_name", sa.String(80), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("ai_mode", sa.String(16), nullable=False),
        sa.Column("ollama_url", sa.String(255), nullable=True),
        sa.Column("default_structure", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("ai_mode IN ('demo', 'ollama', 'anthropic')", name="ck_village_ai_mode"),
        sa.CheckConstraint("default_structure IN ('empty', 'standard')", name="ck_village_default_structure"),
    )
    op.create_table(
        "admin_user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("username", name="uq_admin_user_username"),
    )
    op.create_table(
        "session",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("admin_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_session_token_hash"),
    )
    op.create_index("ix_session_user_id", "session", ["user_id"])
    _set_schema_version("2")


def downgrade() -> None:
    op.drop_index("ix_session_user_id", table_name="session")
    op.drop_table("session")
    op.drop_table("admin_user")
    op.drop_table("village")
    _set_schema_version("1")

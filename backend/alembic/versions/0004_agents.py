"""agents: agent_template, agent (+ 15 seeded templates and the Central Manager)

Revision ID: 0004
Revises: 0003

An agent's Upazila, Union and Ward are not stored: they follow from its office. Tools and
permissions are stored only — nothing enforces them before M4.
The seed (docs/SPEC.md §6 templates, one Central Manager in the Central Administration office)
is `app.seed.seed_agents`: idempotent, and written against the columns created here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.seed import seed_agents

revision = "0004"
down_revision = "0003"
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
        "agent_template",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("avatar_key", sa.String(40), nullable=False),
        sa.Column("default_instructions", sa.Text, nullable=False),
        sa.Column("default_tools", sa.JSON, nullable=False),
        sa.Column("default_permissions", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("key", name="uq_agent_template_key"),
    )
    op.create_table(
        "agent",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("avatar_key", sa.String(40), nullable=False),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("agent_template.id", ondelete="SET NULL"), nullable=True),
        # NULL = the agent's office was deleted. The application also disables such an agent.
        sa.Column("office_id", sa.Integer, sa.ForeignKey("office.id", ondelete="SET NULL"), nullable=True),
        sa.Column("system_instructions", sa.Text, nullable=False),
        sa.Column("allowed_tools", sa.JSON, nullable=False),
        sa.Column("permissions", sa.JSON, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("memory_config", sa.JSON, nullable=False),
        sa.Column("working_schedule", sa.JSON, nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False),
        sa.Column("runtime_state", sa.String(16), nullable=False),
        sa.Column("is_central_manager", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("disabled_at", sa.DateTime, nullable=True),
        sa.CheckConstraint("lifecycle IN ('active', 'paused', 'disabled')", name="ck_agent_lifecycle"),
        sa.CheckConstraint("runtime_state IN ('idle', 'working', 'waiting', 'offline')", name="ck_agent_runtime_state"),
    )
    op.create_index("ix_agent_office_id", "agent", ["office_id"])
    # At most one Central Manager: a partial unique index over the rows that are one.
    op.create_index(
        "uq_agent_single_central_manager",
        "agent",
        ["is_central_manager"],
        unique=True,
        sqlite_where=sa.text("is_central_manager = 1"),
    )
    seed_agents(op.get_bind())
    _set_schema_version("4")


def downgrade() -> None:
    op.drop_index("uq_agent_single_central_manager", table_name="agent")
    op.drop_index("ix_agent_office_id", table_name="agent")
    op.drop_table("agent")
    op.drop_table("agent_template")
    _set_schema_version("3")

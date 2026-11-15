"""tasks: task, agent_message

Revision ID: 0005
Revises: 0004

`task` holds every field of docs/SPEC.md §8B plus `depth` (delegation depth, 0 = sent by the
Chairman) and `updated_at`. `agent_message` is the communication log of §8C. No rows are
seeded. An agent that has tasks or messages cannot be deleted by the application, so the
agent foreign keys have no ON DELETE action.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
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
        "task",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("assigned_agent_id", sa.Integer, sa.ForeignKey("agent.id"), nullable=True),
        sa.Column("parent_task_id", sa.Integer, sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=True),
        sa.Column("depth", sa.Integer, nullable=False),
        sa.Column("priority", sa.String(8), nullable=False),
        sa.Column("input", sa.JSON, nullable=False),
        sa.Column("output", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING_APPROVAL', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_task_status",
        ),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_task_priority"),
        sa.CheckConstraint("depth >= 0", name="ck_task_depth"),
    )
    op.create_index("ix_task_status", "task", ["status"])
    op.create_index("ix_task_parent_task_id", "task", ["parent_task_id"])
    op.create_index("ix_task_assigned_agent_id", "task", ["assigned_agent_id"])
    op.create_table(
        "agent_message",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sender_agent_id", sa.Integer, sa.ForeignKey("agent.id"), nullable=False),
        sa.Column("receiver_agent_id", sa.Integer, sa.ForeignKey("agent.id"), nullable=False),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("type IN ('delegation', 'result')", name="ck_agent_message_type"),
    )
    op.create_index("ix_agent_message_task_id", "agent_message", ["task_id"])
    _set_schema_version("5")


def downgrade() -> None:
    op.drop_index("ix_agent_message_task_id", table_name="agent_message")
    op.drop_table("agent_message")
    op.drop_index("ix_task_assigned_agent_id", table_name="task")
    op.drop_index("ix_task_parent_task_id", table_name="task")
    op.drop_index("ix_task_status", table_name="task")
    op.drop_table("task")
    _set_schema_version("4")

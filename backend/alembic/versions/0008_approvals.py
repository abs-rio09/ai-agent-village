"""approvals (human in the loop)

Revision ID: 0008
Revises: 0007

One row per request of an agent to use a SENSITIVE tool. It holds everything the Chairman is
shown before deciding (docs/SPEC.md §8F: requesting agent, requested action, reason, tool,
expected changes, risk information), the decision, and what the task still has to do after an
approval (`continuation`). `executed_at` is set when the approved call has been carried out, so
an approval can never be used twice.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
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
        "approval",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agent.id"), nullable=False),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_key", sa.String(64), nullable=False),
        sa.Column("args", sa.JSON, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("expected_changes", sa.Text, nullable=False),
        sa.Column("risk_info", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.Column("decided_by", sa.String(80), nullable=True),
        sa.Column("decision_note", sa.Text, nullable=False, server_default=""),
        sa.Column("continuation", sa.JSON, nullable=False),
        sa.Column("executed_at", sa.DateTime, nullable=True),
        sa.Column("result", sa.Text, nullable=True),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')", name="ck_approval_status"),
    )
    op.create_index("ix_approval_status", "approval", ["status"])
    op.create_index("ix_approval_task_id", "approval", ["task_id"])
    _set_schema_version("8")


def downgrade() -> None:
    # A task cannot wait for an approval that no longer exists.
    op.execute(
        "UPDATE task SET status = 'FAILED', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, "
        "error = 'The approval system was removed (database downgrade) while this task was waiting for approval.' "
        "WHERE status = 'WAITING_APPROVAL'"
    )
    op.drop_index("ix_approval_task_id", table_name="approval")
    op.drop_index("ix_approval_status", table_name="approval")
    op.drop_table("approval")
    _set_schema_version("7")

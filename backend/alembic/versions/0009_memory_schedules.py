"""memory scopes, task context, schedules

Revision ID: 0009
Revises: 0008

- `memory`: VILLAGE / UPAZILA / AGENT notes (docs/SPEC.md §8D). A CHECK makes sure a row belongs
  to exactly the owner its scope names, and another one that VILLAGE memory can never carry the
  customer-data flag: private customer information does not go into shared memory.
- `task_context`: short-lived working notes of ONE task. The application deletes them when the
  task finishes.
- `task.kind`: 'request' (sent by the Chairman), 'delegated' (child task), 'scheduled' (created
  by a schedule for one agent), 'daily_report', 'health_check'. Added with ALTER TABLE ADD COLUMN
  and removed with ALTER TABLE DROP COLUMN — never with a batch rebuild: rebuilding `task` would
  drop the old table, and that cascades to its messages and approvals.
- `schedule` + `schedule_run`: the owner's and the built-in schedules, and one row per run. The
  UNIQUE run key is what guarantees "one run, at most one task".
- `apscheduler_jobs`: APScheduler's own job store table, created here (same columns as
  APScheduler 3.x creates) so that the schema only ever changes through Alembic.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
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
        "memory",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("upazila_id", sa.Integer, sa.ForeignKey("upazila.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("contains_customer_data", sa.Boolean, nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.CheckConstraint(
            "(scope = 'VILLAGE' AND upazila_id IS NULL AND agent_id IS NULL) OR "
            "(scope = 'UPAZILA' AND upazila_id IS NOT NULL AND agent_id IS NULL) OR "
            "(scope = 'AGENT' AND agent_id IS NOT NULL AND upazila_id IS NULL)",
            name="ck_memory_scope_owner",
        ),
        sa.CheckConstraint("NOT (scope = 'VILLAGE' AND contains_customer_data)", name="ck_memory_no_customer_data_in_village"),
    )
    op.create_index("ix_memory_scope", "memory", ["scope"])
    op.create_index("ix_memory_upazila_id", "memory", ["upazila_id"])
    op.create_index("ix_memory_agent_id", "memory", ["agent_id"])

    op.create_table(
        "task_context",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("task_id", "key", name="uq_task_context_task_key"),
    )

    op.add_column("task", sa.Column("kind", sa.String(16), nullable=False, server_default="request"))
    op.execute("UPDATE task SET kind = 'delegated' WHERE parent_task_id IS NOT NULL")

    op.create_table(
        "schedule",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("builtin_key", sa.String(32), nullable=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=True),
        sa.Column("request_text", sa.Text, nullable=False),
        sa.Column("trigger_type", sa.String(16), nullable=False),
        sa.Column("interval_minutes", sa.Integer, nullable=True),
        sa.Column("daily_time", sa.String(5), nullable=True),
        sa.Column("paused", sa.Boolean, nullable=False),
        sa.Column("anchor_at", sa.DateTime, nullable=False),
        sa.Column("last_run_at", sa.DateTime, nullable=True),
        sa.Column("last_task_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("kind IN ('builtin', 'custom')", name="ck_schedule_kind"),
        sa.CheckConstraint(
            "(trigger_type = 'interval' AND interval_minutes >= 1) OR (trigger_type = 'daily' AND daily_time IS NOT NULL)",
            name="ck_schedule_trigger",
        ),
        sa.CheckConstraint(
            "(kind = 'builtin' AND builtin_key IS NOT NULL) OR (kind = 'custom' AND builtin_key IS NULL AND agent_id IS NOT NULL)",
            name="ck_schedule_owner",
        ),
        sa.UniqueConstraint("builtin_key", name="uq_schedule_builtin_key"),
    )
    op.create_table(
        "schedule_run",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("schedule_id", sa.Integer, sa.ForeignKey("schedule.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_key", sa.String(80), nullable=False),
        sa.Column("fired_at", sa.DateTime, nullable=False),
        sa.Column("task_id", sa.Integer, nullable=True),
        sa.UniqueConstraint("run_key", name="uq_schedule_run_key"),
    )
    op.create_index("ix_schedule_run_schedule_id", "schedule_run", ["schedule_id"])

    # APScheduler 3.x SQLAlchemyJobStore (apscheduler/jobstores/sqlalchemy.py)
    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.Unicode(191), primary_key=True),
        sa.Column("next_run_time", sa.Float(25), nullable=True),
        sa.Column("job_state", sa.LargeBinary, nullable=False),
    )
    op.create_index("ix_apscheduler_jobs_next_run_time", "apscheduler_jobs", ["next_run_time"])
    _set_schema_version("9")


def downgrade() -> None:
    op.drop_index("ix_apscheduler_jobs_next_run_time", table_name="apscheduler_jobs")
    op.drop_table("apscheduler_jobs")
    op.drop_index("ix_schedule_run_schedule_id", table_name="schedule_run")
    op.drop_table("schedule_run")
    op.drop_table("schedule")
    # Tasks only this revision knows how to run would be routed like ordinary requests afterwards.
    op.execute(
        "UPDATE task SET status = 'CANCELLED', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, "
        "error = 'Cancelled by a database downgrade: schedules were removed.' "
        "WHERE kind IN ('scheduled', 'daily_report', 'health_check') AND status IN ('QUEUED', 'ASSIGNED', 'RUNNING')"
    )
    op.execute("ALTER TABLE task DROP COLUMN kind")  # native; see the note at the top
    op.drop_table("task_context")
    op.drop_index("ix_memory_agent_id", table_name="memory")
    op.drop_index("ix_memory_upazila_id", table_name="memory")
    op.drop_index("ix_memory_scope", table_name="memory")
    op.drop_table("memory")
    _set_schema_version("8")

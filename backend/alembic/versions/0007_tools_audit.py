"""tool registry keys, audit log, information-request messages

Revision ID: 0007
Revises: 0006

- `audit_log`: append-only. Two triggers refuse UPDATE and DELETE, so not even a bug in the
  application can rewrite history. (A later migration that rebuilds this table with
  batch_alter_table must create the triggers again.) agent_id / task_id are plain numbers on
  purpose: an entry outlives the agent or task it is about.
- `agent_message.type` may now also be 'info_request' (the agent.request_info tool).
- Tool keys: M3 stored free-form keys ("create_task"); the M4 registry uses "area.verb" keys
  ("task.create_child"). The keys stored on agents and agent templates are renamed. Templates
  also get the new non-sensitive default tools (memory.read / memory.write, org.read for the
  two manager templates). EXISTING AGENTS ONLY GET THE RENAME — no agent is given a tool it
  did not have. Nothing sensitive is assigned to anyone by this migration.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# Frozen on purpose: a migration must not change when the application's catalogue changes.
RENAMED_TOOLS = {
    "read_documents": "document.read",
    "search_knowledge": "knowledge.search",
    "create_document": "document.create",
    "generate_pdf": "pdf.generate",
    "create_task": "task.create_child",
    "ask_agent": "agent.request_info",
    "read_calendar": "calendar.read",
    "get_product_info": "product.read",
    "check_inventory": "inventory.check",
    "system_health_check": "system.health_check",
}
_OLD_NAMES = {new: old for old, new in RENAMED_TOOLS.items()}
NEW_TEMPLATE_TOOLS = ("memory.read", "memory.write")
NEW_MANAGER_TOOLS = ("org.read",)
MANAGER_TEMPLATES = ("village_manager", "office_manager")


def _set_schema_version(version: str) -> None:
    op.execute(
        sa.text("UPDATE app_meta SET value = :v, updated_at = CURRENT_TIMESTAMP WHERE key = 'schema_version'").bindparams(
            v=version
        )
    )


def _load(value: object) -> list[str]:
    items = json.loads(value) if isinstance(value, str) else value
    return [item for item in (items or []) if isinstance(item, str)]


def _rewrite(table: str, column: str, change) -> None:  # noqa: ANN001
    """Apply `change(row_key, tools) -> tools` to a JSON list column of every row."""
    connection = op.get_bind()
    key_column = "key" if table == "agent_template" else "id"
    rows = connection.execute(sa.text(f"SELECT id, {key_column}, {column} FROM {table}")).all()  # noqa: S608
    for row_id, row_key, value in rows:
        before = _load(value)
        after = list(dict.fromkeys(change(row_key, before)))
        if after != before:
            connection.execute(
                sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),  # noqa: S608
                {"value": json.dumps(after), "id": row_id},
            )


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("agent_id", sa.Integer, nullable=True),
        sa.Column("agent_name", sa.String(80), nullable=True),
        sa.Column("task_id", sa.Integer, nullable=True),
        sa.Column("tool_key", sa.String(64), nullable=True),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_agent_id", "audit_log", ["agent_id"])
    op.create_index("ix_audit_log_task_id", "audit_log", ["task_id"])
    for event in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER audit_log_no_{event.lower()} BEFORE {event} ON audit_log "
            "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
        )

    with op.batch_alter_table("agent_message") as batch:
        batch.drop_constraint("ck_agent_message_type", type_="check")
        batch.create_check_constraint("ck_agent_message_type", "type IN ('delegation', 'result', 'info_request')")

    _rewrite("agent", "allowed_tools", lambda _id, tools: [RENAMED_TOOLS.get(tool, tool) for tool in tools])

    def template_tools(key: str, tools: list[str]) -> list[str]:
        renamed = [RENAMED_TOOLS.get(tool, tool) for tool in tools]
        return [*renamed, *(NEW_MANAGER_TOOLS if key in MANAGER_TEMPLATES else ()), *NEW_TEMPLATE_TOOLS]

    _rewrite("agent_template", "default_tools", template_tools)
    _set_schema_version("7")


def downgrade() -> None:
    def old_tools(_key: object, tools: list[str]) -> list[str]:
        # tools that did not exist before this revision are dropped
        return [_OLD_NAMES[tool] for tool in tools if tool in _OLD_NAMES]

    _rewrite("agent_template", "default_tools", old_tools)
    _rewrite("agent", "allowed_tools", old_tools)

    op.execute("DELETE FROM agent_message WHERE type = 'info_request'")  # the old CHECK would refuse them
    with op.batch_alter_table("agent_message") as batch:
        batch.drop_constraint("ck_agent_message_type", type_="check")
        batch.create_check_constraint("ck_agent_message_type", "type IN ('delegation', 'result')")

    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
    op.drop_index("ix_audit_log_task_id", table_name="audit_log")
    op.drop_index("ix_audit_log_agent_id", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_table("audit_log")
    _set_schema_version("6")

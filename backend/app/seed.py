"""Idempotent seed data for M3: the agent templates and the one Central Manager.

`seed_agents` is called by migration 0004 and again at every application start, so a missing
template or a missing Central Manager is put back. Rows that exist are never changed, which
keeps the owner's edits. It uses plain table constructs with the columns of revision 0004
only, so it keeps working inside that migration whatever later revisions add.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from app.agent_catalog import AGENT_TEMPLATES, CENTRAL_MANAGER_NAME, CENTRAL_MANAGER_TEMPLATE_KEY, DEFAULT_PROVIDER
from app.db import utcnow

_agent_template = sa.table(
    "agent_template",
    sa.column("id", sa.Integer),
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("role", sa.String),
    sa.column("description", sa.Text),
    sa.column("avatar_key", sa.String),
    sa.column("default_instructions", sa.Text),
    sa.column("default_tools", sa.JSON),
    sa.column("default_permissions", sa.JSON),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)
_agent = sa.table(
    "agent",
    sa.column("id", sa.Integer),
    sa.column("display_name", sa.String),
    sa.column("avatar_key", sa.String),
    sa.column("role", sa.String),
    sa.column("description", sa.Text),
    sa.column("template_id", sa.Integer),
    sa.column("office_id", sa.Integer),
    sa.column("system_instructions", sa.Text),
    sa.column("allowed_tools", sa.JSON),
    sa.column("permissions", sa.JSON),
    sa.column("provider", sa.String),
    sa.column("memory_config", sa.JSON),
    sa.column("working_schedule", sa.JSON),
    sa.column("lifecycle", sa.String),
    sa.column("runtime_state", sa.String),
    sa.column("is_central_manager", sa.Boolean),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
    sa.column("disabled_at", sa.DateTime),
)
_office = sa.table("office", sa.column("id", sa.Integer), sa.column("kind", sa.String))


def seed_agent_templates(connection: Connection) -> int:
    """Insert the templates that are missing (matched by key). Returns how many were added."""
    existing = set(connection.execute(sa.select(_agent_template.c.key)).scalars())
    now = utcnow()
    rows = [
        {
            "key": template.key,
            "name": template.name,
            "role": template.role,
            "description": template.description,
            "avatar_key": template.avatar_key,
            "default_instructions": template.default_instructions,
            "default_tools": list(template.default_tools),
            "default_permissions": list(template.default_permissions),
            "created_at": now,
            "updated_at": now,
        }
        for template in AGENT_TEMPLATES
        if template.key not in existing
    ]
    if rows:
        connection.execute(sa.insert(_agent_template), rows)
    return len(rows)


def ensure_central_manager(connection: Connection) -> bool:
    """Create the Central Manager in the Central Administration office unless one exists.

    Returns True when it was created. Without a central office or the Village Manager template
    (neither can be deleted through the application) nothing is created.
    """
    if connection.execute(sa.select(_agent.c.id).where(_agent.c.is_central_manager.is_(True))).first():
        return False
    office_id = connection.execute(sa.select(_office.c.id).where(_office.c.kind == "central")).scalar()
    template = connection.execute(
        sa.select(_agent_template).where(_agent_template.c.key == CENTRAL_MANAGER_TEMPLATE_KEY)
    ).first()
    if office_id is None or template is None:
        return False
    now = utcnow()
    connection.execute(
        sa.insert(_agent),
        [
            {
                "display_name": CENTRAL_MANAGER_NAME,
                "avatar_key": template.avatar_key,
                "role": template.role,
                "description": template.description,
                "template_id": template.id,
                "office_id": office_id,
                "system_instructions": template.default_instructions,
                "allowed_tools": list(template.default_tools),
                "permissions": list(template.default_permissions),
                "provider": DEFAULT_PROVIDER,
                "memory_config": {},
                "working_schedule": {},
                "lifecycle": "active",
                "runtime_state": "idle",
                "is_central_manager": True,
                "created_at": now,
                "updated_at": now,
                "disabled_at": None,
            }
        ],
    )
    return True


def seed_agents(connection: Connection) -> tuple[int, bool]:
    """(templates added, Central Manager created). Safe to call any number of times."""
    return seed_agent_templates(connection), ensure_central_manager(connection)


def seed_if_migrated(engine: Engine) -> bool:
    """Run the seed at application start, but only on a database that already has the M3 tables."""
    if not sa.inspect(engine).has_table("agent"):
        return False
    with engine.begin() as connection:
        seed_agents(connection)
    return True

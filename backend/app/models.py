"""SQLAlchemy 2 typed models. Schema changes go through Alembic migrations only."""

from __future__ import annotations

from datetime import datetime

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, utcnow


class AppMeta(Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)



class Village(Base):
    __tablename__ = "village"
    __table_args__ = (
        CheckConstraint("ai_mode IN ('demo', 'ollama', 'anthropic')", name="ck_village_ai_mode"),
        CheckConstraint("default_structure IN ('empty', 'standard')", name="ck_village_default_structure"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    chairman_name: Mapped[str] = mapped_column(String(80), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    ollama_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_structure: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class AdminUser(Base):
    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserSession(Base):
    """Login session. Only the sha256 of the cookie token is stored."""

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_user.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # "Chrome on Android" — derived from the User-Agent at login; the User-Agent itself is not kept.
    device_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoginFailure(Base):
    """One counted login attempt. The lockout (5 per 5 minutes per username) is computed from
    these rows, so it survives a restart. A successful login deletes the username's rows."""

    __tablename__ = "login_failure"
    __table_args__ = (Index("ix_login_failure_username", "username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    failed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

# ---------------------------------------------------------------- organization (M2)
#
# Hierarchy: village -> upazila -> union_unit -> ward -> office. Every foreign key down the
# hierarchy is ON DELETE CASCADE, so deleting a unit removes everything below it.
# Templates are plain rows: editing them changes FUTURE generation only.


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class UpazilaTemplate(Timestamps, Base):
    __tablename__ = "upazila_template"
    __table_args__ = (UniqueConstraint("name", name="uq_upazila_template_name"),)

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UnionTemplate(Timestamps, Base):
    __tablename__ = "union_template"
    __table_args__ = (UniqueConstraint("upazila_template_key", "name", name="uq_union_template_key_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upazila_template_key: Mapped[str] = mapped_column(
        ForeignKey("upazila_template.key", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WardTemplate(Timestamps, Base):
    """The default ward set of an Upazila template: every generated Union gets these wards."""

    __tablename__ = "ward_template"
    __table_args__ = (
        UniqueConstraint("upazila_template_key", "number", name="uq_ward_template_key_number"),
        CheckConstraint("number >= 1", name="ck_ward_template_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upazila_template_key: Mapped[str] = mapped_column(
        ForeignKey("upazila_template.key", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    responsibility: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class Upazila(Timestamps, Base):
    __tablename__ = "upazila"
    __table_args__ = (UniqueConstraint("village_id", "name", name="uq_upazila_village_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    village_id: Mapped[int] = mapped_column(ForeignKey("village.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    template_key: Mapped[str | None] = mapped_column(
        ForeignKey("upazila_template.key", ondelete="SET NULL"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UnionUnit(Timestamps, Base):
    """A Union. The table is called union_unit because UNION is an SQL keyword."""

    __tablename__ = "union_unit"
    __table_args__ = (UniqueConstraint("upazila_id", "name", name="uq_union_unit_upazila_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upazila_id: Mapped[int] = mapped_column(ForeignKey("upazila.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Ward(Timestamps, Base):
    __tablename__ = "ward"
    __table_args__ = (
        UniqueConstraint("union_id", "number", name="uq_ward_union_number"),
        CheckConstraint("number >= 1", name="ck_ward_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    union_id: Mapped[int] = mapped_column(ForeignKey("union_unit.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    responsibility: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class Office(Timestamps, Base):
    """One office per ward (kind='ward') plus the single Central Administration (kind='central')."""

    __tablename__ = "office"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'ward' AND ward_id IS NOT NULL) OR (kind = 'central' AND ward_id IS NULL)",
            name="ck_office_kind_ward",
        ),
        UniqueConstraint("ward_id", name="uq_office_ward_id"),
        Index("uq_office_single_central", "kind", unique=True, sqlite_where=text("kind = 'central'")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("ward.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


# ---------------------------------------------------------------- agents (M3)
#
# An agent belongs to an office; its Upazila, Union and Ward follow from that office and are
# not stored again. Tools and permissions are enforced by app/tools (check_tool_use) since M4.


class AgentTemplate(Timestamps, Base):
    __tablename__ = "agent_template"
    __table_args__ = (UniqueConstraint("key", name="uq_agent_template_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar_key: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    default_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    default_permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class Agent(Timestamps, Base):
    __tablename__ = "agent"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('active', 'paused', 'disabled')", name="ck_agent_lifecycle"),
        CheckConstraint("runtime_state IN ('idle', 'working', 'waiting', 'offline')", name="ck_agent_runtime_state"),
        Index("ix_agent_office_id", "office_id"),
        Index(
            "uq_agent_single_central_manager",
            "is_central_manager",
            unique=True,
            sqlite_where=text("is_central_manager = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    avatar_key: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    template_id: Mapped[int | None] = mapped_column(ForeignKey("agent_template.id", ondelete="SET NULL"), nullable=True)
    # NULL = the agent's office was deleted (the agent is then disabled, its history kept).
    office_id: Mapped[int | None] = mapped_column(ForeignKey("office.id", ondelete="SET NULL"), nullable=True)
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="demo")
    memory_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    working_schedule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    runtime_state: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    is_central_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- tasks + messages (M3)
#
# A task is one row; delegation creates child rows (parent_task_id, depth). Every delegation
# and every result is also written as an agent_message. Statuses and their valid changes live
# in app/task_status.py.


class Task(Timestamps, Base):
    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING_APPROVAL', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_task_status",
        ),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_task_priority"),
        CheckConstraint("depth >= 0", name="ck_task_depth"),
        Index("ix_task_status", "status"),
        Index("ix_task_parent_task_id", "parent_task_id"),
        Index("ix_task_assigned_agent_id", "assigned_agent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # A username for the Chairman's tasks, "agent:<id>" for tasks an agent delegated.
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agent.id"), nullable=True)
    parent_task_id: Mapped[int | None] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = sent by the Chairman
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="normal")
    input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentMessage(Base):
    """Structured agent-to-agent communication (docs/SPEC.md §8C)."""

    __tablename__ = "agent_message"
    __table_args__ = (
        CheckConstraint("type IN ('delegation', 'result', 'info_request')", name="ck_agent_message_type"),
        Index("ix_agent_message_task_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_agent_id: Mapped[int] = mapped_column(ForeignKey("agent.id"), nullable=False)
    receiver_agent_id: Mapped[int] = mapped_column(ForeignKey("agent.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------- approvals (M4)
#
# One row per request of an agent to use a SENSITIVE tool. The task waits (WAITING_APPROVAL)
# until the Chairman approves or rejects. CANCELLED = the task ended before a decision.


class Approval(Base):
    __tablename__ = "approval"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')", name="ck_approval_status"),
        Index("ix_approval_status", "status"),
        Index("ix_approval_task_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agent.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"), nullable=False)
    tool_key: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # What the Chairman is shown (docs/SPEC.md §8F), written when the request is made.
    action: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_changes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_info: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # The tool requests of the same reply that come after this one; they run after an approval.
    continuation: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # set once the approved call ran
    result: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------- audit log (M4)
#
# Append-only: the application only inserts (app/audit.py) and the database refuses UPDATE and
# DELETE with triggers. agent_id and task_id are plain numbers, not foreign keys — an audit
# entry must outlive the thing it describes (agent_name keeps the name as it was).


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_agent_id", "agent_id"),
        Index("ix_audit_log_task_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    # "chairman:<username>", "agent:<id>" or "system"
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)  # "tool.denied", "agent.paused", …
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)  # allowed / denied / approved / …
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


def get_meta(session: Session, key: str) -> str | None:
    return session.execute(select(AppMeta.value).where(AppMeta.key == key)).scalar_one_or_none()

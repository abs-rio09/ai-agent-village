"""SQLAlchemy 2 typed models. Schema changes go through Alembic migrations only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select, text
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


def get_meta(session: Session, key: str) -> str | None:
    return session.execute(select(AppMeta.value).where(AppMeta.key == key)).scalar_one_or_none()

"""SQLAlchemy 2 typed models. Schema changes go through Alembic migrations only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, utcnow

class AppMeta(Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


def get_meta(session: Session, key: str) -> str | None:
    return session.execute(select(AppMeta.value).where(AppMeta.key == key)).scalar_one_or_none()

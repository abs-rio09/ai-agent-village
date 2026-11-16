"""Audit log: who did what, when, to which agent / task / tool, and how it was decided.

The log is append-only. This module only ever INSERTs; there is no update or delete function,
no update or delete API, and the database refuses both with triggers (migration 0007).

Nothing secret may reach the log. `record` drops every detail whose name looks like a
credential, masks strings that look like an API key and cuts long texts short. Callers must
still never pass a password, a session token or an API key in the first place.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, AuditLog

SYSTEM = "system"
SUMMARY_MAX = 500
_DETAIL_TEXT_MAX = 300
_DETAIL_ITEMS_MAX = 20
_SECRET_NAME = re.compile(r"pass(word|wd)?|token|secret|api[_-]?key|cookie|authori[sz]ation|credential|session_id", re.I)
# Anything shaped like a provider key or a long random token is masked wherever it appears.
_SECRET_VALUE = re.compile(r"\b(?:sk|pk|rk|xox[a-z])-[A-Za-z0-9_-]{12,}|\b[A-Za-z0-9_-]{40,}\b")
REDACTED = "[redacted]"


def chairman(username: str) -> str:
    return f"chairman:{username}"


def agent_actor(agent: Agent) -> str:
    return f"agent:{agent.id}"


def clean_text(value: str, limit: int = SUMMARY_MAX) -> str:
    text = _SECRET_VALUE.sub(REDACTED, re.sub(r"\s+", " ", value).strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _clean(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return clean_text(value, _DETAIL_TEXT_MAX)
    if isinstance(value, bool | int | float) or value is None:
        return value
    if depth >= 3:
        return "…"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in list(value.items())[:_DETAIL_ITEMS_MAX]:
            name = str(key)
            cleaned[name] = REDACTED if _SECRET_NAME.search(name) else _clean(item, depth + 1)
        return cleaned
    if isinstance(value, list | tuple | set | frozenset):
        return [_clean(item, depth + 1) for item in list(value)[:_DETAIL_ITEMS_MAX]]
    return clean_text(str(value), _DETAIL_TEXT_MAX)


def record(
    db: Session,
    action: str,
    *,
    actor: str = SYSTEM,
    agent: Agent | None = None,
    task_id: int | None = None,
    tool_key: str | None = None,
    decision: str | None = None,
    summary: str = "",
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add one audit entry to the session. The caller commits (so the entry is written together
    with the change it describes, or not at all)."""
    entry = AuditLog(
        actor=actor[:80],
        action=action,
        agent_id=agent.id if agent is not None else None,
        agent_name=agent.display_name if agent is not None else None,
        task_id=task_id,
        tool_key=tool_key,
        decision=decision,
        summary=clean_text(summary),
        details=_clean(details or {}),
    )
    db.add(entry)
    return entry

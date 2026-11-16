"""Memory & Knowledge API for the Chairman: list by scope, view, add, edit, delete.

The Chairman may see and change every memory. Two rules bind the Chairman too: a memory
belongs to exactly the owner its scope names, and customer data never goes into VILLAGE memory.
Edits and deletes are written to the audit log (without the content).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import audit
from app import memory as rules
from app.db import as_utc, get_session
from app.models import Agent, Memory, Upazila
from app.security import AuthContext, current_auth

router = APIRouter(prefix="/memory", tags=["memory"])

Scope = Literal["VILLAGE", "UPAZILA", "AGENT"]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=rules.TITLE_MAX)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=rules.CONTENT_MAX)]


class MemoryOut(BaseModel):
    id: int
    scope: Scope
    upazila_id: int | None
    upazila_name: str | None
    agent_id: int | None
    agent_name: str | None
    title: str
    content: str
    contains_customer_data: bool
    created_by: str  # "chairman:<username>" or "agent:<id>"
    updated_by: str
    created_at: datetime
    updated_at: datetime


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Scope
    upazila_id: int | None = None
    agent_id: int | None = None
    title: Title
    content: Content
    contains_customer_data: bool = False


class MemoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    content: Content | None = None
    contains_customer_data: bool | None = None


class MemoryDeleted(BaseModel):
    deleted: bool


def _out(db: Session, rows: list[Memory]) -> list[MemoryOut]:
    upazila_ids = {row.upazila_id for row in rows if row.upazila_id is not None}
    agent_ids = {row.agent_id for row in rows if row.agent_id is not None}
    upazilas = dict(db.execute(select(Upazila.id, Upazila.name).where(Upazila.id.in_(upazila_ids))).all()) if upazila_ids else {}
    agents = dict(db.execute(select(Agent.id, Agent.display_name).where(Agent.id.in_(agent_ids))).all()) if agent_ids else {}
    return [
        MemoryOut(
            id=row.id,
            scope=row.scope,  # type: ignore[arg-type]
            upazila_id=row.upazila_id,
            upazila_name=upazilas.get(row.upazila_id),
            agent_id=row.agent_id,
            agent_name=agents.get(row.agent_id),
            title=row.title,
            content=row.content,
            contains_customer_data=row.contains_customer_data,
            created_by=row.created_by,
            updated_by=row.updated_by,
            created_at=as_utc(row.created_at),  # type: ignore[arg-type]
            updated_at=as_utc(row.updated_at),  # type: ignore[arg-type]
        )
        for row in rows
    ]


def _get(db: Session, memory_id: int) -> Memory:
    row = db.get(Memory, memory_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return row


def _unprocessable(field: str, message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=[{"loc": ["body", field], "msg": message, "type": "value_error"}])


def _where(row: Memory) -> str:
    return {"VILLAGE": "village memory", "UPAZILA": f"the memory of Upazila #{row.upazila_id}", "AGENT": f"the notes of agent #{row.agent_id}"}[row.scope]


@router.get("", response_model=list[MemoryOut])
def list_memory(
    scope: Scope | None = Query(default=None),
    upazila_id: int | None = Query(default=None),
    agent_id: int | None = Query(default=None),
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_session),
) -> list[MemoryOut]:
    """Newest first."""
    query = select(Memory).order_by(Memory.id.desc()).limit(limit)
    if scope is not None:
        query = query.where(Memory.scope == scope)
    if upazila_id is not None:
        query = query.where(Memory.upazila_id == upazila_id)
    if agent_id is not None:
        query = query.where(Memory.agent_id == agent_id)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(Memory.title.ilike(like), Memory.content.ilike(like)))
    return _out(db, list(db.execute(query).scalars()))


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    body: MemoryCreate, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> MemoryOut:
    upazila_id = agent_id = None
    if body.scope == "UPAZILA":
        if body.upazila_id is None:
            raise _unprocessable("upazila_id", "choose the Upazila this memory belongs to")
        if db.get(Upazila, body.upazila_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upazila not found")
        upazila_id = body.upazila_id
    elif body.scope == "AGENT":
        if body.agent_id is None:
            raise _unprocessable("agent_id", "choose the agent this memory belongs to")
        if db.get(Agent, body.agent_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        agent_id = body.agent_id
    try:
        contains = rules.check_customer_data(body.scope, body.title, body.content, body.contains_customer_data)
    except rules.MemoryRefused as exc:
        raise _unprocessable("contains_customer_data", str(exc)) from None
    actor = audit.chairman(auth.user.username)
    row = Memory(
        scope=body.scope,
        upazila_id=upazila_id,
        agent_id=agent_id,
        title=body.title,
        content=body.content,
        contains_customer_data=contains,
        created_by=actor,
        updated_by=actor,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        "memory.created",
        actor=actor,
        agent=db.get(Agent, agent_id) if agent_id is not None else None,
        summary=f"Added '{row.title}' to {_where(row)}.",
        details={"memory_id": row.id, "scope": row.scope},
    )
    db.commit()
    return _out(db, [row])[0]


@router.get("/{memory_id}", response_model=MemoryOut)
def get_memory(memory_id: int, db: Session = Depends(get_session)) -> MemoryOut:
    return _out(db, [_get(db, memory_id)])[0]


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int, body: MemoryPatch, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> MemoryOut:
    row = _get(db, memory_id)
    title = row.title if body.title is None else body.title
    content = row.content if body.content is None else body.content
    flagged = row.contains_customer_data if body.contains_customer_data is None else body.contains_customer_data
    try:
        contains = rules.check_customer_data(row.scope, title, content, flagged)
    except rules.MemoryRefused as exc:
        raise _unprocessable("contains_customer_data", str(exc)) from None
    changed = [
        name
        for name, old, new in (("title", row.title, title), ("content", row.content, content), ("contains_customer_data", row.contains_customer_data, contains))
        if old != new
    ]
    if changed:
        row.title, row.content, row.contains_customer_data = title, content, contains
        row.updated_by = audit.chairman(auth.user.username)
        audit.record(
            db,
            "memory.updated",
            actor=row.updated_by,
            agent=db.get(Agent, row.agent_id) if row.agent_id is not None else None,
            summary=f"Edited '{row.title}' in {_where(row)} ({', '.join(changed)}).",
            details={"memory_id": row.id, "scope": row.scope, "changed": changed},
        )
        db.commit()
    return _out(db, [row])[0]


@router.delete("/{memory_id}", response_model=MemoryDeleted)
def delete_memory(
    memory_id: int, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> MemoryDeleted:
    row = _get(db, memory_id)
    audit.record(
        db,
        "memory.deleted",
        actor=audit.chairman(auth.user.username),
        agent=db.get(Agent, row.agent_id) if row.agent_id is not None else None,
        summary=f"Deleted '{row.title}' from {_where(row)}.",
        details={"memory_id": row.id, "scope": row.scope},
    )
    db.delete(row)
    db.commit()
    return MemoryDeleted(deleted=True)

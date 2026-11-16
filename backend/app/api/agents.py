"""Agent registry API: agent templates, agents, their lifecycle and safe deletion.

Rules:
- An agent's Upazila, Union and Ward are derived from its office (nothing is stored twice).
- Tools come from the central registry (app/tools) and, like permissions, are enforced on every
  tool call (app.tools.check_tool_use). Every lifecycle change is written to the audit log.
- The Central Manager cannot be paused, disabled, deleted or moved out of Central Administration.
- An agent with history (tasks or messages) cannot be deleted — it is disabled instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.agent_catalog import PERMISSION_KEYS, PERMISSIONS
from app.api.fields import Description, IconKey, Name
from app.db import as_utc, get_session, utcnow
from app.models import Agent, AgentMessage, AgentTemplate, Office, Task, UnionUnit, Upazila, Ward
from app.providers import provider_names
from app.security import AuthContext, current_auth
from app.tools import all_tools, tool_keys

router = APIRouter(tags=["agents"])

Instructions = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Lifecycle = Literal["active", "paused", "disabled"]
PATH_SEPARATOR = " › "


# ---------------------------------------------------------------- schemas


class CatalogItemOut(BaseModel):
    key: str
    label: str
    description: str
    sensitive: bool  # a tool that always needs approval / the permission such a tool requires
    # tools only:
    risk: Literal["READ", "WRITE", "SENSITIVE"] | None = None
    available: bool = True  # False = registered, but it answers "not available yet"
    planned_for: str = ""
    required_permission: str | None = None


class AgentOptions(BaseModel):
    tools: list[CatalogItemOut]
    permissions: list[CatalogItemOut]
    providers: list[str]
    enforced: bool  # True since M4: every tool call is checked against them


class AgentTemplateOut(BaseModel):
    id: int
    key: str
    name: str
    role: str
    description: str
    avatar_key: str
    default_instructions: str
    default_tools: list[str]
    default_permissions: list[str]


class UnitRef(BaseModel):
    id: int
    name: str


class WardRef(BaseModel):
    id: int
    number: int
    name: str


class OfficeRef(BaseModel):
    id: int
    name: str
    kind: str


class AgentLocation(BaseModel):
    """Where the agent works. Everything above the office is derived from the office."""

    office: OfficeRef
    ward: WardRef | None
    union: UnitRef | None
    upazila: UnitRef | None
    path: str


class AgentOut(BaseModel):
    id: int
    display_name: str
    avatar_key: str
    role: str
    description: str
    template_id: int | None
    template_key: str | None
    template_name: str | None
    office_id: int | None
    location: AgentLocation | None  # None = the office was deleted
    system_instructions: str
    allowed_tools: list[str]
    permissions: list[str]
    provider: str
    memory_config: dict[str, Any]
    working_schedule: dict[str, Any]
    lifecycle: Lifecycle
    runtime_state: Literal["idle", "working", "waiting", "offline"]
    is_central_manager: bool
    has_history: bool  # True = it has tasks or messages, so it can only be disabled, not deleted
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


def _known(values: list[str] | None, allowed: frozenset[str], what: str) -> list[str] | None:
    if values is None:
        return None
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"unknown {what}: {', '.join(unknown)}")
    return list(dict.fromkeys(values))  # no duplicates, order kept


class _AgentFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Name | None = None
    description: Description | None = None
    avatar_key: IconKey | None = None
    system_instructions: Instructions | None = None
    allowed_tools: list[str] | None = None
    permissions: list[str] | None = None

    @field_validator("allowed_tools")
    @classmethod
    def _known_tools(cls, value: list[str] | None) -> list[str] | None:
        return _known(value, tool_keys(), "tool")

    @field_validator("permissions")
    @classmethod
    def _known_permissions(cls, value: list[str] | None) -> list[str] | None:
        return _known(value, PERMISSION_KEYS, "permission")


class AgentCreate(_AgentFields):
    """Template defaults are copied into the agent; any field given here replaces its default."""

    template_id: int
    display_name: Name
    office_id: int
    activate: bool = True  # False = create it paused


class AgentPatch(_AgentFields):
    display_name: Name | None = None
    office_id: int | None = None
    provider: str | None = None

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str | None) -> str | None:
        if value is not None and value not in provider_names():
            raise ValueError(f"unknown provider; available: {', '.join(provider_names())}")
        return value


class ConfirmDelete(BaseModel):
    confirm_name: str | None = None


class AgentDeleted(BaseModel):
    deleted: bool


# ---------------------------------------------------------------- helpers


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def tools_out() -> list[CatalogItemOut]:
    """The tool registry as the API shows it (GET /api/tools and the agent forms)."""
    return [
        CatalogItemOut(
            key=tool.key,
            label=tool.name,
            description=tool.description,
            sensitive=tool.needs_approval,
            risk=tool.risk.value,
            available=tool.available,
            planned_for=tool.planned_for,
            required_permission=tool.required_permission,
        )
        for tool in all_tools()
    ]


def _permissions_out() -> list[CatalogItemOut]:
    return [
        CatalogItemOut(key=item.key, label=item.label, description=item.description, sensitive=item.sensitive)
        for item in PERMISSIONS
    ]


def _audit(db: Session, auth: AuthContext, action: str, agent: Agent, summary: str, **details: Any) -> None:
    audit.record(db, action, actor=audit.chairman(auth.user.username), agent=agent, summary=summary, details=details)


def _template_out(row: AgentTemplate) -> AgentTemplateOut:
    return AgentTemplateOut(
        id=row.id,
        key=row.key,
        name=row.name,
        role=row.role,
        description=row.description,
        avatar_key=row.avatar_key,
        default_instructions=row.default_instructions,
        default_tools=list(row.default_tools),
        default_permissions=list(row.default_permissions),
    )


def agents_with_history(db: Session, agent_ids: list[int]) -> set[int]:
    """The agents among `agent_ids` that have history — any task or any message — and therefore
    cannot be deleted (three small queries, whatever the number of agents)."""
    if not agent_ids:
        return set()
    found: set[int] = set()
    for column in (Task.assigned_agent_id, AgentMessage.sender_agent_id, AgentMessage.receiver_agent_id):
        found |= set(db.execute(select(column).where(column.in_(agent_ids)).distinct()).scalars())
    return found


def location_of(office: Office, ward: Ward | None, union: UnionUnit | None, upazila: Upazila | None) -> AgentLocation:
    if ward is not None and union is not None and upazila is not None:
        path = PATH_SEPARATOR.join([upazila.name, union.name, f"Ward {ward.number}: {ward.name}"])
    else:
        path = office.name  # the Central Administration office has no ward
    return AgentLocation(
        office=OfficeRef(id=office.id, name=office.name, kind=office.kind),
        ward=WardRef(id=ward.id, number=ward.number, name=ward.name) if ward is not None else None,
        union=UnitRef(id=union.id, name=union.name) if union is not None else None,
        upazila=UnitRef(id=upazila.id, name=upazila.name) if upazila is not None else None,
        path=path,
    )


def agent_rows_query():  # noqa: ANN201
    """Agents with their template and derived location, in ONE query (outer joins)."""
    return (
        select(Agent, AgentTemplate, Office, Ward, UnionUnit, Upazila)
        .outerjoin(AgentTemplate, AgentTemplate.id == Agent.template_id)
        .outerjoin(Office, Office.id == Agent.office_id)
        .outerjoin(Ward, Ward.id == Office.ward_id)
        .outerjoin(UnionUnit, UnionUnit.id == Ward.union_id)
        .outerjoin(Upazila, Upazila.id == UnionUnit.upazila_id)
    )


def _agent_out(row: Any, history: set[int]) -> AgentOut:
    agent, template, office, ward, union, upazila = row
    return AgentOut(
        id=agent.id,
        display_name=agent.display_name,
        avatar_key=agent.avatar_key,
        role=agent.role,
        description=agent.description,
        template_id=agent.template_id,
        template_key=template.key if template is not None else None,
        template_name=template.name if template is not None else None,
        office_id=agent.office_id,
        location=location_of(office, ward, union, upazila) if office is not None else None,
        system_instructions=agent.system_instructions,
        allowed_tools=list(agent.allowed_tools),
        permissions=list(agent.permissions),
        provider=agent.provider,
        memory_config=dict(agent.memory_config),
        working_schedule=dict(agent.working_schedule),
        lifecycle=agent.lifecycle,
        runtime_state=agent.runtime_state,
        is_central_manager=agent.is_central_manager,
        has_history=agent.id in history,
        created_at=as_utc(agent.created_at),  # type: ignore[arg-type]
        updated_at=as_utc(agent.updated_at),  # type: ignore[arg-type]
        disabled_at=as_utc(agent.disabled_at),
    )


def _load(db: Session, agent_id: int) -> AgentOut:
    row = db.execute(agent_rows_query().where(Agent.id == agent_id)).first()
    if row is None:
        raise _not_found("Agent")
    return _agent_out(row, agents_with_history(db, [agent_id]))


def _get_agent(db: Session, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise _not_found("Agent")
    return agent


def _protect_central_manager(agent: Agent, action: str) -> None:
    if agent.is_central_manager:
        raise _conflict(f"The Central Manager cannot be {action}: the village needs it to route tasks.")


# ---------------------------------------------------------------- templates + options


@router.get("/agent-templates", response_model=list[AgentTemplateOut])
def list_agent_templates(db: Session = Depends(get_session)) -> list[AgentTemplateOut]:
    return [_template_out(row) for row in db.execute(select(AgentTemplate).order_by(AgentTemplate.id)).scalars()]


@router.get("/agent-options", response_model=AgentOptions)
def agent_options() -> AgentOptions:
    """The tools and permissions an agent can be given, with labels for the forms."""
    return AgentOptions(tools=tools_out(), permissions=_permissions_out(), providers=provider_names(), enforced=True)


# ---------------------------------------------------------------- agents


@router.get("/agents", response_model=list[AgentOut])
def list_agents(
    office_id: int | None = Query(default=None),
    upazila_id: int | None = Query(default=None),
    lifecycle: Lifecycle | None = Query(default=None),
    db: Session = Depends(get_session),
) -> list[AgentOut]:
    query = agent_rows_query().order_by(Agent.is_central_manager.desc(), Agent.id)
    if office_id is not None:
        query = query.where(Agent.office_id == office_id)
    if upazila_id is not None:
        query = query.where(Upazila.id == upazila_id)
    if lifecycle is not None:
        query = query.where(Agent.lifecycle == lifecycle)
    rows = db.execute(query).all()
    history = agents_with_history(db, [row[0].id for row in rows])
    return [_agent_out(row, history) for row in rows]


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    body: AgentCreate, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> AgentOut:
    template = db.get(AgentTemplate, body.template_id)
    if template is None:
        raise _not_found("Agent template")
    if db.get(Office, body.office_id) is None:
        raise _not_found("Office")
    agent = Agent(
        display_name=body.display_name,
        avatar_key=template.avatar_key if body.avatar_key is None else body.avatar_key,
        role=body.role or template.role,
        description=template.description if body.description is None else body.description,
        template_id=template.id,
        office_id=body.office_id,
        system_instructions=(
            template.default_instructions if body.system_instructions is None else body.system_instructions
        ),
        allowed_tools=list(template.default_tools) if body.allowed_tools is None else body.allowed_tools,
        permissions=list(template.default_permissions) if body.permissions is None else body.permissions,
        memory_config={},
        working_schedule={},
        lifecycle="active" if body.activate else "paused",
        runtime_state="idle" if body.activate else "offline",
    )
    db.add(agent)
    db.flush()
    _audit(
        db,
        auth,
        "agent.created",
        agent,
        f"Created '{agent.display_name}' ({agent.role}) as {agent.lifecycle}.",
        template=template.key,
        allowed_tools=list(agent.allowed_tools),
        permissions=list(agent.permissions),
    )
    db.commit()
    return _load(db, agent.id)


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, db: Session = Depends(get_session)) -> AgentOut:
    return _load(db, agent_id)


@router.patch("/agents/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: int, body: AgentPatch, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> AgentOut:
    agent = _get_agent(db, agent_id)
    changed: list[str] = []
    details: dict[str, Any] = {}
    if body.office_id is not None and body.office_id != agent.office_id:
        if agent.is_central_manager:
            raise _conflict("The Central Manager works in Central Administration and cannot be moved.")
        if db.get(Office, body.office_id) is None:
            raise _not_found("Office")
        agent.office_id = body.office_id
        changed.append("office_id")
    for field in (
        "display_name",
        "role",
        "description",
        "avatar_key",
        "system_instructions",
        "allowed_tools",
        "permissions",
        "provider",
    ):
        value = getattr(body, field)
        if value is None or value == getattr(agent, field):
            continue
        if field in ("allowed_tools", "permissions"):  # the audit log says exactly what was granted or taken
            before = list(getattr(agent, field))
            details[f"{field}_added"] = [item for item in value if item not in before]
            details[f"{field}_removed"] = [item for item in before if item not in value]
        setattr(agent, field, value)
        changed.append(field)
    if changed:
        _audit(db, auth, "agent.updated", agent, f"Changed {', '.join(changed)} of '{agent.display_name}'.", **details)
    db.commit()
    return _load(db, agent_id)


@router.post("/agents/{agent_id}/activate", response_model=AgentOut)
def activate_agent(
    agent_id: int, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> AgentOut:
    agent = _get_agent(db, agent_id)
    if agent.office_id is None:
        raise _conflict("This agent has no Office. Assign an Office before activating it.")
    if agent.lifecycle != "active":
        previous = agent.lifecycle
        agent.lifecycle = "active"
        agent.runtime_state = "idle"
        agent.disabled_at = None
        _audit(db, auth, "agent.activated", agent, f"Activated '{agent.display_name}' (it was {previous}).")
        db.commit()
    return _load(db, agent_id)


@router.post("/agents/{agent_id}/pause", response_model=AgentOut)
def pause_agent(
    agent_id: int, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> AgentOut:
    agent = _get_agent(db, agent_id)
    _protect_central_manager(agent, "paused")
    if agent.lifecycle != "paused":
        previous = agent.lifecycle
        agent.lifecycle = "paused"
        agent.runtime_state = "offline"
        agent.disabled_at = None
        _audit(db, auth, "agent.paused", agent, f"Paused '{agent.display_name}' (it was {previous}).")
        db.commit()
    return _load(db, agent_id)


@router.post("/agents/{agent_id}/disable", response_model=AgentOut)
def disable_agent(
    agent_id: int, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> AgentOut:
    agent = _get_agent(db, agent_id)
    _protect_central_manager(agent, "disabled")
    if agent.lifecycle != "disabled":
        previous = agent.lifecycle
        agent.lifecycle = "disabled"
        agent.runtime_state = "offline"
        agent.disabled_at = utcnow()
        _audit(db, auth, "agent.disabled", agent, f"Disabled '{agent.display_name}' (it was {previous}).")
        db.commit()
    return _load(db, agent_id)


@router.delete("/agents/{agent_id}", response_model=AgentDeleted)
def delete_agent(
    agent_id: int,
    body: ConfirmDelete | None = Body(default=None),
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_session),
) -> AgentDeleted:
    agent = _get_agent(db, agent_id)
    _protect_central_manager(agent, "deleted")
    if agent_id in agents_with_history(db, [agent_id]):
        raise _conflict(
            f"'{agent.display_name}' has task history, so it cannot be deleted. Disable it instead — "
            "its history is kept."
        )
    if body is None or body.confirm_name != agent.display_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Deletion must be confirmed with {"confirm_name": "<the exact name>"}',
        )
    _audit(db, auth, "agent.deleted", agent, f"Deleted '{agent.display_name}' ({agent.role}). It had no history.")
    db.delete(agent)
    db.commit()
    return AgentDeleted(deleted=True)

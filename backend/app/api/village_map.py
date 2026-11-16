"""GET /api/map — what the Interactive Village Map (and its list view) needs for ONE level.

  level=village            Central Administration + one building per Upazila
  level=upazila&id=<id>    the Unions of that Upazila
  level=union&id=<id>      the Wards of that Union (each Ward has one Office)
  level=ward&id=<id>       that Ward's Office and every agent working in it

The map never shows all offices at once: each request returns one level. A building carries its
child count, how many agents work in it (or below it), up to four of them to draw, and how many
of their tasks are open. Everything is counted at request time; the number of queries does not
grow with the size of the village.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import agent_activity
from app.db import get_session
from app.models import Agent, AgentTemplate, Office, Task, UnionUnit, Upazila, Village, Ward
from app.task_status import ACTIVE

router = APIRouter(prefix="/map", tags=["map"])

Level = Literal["village", "upazila", "union", "ward"]
PREVIEW_AGENTS = 4  # robots drawn in front of a building; the rest is "+n"


class MapAgent(BaseModel):
    id: int
    name: str
    role: str
    template_key: str | None
    activity: Literal["working", "idle", "waiting", "offline"]
    current_task_id: int | None


class MapTarget(BaseModel):
    level: Level
    id: int | None


class MapCrumb(MapTarget):
    label: str


class MapBuilding(BaseModel):
    id: int
    type: Literal["central", "upazila", "union", "ward"]
    name: str
    detail: str  # a second line: the Office's name, a Ward's responsibility, …
    child_count: int
    child_label: str  # what the children are: "Unions", "Wards", "Agents"
    agent_count: int  # agents working in this building or anywhere below it
    active_tasks: int  # their tasks that are not finished
    agents: list[MapAgent]  # the first few, to draw
    target: MapTarget | None  # where a click leads; None = nothing below (Central Administration)


class MapOut(BaseModel):
    level: Level
    id: int | None
    name: str
    breadcrumb: list[MapCrumb]  # from the village down to this place
    parent: MapTarget | None  # one level up; None at the village
    buildings: list[MapBuilding]
    office_name: str | None  # ward level: the Office whose workspaces are shown
    agents: list[MapAgent]  # ward level: everyone working in the Office
    agent_count: int  # agents in everything shown
    active_tasks: int


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


class _Scope:
    """The agents of one part of the village with their activity and open tasks (3 queries)."""

    def __init__(self, db: Session, *where: Any) -> None:
        rows = db.execute(
            select(Agent, AgentTemplate.key, Office.kind, Ward.id, Ward.union_id, UnionUnit.upazila_id)
            .outerjoin(AgentTemplate, AgentTemplate.id == Agent.template_id)
            .join(Office, Office.id == Agent.office_id)
            .outerjoin(Ward, Ward.id == Office.ward_id)
            .outerjoin(UnionUnit, UnionUnit.id == Ward.union_id)
            .where(*where)
            .order_by(Agent.is_central_manager.desc(), Agent.id)
        ).all()
        ids = [row[0].id for row in rows]
        activities = agent_activity.activity_of(db, {row[0].id: row[0].lifecycle for row in rows})
        open_tasks: dict[int, int] = (
            dict(
                db.execute(
                    select(Task.assigned_agent_id, func.count())
                    .where(Task.assigned_agent_id.in_(ids), Task.status.in_(ACTIVE), Task.kind != "health_check")
                    .group_by(Task.assigned_agent_id)
                ).all()
            )
            if ids
            else {}
        )
        # (agent, where it works, its open tasks)
        self.items: list[tuple[MapAgent, dict[str, Any], int]] = []
        for agent, template_key, office_kind, ward_id, union_id, upazila_id in rows:
            activity, task_id = activities[agent.id]
            self.items.append(
                (
                    MapAgent(
                        id=agent.id,
                        name=agent.display_name,
                        role=agent.role,
                        template_key=template_key,
                        activity=activity,  # type: ignore[arg-type]
                        current_task_id=task_id,
                    ),
                    {"central": office_kind == "central", "ward": ward_id, "union": union_id, "upazila": upazila_id},
                    open_tasks.get(agent.id, 0),
                )
            )

    def of(self, key: str, value: Any) -> tuple[list[MapAgent], int]:
        """(agents, their open tasks) of the part where `key` is `value`."""
        found = [(agent, tasks) for agent, place, tasks in self.items if place[key] == value]
        return [agent for agent, _tasks in found], sum(tasks for _agent, tasks in found)

    @property
    def totals(self) -> tuple[int, int]:
        return len(self.items), sum(tasks for _agent, _place, tasks in self.items)


def _building(kind: str, row_id: int, name: str, detail: str, children: int, child_label: str, scope: _Scope, key: str, value: Any, target: MapTarget | None) -> MapBuilding:
    agents, tasks = scope.of(key, value)
    return MapBuilding(
        id=row_id,
        type=kind,  # type: ignore[arg-type]
        name=name,
        detail=detail,
        child_count=children,
        child_label=child_label,
        agent_count=len(agents),
        active_tasks=tasks,
        agents=agents[:PREVIEW_AGENTS],
        target=target,
    )


def _out(level: Level, row_id: int | None, name: str, crumbs: list[MapCrumb], buildings: list[MapBuilding], scope: _Scope, **extra: Any) -> MapOut:
    agent_count, active_tasks = scope.totals
    parent = crumbs[-2] if len(crumbs) >= 2 else None
    return MapOut(
        level=level,
        id=row_id,
        name=name,
        breadcrumb=crumbs,
        parent=MapTarget(level=parent.level, id=parent.id) if parent is not None else None,
        buildings=buildings,
        office_name=extra.get("office_name"),
        agents=extra.get("agents", []),
        agent_count=agent_count,
        active_tasks=active_tasks,
    )


def _village_crumb(db: Session) -> MapCrumb:
    name = db.execute(select(Village.name).limit(1)).scalar_one_or_none() or "Village"
    return MapCrumb(level="village", id=None, label=name)


@router.get("", response_model=MapOut)
def village_map(
    level: Level = Query(default="village"),
    place_id: int | None = Query(default=None, alias="id", ge=1),
    db: Session = Depends(get_session),
) -> MapOut:
    if level != "village" and place_id is None:
        raise HTTPException(status_code=422, detail=[{"loc": ["query", "id"], "msg": f"id is required for level '{level}'", "type": "missing"}])
    village = _village_crumb(db)

    if level == "village":
        scope = _Scope(db)
        unions = dict(db.execute(select(UnionUnit.upazila_id, func.count()).group_by(UnionUnit.upazila_id)).all())
        central = db.execute(select(Office).where(Office.kind == "central")).scalar_one_or_none()
        buildings = []
        if central is not None:
            agents, _tasks = scope.of("central", True)
            buildings.append(_building("central", central.id, central.name, "The village's own office", len(agents), "Agents", scope, "central", True, None))
        for upazila in db.execute(select(Upazila).order_by(Upazila.sort_order, Upazila.id)).scalars():
            buildings.append(
                _building("upazila", upazila.id, upazila.name, upazila.description, unions.get(upazila.id, 0), "Unions", scope, "upazila", upazila.id, MapTarget(level="upazila", id=upazila.id))
            )
        return _out("village", None, village.label, [village], buildings, scope)

    if level == "upazila":
        upazila = db.get(Upazila, place_id)
        if upazila is None:
            raise _not_found("Upazila")
        scope = _Scope(db, UnionUnit.upazila_id == upazila.id)
        wards = dict(
            db.execute(
                select(Ward.union_id, func.count()).join(UnionUnit, UnionUnit.id == Ward.union_id).where(UnionUnit.upazila_id == upazila.id).group_by(Ward.union_id)
            ).all()
        )
        buildings = [
            _building("union", union.id, union.name, union.description, wards.get(union.id, 0), "Wards", scope, "union", union.id, MapTarget(level="union", id=union.id))
            for union in db.execute(select(UnionUnit).where(UnionUnit.upazila_id == upazila.id).order_by(UnionUnit.sort_order, UnionUnit.id)).scalars()
        ]
        crumbs = [village, MapCrumb(level="upazila", id=upazila.id, label=upazila.name)]
        return _out("upazila", upazila.id, upazila.name, crumbs, buildings, scope)

    if level == "union":
        union = db.get(UnionUnit, place_id)
        if union is None:
            raise _not_found("Union")
        upazila = db.get(Upazila, union.upazila_id)
        scope = _Scope(db, Ward.union_id == union.id)
        buildings = []
        for ward, office_name in db.execute(
            select(Ward, Office.name).outerjoin(Office, Office.ward_id == Ward.id).where(Ward.union_id == union.id).order_by(Ward.number)
        ).all():
            agents, _tasks = scope.of("ward", ward.id)
            buildings.append(
                _building("ward", ward.id, f"Ward {ward.number}: {ward.name}", office_name or "", len(agents), "Agents", scope, "ward", ward.id, MapTarget(level="ward", id=ward.id))
            )
        crumbs = [village, MapCrumb(level="upazila", id=union.upazila_id, label=upazila.name if upazila else ""), MapCrumb(level="union", id=union.id, label=union.name)]
        return _out("union", union.id, union.name, crumbs, buildings, scope)

    ward = db.get(Ward, place_id)
    if ward is None:
        raise _not_found("Ward")
    union = db.get(UnionUnit, ward.union_id)
    upazila = db.get(Upazila, union.upazila_id) if union is not None else None
    office_name = db.execute(select(Office.name).where(Office.ward_id == ward.id)).scalar_one_or_none()
    scope = _Scope(db, Ward.id == ward.id)
    agents, _tasks = scope.of("ward", ward.id)
    label = f"Ward {ward.number}: {ward.name}"
    crumbs = [
        village,
        MapCrumb(level="upazila", id=upazila.id if upazila else None, label=upazila.name if upazila else ""),
        MapCrumb(level="union", id=union.id if union else None, label=union.name if union else ""),
        MapCrumb(level="ward", id=ward.id, label=label),
    ]
    return _out("ward", ward.id, label, crumbs, [], scope, office_name=office_name, agents=agents)

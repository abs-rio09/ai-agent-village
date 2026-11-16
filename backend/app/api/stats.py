"""GET /api/stats/overview — the dashboard's numbers (docs/SPEC.md §13). Every value is an SQL
count taken at the moment of the request; nothing here is estimated, cached or faked.

Task numbers count every task — requests of the Chairman, delegated and scheduled tasks — except
the scheduler's own health checks (one every 10 minutes), which are housekeeping, not work.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Agent, Approval, Office, Task, UnionUnit, Upazila, Ward
from app.task_status import FAILED, RUNNING, SUCCEEDED

router = APIRouter(prefix="/stats", tags=["stats"])

HOUSEKEEPING = "health_check"


class OverviewStats(BaseModel):
    upazilas: int
    unions: int
    wards: int
    # Every office row: the ward offices plus the Central Administration office.
    offices: int
    ward_offices: int
    # Every agent, whatever its lifecycle; active_agents are the ones that can receive tasks.
    agents: int
    active_agents: int
    # Tasks (without the scheduler's health checks):
    running_tasks: int  # status RUNNING right now
    completed_tasks: int  # status SUCCEEDED
    failed_tasks: int  # status FAILED
    # Requests of agents that wait for the Chairman's decision.
    pending_approvals: int


def _count(model, *where):  # noqa: ANN001, ANN002, ANN202
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


def _tasks(status: str):  # noqa: ANN202
    return _count(Task, Task.status == status, Task.kind != HOUSEKEEPING)


@router.get("/overview", response_model=OverviewStats)
def overview(db: Session = Depends(get_session)) -> OverviewStats:
    row = db.execute(  # one statement, whatever the size of the village
        select(
            _count(Upazila),
            _count(UnionUnit),
            _count(Ward),
            _count(Office),
            _count(Office, Office.kind == "ward"),
            _count(Agent),
            _count(Agent, Agent.lifecycle == "active"),
            _tasks(RUNNING),
            _tasks(SUCCEEDED),
            _tasks(FAILED),
            _count(Approval, Approval.status == "PENDING"),
        )
    ).one()
    return OverviewStats(
        upazilas=row[0],
        unions=row[1],
        wards=row[2],
        offices=row[3],
        ward_offices=row[4],
        agents=row[5],
        active_agents=row[6],
        running_tasks=row[7],
        completed_tasks=row[8],
        failed_tasks=row[9],
        pending_approvals=row[10],
    )

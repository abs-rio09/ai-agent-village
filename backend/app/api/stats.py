"""GET /api/stats/overview — real counts for the dashboard. Nothing here is estimated or faked.

Agents and tasks do not exist yet (M3+), so they are deliberately absent from the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Office, UnionUnit, Upazila, Ward

router = APIRouter(prefix="/stats", tags=["stats"])


class OverviewStats(BaseModel):
    upazilas: int
    unions: int
    wards: int
    # Every office row: the ward offices plus the Central Administration office.
    offices: int
    ward_offices: int


@router.get("/overview", response_model=OverviewStats)
def overview(db: Session = Depends(get_session)) -> OverviewStats:
    row = db.execute(
        select(
            select(func.count()).select_from(Upazila).scalar_subquery(),
            select(func.count()).select_from(UnionUnit).scalar_subquery(),
            select(func.count()).select_from(Ward).scalar_subquery(),
            select(func.count()).select_from(Office).scalar_subquery(),
            select(func.count()).select_from(Office).where(Office.kind == "ward").scalar_subquery(),
        )
    ).one()
    return OverviewStats(upazilas=row[0], unions=row[1], wards=row[2], offices=row[3], ward_offices=row[4])

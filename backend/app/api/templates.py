"""Upazila templates: list and edit, without touching code.

A template is a suggested structure: Union names plus a default ward set that every generated
Union receives. Edits change FUTURE generation only — Upazilas, Unions and Wards that already
exist are copies and are never modified by a template edit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.fields import Description, IconKey, Name, Responsibility
from app.db import get_session
from app.models import UnionTemplate, UpazilaTemplate, WardTemplate

router = APIRouter(prefix="/templates", tags=["templates"])


class UnionTemplateOut(BaseModel):
    id: int
    name: str
    sort_order: int


class WardTemplateOut(BaseModel):
    id: int
    number: int
    name: str
    responsibility: str


class TemplateOut(BaseModel):
    key: str
    name: str
    description: str
    icon: str
    sort_order: int
    unions: list[UnionTemplateOut]
    wards: list[WardTemplateOut]


class TemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description | None = None
    icon: IconKey | None = None


class UnionTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name


class WardTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    responsibility: Responsibility | None = None


def _union_out(row: UnionTemplate) -> UnionTemplateOut:
    return UnionTemplateOut(id=row.id, name=row.name, sort_order=row.sort_order)


def _ward_out(row: WardTemplate) -> WardTemplateOut:
    return WardTemplateOut(id=row.id, number=row.number, name=row.name, responsibility=row.responsibility)


def _load(db: Session, key: str | None = None) -> list[TemplateOut]:
    """All templates (or one) with their unions and wards: three queries, whatever the size."""
    templates_query = select(UpazilaTemplate).order_by(UpazilaTemplate.sort_order, UpazilaTemplate.key)
    unions_query = select(UnionTemplate).order_by(UnionTemplate.sort_order, UnionTemplate.id)
    wards_query = select(WardTemplate).order_by(WardTemplate.number)
    if key is not None:
        templates_query = templates_query.where(UpazilaTemplate.key == key)
        unions_query = unions_query.where(UnionTemplate.upazila_template_key == key)
        wards_query = wards_query.where(WardTemplate.upazila_template_key == key)
    unions: dict[str, list[UnionTemplateOut]] = {}
    for union in db.execute(unions_query).scalars():
        unions.setdefault(union.upazila_template_key, []).append(_union_out(union))
    wards: dict[str, list[WardTemplateOut]] = {}
    for ward in db.execute(wards_query).scalars():
        wards.setdefault(ward.upazila_template_key, []).append(_ward_out(ward))
    return [
        TemplateOut(
            key=template.key,
            name=template.name,
            description=template.description,
            icon=template.icon,
            sort_order=template.sort_order,
            unions=unions.get(template.key, []),
            wards=wards.get(template.key, []),
        )
        for template in db.execute(templates_query).scalars()
    ]


def _commit(db: Session, conflict: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict) from None


@router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_session)) -> list[TemplateOut]:
    return _load(db)


@router.patch("/{key}", response_model=TemplateOut)
def update_template(key: str, body: TemplatePatch, db: Session = Depends(get_session)) -> TemplateOut:
    template = db.get(UpazilaTemplate, key)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upazila template not found")
    if body.name is not None:
        template.name = body.name
    if body.description is not None:
        template.description = body.description
    if body.icon is not None:
        template.icon = body.icon
    _commit(db, f"Another Upazila template is already named '{body.name}'")
    return _load(db, key)[0]


@router.patch("/unions/{union_template_id}", response_model=UnionTemplateOut)
def update_union_template(
    union_template_id: int, body: UnionTemplatePatch, db: Session = Depends(get_session)
) -> UnionTemplateOut:
    union = db.get(UnionTemplate, union_template_id)
    if union is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Union template not found")
    union.name = body.name
    _commit(db, f"This template already has a Union named '{body.name}'")
    return _union_out(union)


@router.patch("/wards/{ward_template_id}", response_model=WardTemplateOut)
def update_ward_template(
    ward_template_id: int, body: WardTemplatePatch, db: Session = Depends(get_session)
) -> WardTemplateOut:
    ward = db.get(WardTemplate, ward_template_id)
    if ward is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ward template not found")
    if body.name is not None:
        ward.name = body.name
    if body.responsibility is not None:
        ward.responsibility = body.responsibility
    db.commit()
    return _ward_out(ward)

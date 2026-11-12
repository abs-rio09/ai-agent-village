"""Organization API: Upazila -> Union -> Ward -> Office, the org tree and standard generation.

Nothing here is created automatically at setup: Upazilas come from the "standard" action or
from the create form, and Unions/Wards/Offices from "generate-standard" or by hand.
Unit counts are never hardcoded — they come from the template rows.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.fields import Description, IconKey, Name, Responsibility
from app.db import get_session
from app.models import Office, UnionTemplate, UnionUnit, Upazila, UpazilaTemplate, Village, Ward, WardTemplate

router = APIRouter(tags=["organization"])


# ---------------------------------------------------------------- schemas


class UpazilaCounts(BaseModel):
    unions: int = 0
    wards: int = 0
    offices: int = 0


class UnionCounts(BaseModel):
    wards: int = 0
    offices: int = 0


class UpazilaOut(BaseModel):
    id: int
    name: str
    description: str
    icon: str
    template_key: str | None
    sort_order: int
    counts: UpazilaCounts


class UnionOut(BaseModel):
    id: int
    upazila_id: int
    name: str
    description: str
    sort_order: int
    counts: UnionCounts


class OfficeOut(BaseModel):
    id: int
    kind: Literal["ward", "central"]
    ward_id: int | None
    name: str
    description: str


class WardOut(BaseModel):
    id: int
    union_id: int
    number: int
    name: str
    responsibility: str
    office: OfficeOut | None


class UpazilaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description = ""
    icon: IconKey | None = None  # defaults to the template's icon
    template_key: str | None = None


class UpazilaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description | None = None
    icon: IconKey | None = None
    template_key: str | None = None  # send null to detach the Upazila from its template
    sort_order: int | None = None


class UnionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description = ""


class UnionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description | None = None
    sort_order: int | None = None


class WardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None  # defaults to "Ward <number>"
    responsibility: Responsibility = ""


class WardPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    responsibility: Responsibility | None = None


class OfficePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description | None = None


class ConfirmDelete(BaseModel):
    confirm_name: str | None = None


class DeleteResult(BaseModel):
    deleted: bool
    upazilas: int = 0
    unions: int = 0
    wards: int = 0
    offices: int = 0


class StandardUpazilasResult(BaseModel):
    created: list[UpazilaOut]
    skipped: list[str]


class GenerateResult(BaseModel):
    unions_created: int
    wards_created: int
    offices_created: int
    skipped: int  # template Unions that already exist in this Upazila (left untouched)


class TreeWard(BaseModel):
    id: int
    number: int
    name: str
    responsibility: str
    office: OfficeOut | None


class TreeUnion(BaseModel):
    id: int
    name: str
    description: str
    counts: UnionCounts
    wards: list[TreeWard]


class TreeUpazila(BaseModel):
    id: int
    name: str
    description: str
    icon: str
    template_key: str | None
    counts: UpazilaCounts
    unions: list[TreeUnion]


class TreeVillage(BaseModel):
    id: int
    name: str


class OrgTree(BaseModel):
    village: TreeVillage
    central_office: OfficeOut | None
    counts: UpazilaCounts  # ward offices only; the central office is listed separately
    upazila_count: int
    upazilas: list[TreeUpazila]


# ---------------------------------------------------------------- helpers


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _commit(db: Session, conflict: str = "That name or number is already in use") -> None:
    """Commit; a unique-constraint race that slipped past the pre-check becomes a 409."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict(conflict) from None


def _village_id(db: Session) -> int:
    village_id = db.execute(select(Village.id).order_by(Village.id).limit(1)).scalar_one_or_none()
    if village_id is None:
        raise _conflict("The village has not been set up yet")
    return village_id


def _require_confirmation(body: ConfirmDelete | None, name: str) -> None:
    if body is None or body.confirm_name != name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Deletion must be confirmed with {"confirm_name": "<the exact name>"}',
        )


def default_office_name(ward_name: str) -> str:
    return f"{ward_name[:73]} Office"  # office names are limited to 80 characters


def _office_out(office: Office) -> OfficeOut:
    return OfficeOut(
        id=office.id,
        kind=office.kind,  # type: ignore[arg-type]
        ward_id=office.ward_id,
        name=office.name,
        description=office.description,
    )


def _ward_out(ward: Ward, office: Office | None) -> WardOut:
    return WardOut(
        id=ward.id,
        union_id=ward.union_id,
        number=ward.number,
        name=ward.name,
        responsibility=ward.responsibility,
        office=_office_out(office) if office is not None else None,
    )


def _upazila_out(upazila: Upazila, counts: UpazilaCounts | None = None) -> UpazilaOut:
    return UpazilaOut(
        id=upazila.id,
        name=upazila.name,
        description=upazila.description,
        icon=upazila.icon,
        template_key=upazila.template_key,
        sort_order=upazila.sort_order,
        counts=counts or UpazilaCounts(),
    )


def _union_out(union: UnionUnit, counts: UnionCounts | None = None) -> UnionOut:
    return UnionOut(
        id=union.id,
        upazila_id=union.upazila_id,
        name=union.name,
        description=union.description,
        sort_order=union.sort_order,
        counts=counts or UnionCounts(),
    )


def _upazila_counts(db: Session, upazila_id: int | None = None) -> dict[int, UpazilaCounts]:
    """Unions, wards and ward offices per Upazila in ONE grouped query."""
    query = (
        select(
            UnionUnit.upazila_id,
            func.count(func.distinct(UnionUnit.id)),
            func.count(func.distinct(Ward.id)),
            func.count(func.distinct(Office.id)),
        )
        .outerjoin(Ward, Ward.union_id == UnionUnit.id)
        .outerjoin(Office, Office.ward_id == Ward.id)
        .group_by(UnionUnit.upazila_id)
    )
    if upazila_id is not None:
        query = query.where(UnionUnit.upazila_id == upazila_id)
    return {row[0]: UpazilaCounts(unions=row[1], wards=row[2], offices=row[3]) for row in db.execute(query)}


def _union_counts(db: Session, *, upazila_id: int | None = None, union_id: int | None = None) -> dict[int, UnionCounts]:
    """Wards and offices per Union in ONE grouped query."""
    query = (
        select(Ward.union_id, func.count(Ward.id), func.count(Office.id))
        .outerjoin(Office, Office.ward_id == Ward.id)
        .group_by(Ward.union_id)
    )
    if union_id is not None:
        query = query.where(Ward.union_id == union_id)
    if upazila_id is not None:
        query = query.join(UnionUnit, UnionUnit.id == Ward.union_id).where(UnionUnit.upazila_id == upazila_id)
    return {row[0]: UnionCounts(wards=row[1], offices=row[2]) for row in db.execute(query)}


def _get_upazila(db: Session, upazila_id: int) -> Upazila:
    upazila = db.get(Upazila, upazila_id)
    if upazila is None:
        raise _not_found("Upazila")
    return upazila


def _get_union(db: Session, union_id: int) -> UnionUnit:
    union = db.get(UnionUnit, union_id)
    if union is None:
        raise _not_found("Union")
    return union


def _get_ward(db: Session, ward_id: int) -> Ward:
    ward = db.get(Ward, ward_id)
    if ward is None:
        raise _not_found("Ward")
    return ward


def _ward_office(db: Session, ward_id: int) -> Office | None:
    return db.execute(select(Office).where(Office.ward_id == ward_id)).scalar_one_or_none()


def _next_sort_order(db: Session, column, *where) -> int:  # noqa: ANN001, ANN002
    return (db.execute(select(func.max(column)).where(*where)).scalar_one() or 0) + 1


def _lock_for_write(db: Session, model, row_id: int) -> bool:  # noqa: ANN001
    """Write to a parent row FIRST (a no-op "id = id"): the UPDATE takes SQLite's write lock, so a
    concurrent request waits (busy_timeout) instead of reading the same "what is missing / next
    number" state. Returns False when the row does not exist. The caller commits or rolls back."""
    result = db.execute(update(model).where(model.id == row_id).values(id=model.id))
    return result.rowcount == 1


# ---------------------------------------------------------------- upazilas


@router.get("/upazilas", response_model=list[UpazilaOut])
def list_upazilas(db: Session = Depends(get_session)) -> list[UpazilaOut]:
    counts = _upazila_counts(db)
    upazilas = db.execute(select(Upazila).order_by(Upazila.sort_order, Upazila.id)).scalars()
    return [_upazila_out(upazila, counts.get(upazila.id)) for upazila in upazilas]


@router.post("/upazilas", response_model=UpazilaOut, status_code=status.HTTP_201_CREATED)
def create_upazila(body: UpazilaCreate, db: Session = Depends(get_session)) -> UpazilaOut:
    village_id = _village_id(db)
    icon = body.icon
    if body.template_key is not None:
        template = db.get(UpazilaTemplate, body.template_key)
        if template is None:
            raise _not_found("Upazila template")
        if icon is None:
            icon = template.icon
    taken = _conflict(f"An Upazila named '{body.name}' already exists")
    if db.execute(select(Upazila.id).where(Upazila.village_id == village_id, Upazila.name == body.name)).first():
        raise taken
    upazila = Upazila(
        village_id=village_id,
        name=body.name,
        description=body.description,
        icon=icon or "",
        template_key=body.template_key,
        sort_order=_next_sort_order(db, Upazila.sort_order, Upazila.village_id == village_id),
    )
    db.add(upazila)
    _commit(db, taken.detail)
    return _upazila_out(upazila)


@router.post("/upazilas/standard", response_model=StandardUpazilasResult)
def create_standard_upazilas(db: Session = Depends(get_session)) -> StandardUpazilasResult:
    """One Upazila per template (no Unions yet). Idempotent: names that already exist are skipped."""
    village_id = _village_id(db)
    if not _lock_for_write(db, Village, village_id):
        db.rollback()
        raise _not_found("Village")
    existing = set(db.execute(select(Upazila.name).where(Upazila.village_id == village_id)).scalars())
    sort_order = _next_sort_order(db, Upazila.sort_order, Upazila.village_id == village_id)
    created: list[Upazila] = []
    skipped: list[str] = []
    templates = db.execute(select(UpazilaTemplate).order_by(UpazilaTemplate.sort_order, UpazilaTemplate.key)).scalars()
    for template in templates:
        if template.name in existing:
            skipped.append(template.name)
            continue
        upazila = Upazila(
            village_id=village_id,
            name=template.name,
            description=template.description,
            icon=template.icon,
            template_key=template.key,
            sort_order=sort_order,
        )
        sort_order += 1
        db.add(upazila)
        created.append(upazila)
    _commit(db)
    return StandardUpazilasResult(created=[_upazila_out(upazila) for upazila in created], skipped=skipped)


@router.get("/upazilas/{upazila_id}", response_model=UpazilaOut)
def get_upazila(upazila_id: int, db: Session = Depends(get_session)) -> UpazilaOut:
    upazila = _get_upazila(db, upazila_id)
    return _upazila_out(upazila, _upazila_counts(db, upazila_id).get(upazila_id))


@router.patch("/upazilas/{upazila_id}", response_model=UpazilaOut)
def update_upazila(upazila_id: int, body: UpazilaPatch, db: Session = Depends(get_session)) -> UpazilaOut:
    upazila = _get_upazila(db, upazila_id)
    taken = _conflict(f"An Upazila named '{body.name}' already exists")
    if body.name is not None and body.name != upazila.name:
        clash = select(Upazila.id).where(Upazila.village_id == upazila.village_id, Upazila.name == body.name)
        if db.execute(clash).first():
            raise taken
        upazila.name = body.name
    if body.description is not None:
        upazila.description = body.description
    if body.icon is not None:
        upazila.icon = body.icon
    if body.sort_order is not None:
        upazila.sort_order = body.sort_order
    if "template_key" in body.model_fields_set:
        if body.template_key is not None and db.get(UpazilaTemplate, body.template_key) is None:
            raise _not_found("Upazila template")
        upazila.template_key = body.template_key
    _commit(db, taken.detail)
    return _upazila_out(upazila, _upazila_counts(db, upazila_id).get(upazila_id))


@router.delete("/upazilas/{upazila_id}", response_model=DeleteResult)
def delete_upazila(
    upazila_id: int, body: ConfirmDelete | None = Body(default=None), db: Session = Depends(get_session)
) -> DeleteResult:
    upazila = _get_upazila(db, upazila_id)
    _require_confirmation(body, upazila.name)
    # TODO(M3): refuse (409) while any Office below this Upazila still has agents assigned.
    counts = _upazila_counts(db, upazila_id).get(upazila_id, UpazilaCounts())
    db.execute(delete(Upazila).where(Upazila.id == upazila_id))  # FKs cascade to unions, wards, offices
    db.commit()
    return DeleteResult(deleted=True, upazilas=1, unions=counts.unions, wards=counts.wards, offices=counts.offices)


# ---------------------------------------------------------------- standard structure


def _generation_plan(db: Session, upazila: Upazila) -> tuple[list[UnionTemplate], list[WardTemplate], int]:
    """(template Unions missing from this Upazila, the template's ward set, how many already exist)."""
    union_templates = (
        db.execute(
            select(UnionTemplate)
            .where(UnionTemplate.upazila_template_key == upazila.template_key)
            .order_by(UnionTemplate.sort_order, UnionTemplate.id)
        )
        .scalars()
        .all()
    )
    existing = set(db.execute(select(UnionUnit.name).where(UnionUnit.upazila_id == upazila.id)).scalars())
    missing = [template for template in union_templates if template.name not in existing]
    ward_templates = (
        db.execute(
            select(WardTemplate)
            .where(WardTemplate.upazila_template_key == upazila.template_key)
            .order_by(WardTemplate.number)
        )
        .scalars()
        .all()
    )
    return missing, list(ward_templates), len(union_templates) - len(missing)


def _no_template() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This Upazila has no template, so there is no standard structure to generate",
    )


@router.get("/upazilas/{upazila_id}/generate-standard/preview", response_model=GenerateResult)
def preview_standard_structure(upazila_id: int, db: Session = Depends(get_session)) -> GenerateResult:
    """What generate-standard would create right now. Writes nothing."""
    upazila = _get_upazila(db, upazila_id)
    if upazila.template_key is None:
        raise _no_template()
    missing, ward_templates, skipped = _generation_plan(db, upazila)
    wards = len(missing) * len(ward_templates)
    return GenerateResult(unions_created=len(missing), wards_created=wards, offices_created=wards, skipped=skipped)


@router.post("/upazilas/{upazila_id}/generate-standard", response_model=GenerateResult)
def generate_standard_structure(upazila_id: int, db: Session = Depends(get_session)) -> GenerateResult:
    """Create the template Unions this Upazila is missing, each with the template's wards and one
    office per ward — all in ONE transaction. Existing Unions are left untouched, so a second
    run creates nothing."""
    try:
        if not _lock_for_write(db, Upazila, upazila_id):
            raise _not_found("Upazila")
        upazila = _get_upazila(db, upazila_id)
        if upazila.template_key is None:
            raise _no_template()
        missing, ward_templates, skipped = _generation_plan(db, upazila)
        sort_order = _next_sort_order(db, UnionUnit.sort_order, UnionUnit.upazila_id == upazila_id)
        wards_created = 0
        for union_template in missing:
            union = UnionUnit(upazila_id=upazila_id, name=union_template.name, description="", sort_order=sort_order)
            sort_order += 1
            db.add(union)
            db.flush()
            wards = [
                Ward(union_id=union.id, number=template.number, name=template.name, responsibility=template.responsibility)
                for template in ward_templates
            ]
            db.add_all(wards)
            db.flush()
            db.add_all(
                [Office(kind="ward", ward_id=ward.id, name=default_office_name(ward.name), description="") for ward in wards]
            )
            wards_created += len(wards)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict("The structure changed while it was being generated. Nothing was created; try again.") from None
    except BaseException:
        db.rollback()  # nothing is kept from a half-finished generation
        raise
    return GenerateResult(
        unions_created=len(missing), wards_created=wards_created, offices_created=wards_created, skipped=skipped
    )


# ---------------------------------------------------------------- unions


@router.get("/upazilas/{upazila_id}/unions", response_model=list[UnionOut])
def list_unions(upazila_id: int, db: Session = Depends(get_session)) -> list[UnionOut]:
    _get_upazila(db, upazila_id)
    counts = _union_counts(db, upazila_id=upazila_id)
    unions = db.execute(
        select(UnionUnit).where(UnionUnit.upazila_id == upazila_id).order_by(UnionUnit.sort_order, UnionUnit.id)
    ).scalars()
    return [_union_out(union, counts.get(union.id)) for union in unions]


@router.post("/upazilas/{upazila_id}/unions", response_model=UnionOut, status_code=status.HTTP_201_CREATED)
def create_union(upazila_id: int, body: UnionCreate, db: Session = Depends(get_session)) -> UnionOut:
    upazila = _get_upazila(db, upazila_id)
    taken = _conflict(f"'{upazila.name}' already has a Union named '{body.name}'")
    if db.execute(select(UnionUnit.id).where(UnionUnit.upazila_id == upazila_id, UnionUnit.name == body.name)).first():
        raise taken
    union = UnionUnit(
        upazila_id=upazila_id,
        name=body.name,
        description=body.description,
        sort_order=_next_sort_order(db, UnionUnit.sort_order, UnionUnit.upazila_id == upazila_id),
    )
    db.add(union)
    _commit(db, taken.detail)
    return _union_out(union)


@router.get("/unions/{union_id}", response_model=UnionOut)
def get_union(union_id: int, db: Session = Depends(get_session)) -> UnionOut:
    union = _get_union(db, union_id)
    return _union_out(union, _union_counts(db, union_id=union_id).get(union_id))


@router.patch("/unions/{union_id}", response_model=UnionOut)
def update_union(union_id: int, body: UnionPatch, db: Session = Depends(get_session)) -> UnionOut:
    union = _get_union(db, union_id)
    taken = _conflict(f"This Upazila already has a Union named '{body.name}'")
    if body.name is not None and body.name != union.name:
        clash = select(UnionUnit.id).where(UnionUnit.upazila_id == union.upazila_id, UnionUnit.name == body.name)
        if db.execute(clash).first():
            raise taken
        union.name = body.name
    if body.description is not None:
        union.description = body.description
    if body.sort_order is not None:
        union.sort_order = body.sort_order
    _commit(db, taken.detail)
    return _union_out(union, _union_counts(db, union_id=union_id).get(union_id))


@router.delete("/unions/{union_id}", response_model=DeleteResult)
def delete_union(
    union_id: int, body: ConfirmDelete | None = Body(default=None), db: Session = Depends(get_session)
) -> DeleteResult:
    union = _get_union(db, union_id)
    _require_confirmation(body, union.name)
    # TODO(M3): refuse (409) while any Office below this Union still has agents assigned.
    counts = _union_counts(db, union_id=union_id).get(union_id, UnionCounts())
    db.execute(delete(UnionUnit).where(UnionUnit.id == union_id))  # FKs cascade to wards and offices
    db.commit()
    return DeleteResult(deleted=True, unions=1, wards=counts.wards, offices=counts.offices)


# ---------------------------------------------------------------- wards


@router.get("/unions/{union_id}/wards", response_model=list[WardOut])
def list_wards(union_id: int, db: Session = Depends(get_session)) -> list[WardOut]:
    _get_union(db, union_id)
    rows = db.execute(
        select(Ward, Office)
        .outerjoin(Office, Office.ward_id == Ward.id)
        .where(Ward.union_id == union_id)
        .order_by(Ward.number)
    )
    return [_ward_out(ward, office) for ward, office in rows]


@router.post("/unions/{union_id}/wards", response_model=WardOut, status_code=status.HTTP_201_CREATED)
def create_ward(
    union_id: int, body: WardCreate | None = Body(default=None), db: Session = Depends(get_session)
) -> WardOut:
    """Add the next ward number to a Union, together with the ward's office."""
    body = body or WardCreate()
    if not _lock_for_write(db, UnionUnit, union_id):
        db.rollback()
        raise _not_found("Union")
    number = _next_sort_order(db, Ward.number, Ward.union_id == union_id)
    ward = Ward(
        union_id=union_id, number=number, name=body.name or f"Ward {number}", responsibility=body.responsibility
    )
    db.add(ward)
    db.flush()
    office = Office(kind="ward", ward_id=ward.id, name=default_office_name(ward.name), description="")
    db.add(office)
    _commit(db)
    return _ward_out(ward, office)


@router.get("/wards/{ward_id}", response_model=WardOut)
def get_ward(ward_id: int, db: Session = Depends(get_session)) -> WardOut:
    ward = _get_ward(db, ward_id)
    return _ward_out(ward, _ward_office(db, ward_id))


@router.patch("/wards/{ward_id}", response_model=WardOut)
def update_ward(ward_id: int, body: WardPatch, db: Session = Depends(get_session)) -> WardOut:
    ward = _get_ward(db, ward_id)
    office = _ward_office(db, ward_id)
    if body.name is not None and body.name != ward.name:
        # An office that still carries its automatic name follows the ward's new name;
        # an office the owner renamed by hand is left alone.
        if office is not None and office.name == default_office_name(ward.name):
            office.name = default_office_name(body.name)
        ward.name = body.name
    if body.responsibility is not None:
        ward.responsibility = body.responsibility
    db.commit()
    return _ward_out(ward, office)


@router.delete("/wards/{ward_id}", response_model=DeleteResult)
def delete_ward(
    ward_id: int, body: ConfirmDelete | None = Body(default=None), db: Session = Depends(get_session)
) -> DeleteResult:
    ward = _get_ward(db, ward_id)
    _require_confirmation(body, ward.name)
    # TODO(M3): refuse (409) while this Ward's Office still has agents assigned.
    offices = db.execute(select(func.count()).select_from(Office).where(Office.ward_id == ward_id)).scalar_one()
    db.execute(delete(Ward).where(Ward.id == ward_id))  # the FK cascades to the ward's office
    db.commit()
    return DeleteResult(deleted=True, wards=1, offices=offices)


# ---------------------------------------------------------------- offices


def _central_office(db: Session) -> Office | None:
    return db.execute(select(Office).where(Office.kind == "central")).scalar_one_or_none()


@router.get("/offices/central", response_model=OfficeOut)
def get_central_office(db: Session = Depends(get_session)) -> OfficeOut:
    office = _central_office(db)
    if office is None:
        raise _not_found("Central Administration office")
    return _office_out(office)


@router.get("/offices/{office_id}", response_model=OfficeOut)
def get_office(office_id: int, db: Session = Depends(get_session)) -> OfficeOut:
    office = db.get(Office, office_id)
    if office is None:
        raise _not_found("Office")
    return _office_out(office)


@router.patch("/offices/{office_id}", response_model=OfficeOut)
def update_office(office_id: int, body: OfficePatch, db: Session = Depends(get_session)) -> OfficeOut:
    office = db.get(Office, office_id)
    if office is None:
        raise _not_found("Office")
    if body.name is not None:
        office.name = body.name
    if body.description is not None:
        office.description = body.description
    db.commit()
    return _office_out(office)


# ---------------------------------------------------------------- tree


@router.get("/org/tree", response_model=OrgTree)
def org_tree(db: Session = Depends(get_session)) -> OrgTree:
    """The whole organization as one nested tree with counts on every node.

    Five queries regardless of size (village, central office, upazilas, unions, wards+offices);
    the nesting and the counts are assembled in memory, so there is no N+1.
    """
    village = db.execute(select(Village.id, Village.name).order_by(Village.id).limit(1)).first()
    if village is None:
        raise _conflict("The village has not been set up yet")
    central = _central_office(db)
    upazilas = db.execute(
        select(Upazila).where(Upazila.village_id == village.id).order_by(Upazila.sort_order, Upazila.id)
    ).scalars()
    unions = db.execute(
        select(UnionUnit)
        .join(Upazila, Upazila.id == UnionUnit.upazila_id)
        .where(Upazila.village_id == village.id)
        .order_by(UnionUnit.sort_order, UnionUnit.id)
    ).scalars()
    ward_rows = db.execute(
        select(Ward, Office)
        .join(UnionUnit, UnionUnit.id == Ward.union_id)
        .join(Upazila, Upazila.id == UnionUnit.upazila_id)
        .outerjoin(Office, Office.ward_id == Ward.id)
        .where(Upazila.village_id == village.id)
        .order_by(Ward.number, Ward.id)
    )

    upazila_nodes = {
        upazila.id: TreeUpazila(
            id=upazila.id,
            name=upazila.name,
            description=upazila.description,
            icon=upazila.icon,
            template_key=upazila.template_key,
            counts=UpazilaCounts(),
            unions=[],
        )
        for upazila in upazilas
    }
    union_nodes: dict[int, TreeUnion] = {}
    union_parent: dict[int, TreeUpazila] = {}
    for union in unions:
        node = TreeUnion(id=union.id, name=union.name, description=union.description, counts=UnionCounts(), wards=[])
        parent = upazila_nodes[union.upazila_id]
        parent.unions.append(node)
        parent.counts.unions += 1
        union_nodes[union.id] = node
        union_parent[union.id] = parent
    total = UpazilaCounts(unions=len(union_nodes))
    for ward, office in ward_rows:
        node = union_nodes[ward.union_id]
        parent = union_parent[ward.union_id]
        node.wards.append(
            TreeWard(
                id=ward.id,
                number=ward.number,
                name=ward.name,
                responsibility=ward.responsibility,
                office=_office_out(office) if office is not None else None,
            )
        )
        has_office = 1 if office is not None else 0
        node.counts.wards += 1
        node.counts.offices += has_office
        parent.counts.wards += 1
        parent.counts.offices += has_office
        total.wards += 1
        total.offices += has_office
    return OrgTree(
        village=TreeVillage(id=village.id, name=village.name),
        central_office=_office_out(central) if central is not None else None,
        counts=total,
        upazila_count=len(upazila_nodes),
        upazilas=list(upazila_nodes.values()),
    )

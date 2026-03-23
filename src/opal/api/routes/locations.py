"""Location API routes."""

import io

import segno
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_update
from opal.core.mri import encode_location_mri
from opal.db.models.inventory import InventoryRecord
from opal.db.models.location import Location
from opal.db.models.part import Part

router = APIRouter(prefix="/locations", tags=["locations"])


class LocationResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    parent_id: int | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class LocationCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    parent_id: int | None = None


class LocationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None


class LocationInventoryItem(BaseModel):
    inventory_id: int
    opal_number: str | None = None
    part_id: int
    part_name: str
    part_pn: str | None = None
    quantity: float
    lot_number: str | None = None


@router.get("", response_model=list[LocationResponse])
async def list_locations(
    db: DbSession,
    parent_id: int | None = None,
    active_only: bool = True,
) -> list[LocationResponse]:
    query = db.query(Location)
    if active_only:
        query = query.filter(Location.is_active == True)  # noqa: E712
    if parent_id is not None:
        query = query.filter(Location.parent_id == parent_id)
    return [LocationResponse.model_validate(loc) for loc in query.order_by(Location.code).all()]


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(location_id: int, db: DbSession) -> LocationResponse:
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    return LocationResponse.model_validate(loc)


@router.post("", response_model=LocationResponse, status_code=201)
async def create_location(
    data: LocationCreate, db: DbSession, user_id: CurrentUserId,
) -> LocationResponse:
    existing = db.query(Location).filter(Location.code == data.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Location code '{data.code}' already exists")

    loc = Location(code=data.code, name=data.name, description=data.description, parent_id=data.parent_id)
    db.add(loc)
    db.flush()
    log_create(db, loc, user_id)
    db.commit()
    db.refresh(loc)
    return LocationResponse.model_validate(loc)


@router.patch("/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: int, data: LocationUpdate, db: DbSession, user_id: CurrentUserId,
) -> LocationResponse:
    from opal.core.audit import get_model_dict

    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    old = get_model_dict(loc)
    if data.name is not None:
        loc.name = data.name
    if data.description is not None:
        loc.description = data.description
    if data.parent_id is not None:
        loc.parent_id = data.parent_id
    if data.is_active is not None:
        loc.is_active = data.is_active

    log_update(db, loc, old, user_id)
    db.commit()
    db.refresh(loc)
    return LocationResponse.model_validate(loc)


@router.get("/{location_id}/contents", response_model=list[LocationInventoryItem])
async def get_location_contents(location_id: int, db: DbSession) -> list[LocationInventoryItem]:
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    records = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(InventoryRecord.location == loc.code, Part.deleted_at.is_(None))
        .all()
    )
    return [
        LocationInventoryItem(
            inventory_id=r.id,
            opal_number=r.opal_number,
            part_id=r.part_id,
            part_name=r.part.name,
            part_pn=r.part.internal_pn,
            quantity=float(r.quantity),
            lot_number=r.lot_number,
        )
        for r in records
    ]


@router.get("/{location_id}/qrcode")
async def get_location_qrcode(location_id: int, db: DbSession) -> Response:
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    mri = encode_location_mri(loc.code)
    qr = segno.make(mri, micro=False)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=1, border=1, svgclass=None, lineclass=None)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")

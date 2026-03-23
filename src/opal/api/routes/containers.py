"""Container (WIP/kit) API routes."""

import io
from datetime import UTC, datetime
from decimal import Decimal

import segno
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import get_model_dict, log_create, log_update
from opal.core.designators import generate_container_code
from opal.core.mri import decode_mri, encode_container_mri
from opal.db.models.container import Container, ContainerItem, ContainerStatus, ContainerType
from opal.db.models.inventory import InventoryRecord

router = APIRouter(prefix="/containers", tags=["containers"])


# ── Schemas ────────────────────────────────────────────────────

class ContainerItemResponse(BaseModel):
    id: int
    inventory_record_id: int
    opal_number: str | None = None
    part_name: str | None = None
    part_pn: str | None = None
    quantity: float
    scanned_at: datetime

    model_config = {"from_attributes": True}


class ContainerResponse(BaseModel):
    id: int
    code: str
    name: str | None = None
    container_type: str
    status: str
    location_id: int | None = None
    procedure_instance_id: int | None = None
    notes: str | None = None
    items: list[ContainerItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContainerCreate(BaseModel):
    name: str | None = None
    container_type: str = "general"
    location_id: int | None = None
    procedure_instance_id: int | None = None
    notes: str | None = None


class ContainerUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    location_id: int | None = None
    notes: str | None = None


class ScanInRequest(BaseModel):
    code: str | None = None
    inventory_record_id: int | None = None
    quantity: float = 1.0


# ── Helpers ────────────────────────────────────────────────────

def _container_to_response(c: Container) -> ContainerResponse:
    items = []
    for item in c.items:
        rec = item.inventory_record
        items.append(ContainerItemResponse(
            id=item.id,
            inventory_record_id=item.inventory_record_id,
            opal_number=rec.opal_number if rec else None,
            part_name=rec.part.name if rec and rec.part else None,
            part_pn=rec.part.internal_pn if rec and rec.part else None,
            quantity=float(item.quantity),
            scanned_at=item.scanned_at,
        ))

    ct = c.container_type.value if hasattr(c.container_type, "value") else c.container_type
    st = c.status.value if hasattr(c.status, "value") else c.status

    return ContainerResponse(
        id=c.id, code=c.code, name=c.name,
        container_type=ct, status=st,
        location_id=c.location_id,
        procedure_instance_id=c.procedure_instance_id,
        notes=c.notes, items=items,
        created_at=c.created_at, updated_at=c.updated_at,
    )


# ── Endpoints ──────────────────────────────────────────────────

@router.get("", response_model=list[ContainerResponse])
async def list_containers(
    db: DbSession,
    status: str | None = None,
    container_type: str | None = None,
    procedure_instance_id: int | None = None,
) -> list[ContainerResponse]:
    query = db.query(Container)
    if status:
        query = query.filter(Container.status == status)
    if container_type:
        query = query.filter(Container.container_type == container_type)
    if procedure_instance_id:
        query = query.filter(Container.procedure_instance_id == procedure_instance_id)
    return [_container_to_response(c) for c in query.order_by(Container.id.desc()).all()]


@router.get("/{container_id}", response_model=ContainerResponse)
async def get_container(container_id: int, db: DbSession) -> ContainerResponse:
    c = db.query(Container).filter(Container.id == container_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Container not found")
    return _container_to_response(c)


@router.post("", response_model=ContainerResponse, status_code=201)
async def create_container(
    data: ContainerCreate, db: DbSession, user_id: CurrentUserId,
) -> ContainerResponse:
    try:
        ct = ContainerType(data.container_type)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid container type: {data.container_type}") from err

    code = generate_container_code(db)
    c = Container(
        code=code, name=data.name, container_type=ct,
        status=ContainerStatus.OPEN,
        location_id=data.location_id,
        procedure_instance_id=data.procedure_instance_id,
        notes=data.notes,
    )
    db.add(c)
    db.flush()
    log_create(db, c, user_id)
    db.commit()
    db.refresh(c)
    return _container_to_response(c)


@router.patch("/{container_id}", response_model=ContainerResponse)
async def update_container(
    container_id: int, data: ContainerUpdate, db: DbSession, user_id: CurrentUserId,
) -> ContainerResponse:
    c = db.query(Container).filter(Container.id == container_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Container not found")

    old = get_model_dict(c)
    if data.name is not None:
        c.name = data.name
    if data.status is not None:
        try:
            c.status = ContainerStatus(data.status)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}") from err
    if data.location_id is not None:
        c.location_id = data.location_id
    if data.notes is not None:
        c.notes = data.notes

    log_update(db, c, old, user_id)
    db.commit()
    db.refresh(c)
    return _container_to_response(c)


@router.post("/{container_id}/scan", response_model=ContainerItemResponse)
async def scan_item_into_container(
    container_id: int, data: ScanInRequest, db: DbSession, user_id: CurrentUserId,
) -> ContainerItemResponse:
    """Scan an inventory item into a container by MRI code or inventory_record_id."""
    c = db.query(Container).filter(Container.id == container_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Container not found")
    if c.status != ContainerStatus.OPEN:
        raise HTTPException(status_code=400, detail=f"Container is {c.status.value}, cannot add items")

    record: InventoryRecord | None = None

    if data.inventory_record_id:
        record = db.query(InventoryRecord).filter(
            InventoryRecord.id == data.inventory_record_id,
        ).first()
    elif data.code:
        result = decode_mri(db, data.code)
        if result and result.type == "inventory" and result.entity:
            record = result.entity
        elif result and result.type == "part":
            raise HTTPException(
                status_code=400,
                detail="Scanned a part code — scan a specific inventory item (with OPAL number) instead",
            )

    if not record:
        raise HTTPException(status_code=404, detail="Inventory record not found")

    item = ContainerItem(
        container_id=c.id,
        inventory_record_id=record.id,
        quantity=Decimal(str(data.quantity)),
        scanned_at=datetime.now(UTC),
        scanned_by_id=user_id,
    )
    db.add(item)
    db.flush()
    db.commit()
    db.refresh(item)

    return ContainerItemResponse(
        id=item.id,
        inventory_record_id=item.inventory_record_id,
        opal_number=record.opal_number,
        part_name=record.part.name if record.part else None,
        part_pn=record.part.internal_pn if record.part else None,
        quantity=float(item.quantity),
        scanned_at=item.scanned_at,
    )


@router.delete("/{container_id}/items/{item_id}", status_code=204)
async def remove_item_from_container(
    container_id: int, item_id: int, db: DbSession,
) -> None:
    item = db.query(ContainerItem).filter(
        ContainerItem.id == item_id, ContainerItem.container_id == container_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Container item not found")
    db.delete(item)
    db.commit()


@router.get("/{container_id}/qrcode")
async def get_container_qrcode(container_id: int, db: DbSession) -> Response:
    c = db.query(Container).filter(Container.id == container_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Container not found")

    mri = encode_container_mri(c.code)
    qr = segno.make(mri)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=1, border=1, svgclass=None, lineclass=None)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")

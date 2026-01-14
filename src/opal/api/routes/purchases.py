"""Purchase order management endpoints."""

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from opal.api.deps import CurrentUserId, DbSession, PaginationParams
from opal.core.audit import log_create, log_update, get_model_dict
from opal.core.inventory import generate_opal_number
from opal.db.models import InventoryRecord, Part, Purchase, PurchaseLine, Supplier
from opal.db.models.inventory import SourceType
from opal.db.models.part import TrackingType
from opal.db.models.purchase import PurchaseStatus

router = APIRouter()


class PurchaseLineCreate(BaseModel):
    """Schema for creating a purchase line."""

    part_id: int
    qty_ordered: Decimal
    unit_cost: Decimal | None = None
    destination: str | None = Field(None, max_length=255)
    notes: str | None = None


class PurchaseLineUpdate(BaseModel):
    """Schema for updating a purchase line."""

    qty_ordered: Decimal | None = None
    unit_cost: Decimal | None = None
    destination: str | None = None
    notes: str | None = None


class PurchaseCreate(BaseModel):
    """Schema for creating a purchase order."""

    supplier: str
    supplier_id: int | None = None
    supplier_reference: str | None = Field(None, max_length=100)
    reference: str | None = Field(None, max_length=64)
    target_date: date | None = None
    destination: str | None = Field(None, max_length=255)
    notes: str | None = None
    lines: list[PurchaseLineCreate] = []


class PurchaseUpdate(BaseModel):
    """Schema for updating a purchase order."""

    supplier: str | None = None
    supplier_id: int | None = None
    supplier_reference: str | None = None
    reference: str | None = None
    target_date: date | None = None
    destination: str | None = None
    notes: str | None = None
    status: PurchaseStatus | None = None


class ReceiveLine(BaseModel):
    """Schema for receiving a line item."""

    line_id: int
    qty_received: Decimal
    location: str
    lot_number: str | None = None


class ReceiveRequest(BaseModel):
    """Schema for receiving against a PO."""

    lines: list[ReceiveLine]


class PurchaseLineResponse(BaseModel):
    """Schema for purchase line response."""

    id: int
    part_id: int
    part_name: str
    part_external_pn: str | None
    qty_ordered: Decimal
    qty_received: Decimal
    qty_outstanding: Decimal
    unit_cost: Decimal | None
    destination: str | None
    notes: str | None
    is_complete: bool

    model_config = {"from_attributes": True}


class PurchaseResponse(BaseModel):
    """Schema for purchase order response."""

    id: int
    reference: str | None
    supplier: str
    supplier_id: int | None
    supplier_name: str | None
    supplier_reference: str | None
    status: PurchaseStatus
    target_date: str | None
    destination: str | None
    ordered_at: str | None
    received_at: str | None
    is_overdue: bool
    notes: str | None
    lines: list[PurchaseLineResponse]
    total_lines: int
    total_cost: Decimal | None
    created_at: str
    updated_at: str
    created_by_id: int | None
    created_by_name: str | None
    received_by_id: int | None
    received_by_name: str | None

    model_config = {"from_attributes": True}


class PurchaseListItem(BaseModel):
    """Schema for purchase in list view."""

    id: int
    reference: str | None
    supplier: str
    supplier_name: str | None
    status: PurchaseStatus
    target_date: str | None
    is_overdue: bool
    ordered_at: str | None
    total_lines: int
    total_cost: Decimal | None
    created_at: str

    model_config = {"from_attributes": True}


class PurchaseListResponse(BaseModel):
    """Schema for purchase list response."""

    items: list[PurchaseListItem]
    total: int


def line_to_response(line: PurchaseLine) -> PurchaseLineResponse:
    """Convert purchase line to response."""
    return PurchaseLineResponse(
        id=line.id,
        part_id=line.part_id,
        part_name=line.part.name,
        part_external_pn=line.part.external_pn,
        qty_ordered=line.qty_ordered,
        qty_received=line.qty_received,
        qty_outstanding=line.qty_outstanding,
        unit_cost=line.unit_cost,
        destination=line.destination,
        notes=line.notes,
        is_complete=line.is_complete,
    )


def purchase_to_response(purchase: Purchase) -> PurchaseResponse:
    """Convert purchase to full response."""
    lines = [line_to_response(l) for l in purchase.lines]
    total_cost = sum(
        (l.unit_cost or Decimal(0)) * l.qty_ordered for l in purchase.lines if l.unit_cost
    )

    return PurchaseResponse(
        id=purchase.id,
        reference=purchase.reference,
        supplier=purchase.supplier,
        supplier_id=purchase.supplier_id,
        supplier_name=purchase.supplier_rel.name if purchase.supplier_rel else None,
        supplier_reference=purchase.supplier_reference,
        status=purchase.status,
        target_date=purchase.target_date.isoformat() if purchase.target_date else None,
        destination=purchase.destination,
        ordered_at=purchase.ordered_at.isoformat() if purchase.ordered_at else None,
        received_at=purchase.received_at.isoformat() if purchase.received_at else None,
        is_overdue=purchase.is_overdue,
        notes=purchase.notes,
        lines=lines,
        total_lines=len(lines),
        total_cost=total_cost if total_cost > 0 else None,
        created_at=purchase.created_at.isoformat(),
        updated_at=purchase.updated_at.isoformat(),
        created_by_id=purchase.created_by_id,
        created_by_name=purchase.created_by.name if purchase.created_by else None,
        received_by_id=purchase.received_by_id,
        received_by_name=purchase.received_by.name if purchase.received_by else None,
    )


def purchase_to_list_item(purchase: Purchase) -> PurchaseListItem:
    """Convert purchase to list item."""
    total_cost = sum(
        (l.unit_cost or Decimal(0)) * l.qty_ordered for l in purchase.lines if l.unit_cost
    )

    return PurchaseListItem(
        id=purchase.id,
        reference=purchase.reference,
        supplier=purchase.supplier,
        supplier_name=purchase.supplier_rel.name if purchase.supplier_rel else None,
        status=purchase.status,
        target_date=purchase.target_date.isoformat() if purchase.target_date else None,
        is_overdue=purchase.is_overdue,
        ordered_at=purchase.ordered_at.isoformat() if purchase.ordered_at else None,
        total_lines=len(purchase.lines),
        total_cost=total_cost if total_cost > 0 else None,
        created_at=purchase.created_at.isoformat(),
    )


@router.get("", response_model=PurchaseListResponse)
async def list_purchases(
    db: DbSession,
    pagination: PaginationParams,
    status_filter: PurchaseStatus | None = Query(None, alias="status"),
    supplier: str | None = Query(None),
) -> PurchaseListResponse:
    """List purchase orders with optional filtering."""
    query = db.query(Purchase)

    if status_filter:
        query = query.filter(Purchase.status == status_filter)
    if supplier:
        query = query.filter(Purchase.supplier.ilike(f"%{supplier}%"))

    total = query.count()
    purchases = (
        query.order_by(Purchase.id.desc()).offset(pagination.skip).limit(pagination.limit).all()
    )

    return PurchaseListResponse(
        items=[purchase_to_list_item(p) for p in purchases],
        total=total,
    )


@router.post("", response_model=PurchaseResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase(
    db: DbSession,
    po_in: PurchaseCreate,
    user_id: CurrentUserId,
) -> PurchaseResponse:
    """Create a new purchase order."""
    # Validate supplier_id if provided
    if po_in.supplier_id:
        supplier = db.query(Supplier).filter(
            Supplier.id == po_in.supplier_id,
            Supplier.deleted_at.is_(None)
        ).first()
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Supplier {po_in.supplier_id} not found",
            )

    # Check for duplicate reference
    if po_in.reference:
        existing = db.query(Purchase).filter(Purchase.reference == po_in.reference).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"PO with reference '{po_in.reference}' already exists",
            )

    purchase = Purchase(
        supplier=po_in.supplier,
        supplier_id=po_in.supplier_id,
        supplier_reference=po_in.supplier_reference,
        reference=po_in.reference,
        target_date=po_in.target_date,
        destination=po_in.destination,
        notes=po_in.notes,
        status=PurchaseStatus.DRAFT,
        created_by_id=user_id,
    )
    db.add(purchase)
    db.flush()  # Get ID

    # Add lines
    for line_in in po_in.lines:
        # Verify part exists
        part = db.query(Part).filter(Part.id == line_in.part_id, Part.deleted_at.is_(None)).first()
        if not part:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Part {line_in.part_id} not found",
            )

        line = PurchaseLine(
            purchase_id=purchase.id,
            part_id=line_in.part_id,
            qty_ordered=line_in.qty_ordered,
            unit_cost=line_in.unit_cost,
            destination=line_in.destination,
            notes=line_in.notes,
        )
        db.add(line)

    db.flush()
    log_create(db, purchase, user_id)
    db.commit()

    return purchase_to_response(purchase)


@router.get("/{purchase_id}", response_model=PurchaseResponse)
async def get_purchase(
    db: DbSession,
    purchase_id: int,
) -> PurchaseResponse:
    """Get a specific purchase order."""
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {purchase_id} not found",
        )

    return purchase_to_response(purchase)


@router.patch("/{purchase_id}", response_model=PurchaseResponse)
async def update_purchase(
    db: DbSession,
    purchase_id: int,
    po_in: PurchaseUpdate,
    user_id: CurrentUserId,
) -> PurchaseResponse:
    """Update a purchase order."""
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {purchase_id} not found",
        )

    old_values = get_model_dict(purchase)

    update_data = po_in.model_dump(exclude_unset=True)

    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == PurchaseStatus.ORDERED and purchase.status == PurchaseStatus.DRAFT:
            update_data["ordered_at"] = datetime.now(timezone.utc)
        elif new_status == PurchaseStatus.CANCELLED:
            pass  # Allow cancellation from any state

    for field, value in update_data.items():
        setattr(purchase, field, value)

    db.commit()
    db.refresh(purchase)

    log_update(db, purchase, old_values, user_id)
    db.commit()

    return purchase_to_response(purchase)


@router.post("/{purchase_id}/lines", response_model=PurchaseLineResponse, status_code=status.HTTP_201_CREATED)
async def add_purchase_line(
    db: DbSession,
    purchase_id: int,
    line_in: PurchaseLineCreate,
    user_id: CurrentUserId,
) -> PurchaseLineResponse:
    """Add a line to a purchase order."""
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {purchase_id} not found",
        )

    if purchase.status not in (PurchaseStatus.DRAFT, PurchaseStatus.ORDERED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add lines to purchase in {purchase.status} status",
        )

    # Verify part exists
    part = db.query(Part).filter(Part.id == line_in.part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {line_in.part_id} not found",
        )

    line = PurchaseLine(
        purchase_id=purchase_id,
        part_id=line_in.part_id,
        qty_ordered=line_in.qty_ordered,
        unit_cost=line_in.unit_cost,
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    return line_to_response(line)


@router.patch("/{purchase_id}/lines/{line_id}", response_model=PurchaseLineResponse)
async def update_purchase_line(
    db: DbSession,
    purchase_id: int,
    line_id: int,
    line_in: PurchaseLineUpdate,
    user_id: CurrentUserId,
) -> PurchaseLineResponse:
    """Update a purchase line."""
    line = (
        db.query(PurchaseLine)
        .filter(PurchaseLine.id == line_id, PurchaseLine.purchase_id == purchase_id)
        .first()
    )
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase line {line_id} not found",
        )

    update_data = line_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(line, field, value)

    db.commit()
    db.refresh(line)

    return line_to_response(line)


@router.delete("/{purchase_id}/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase_line(
    db: DbSession,
    purchase_id: int,
    line_id: int,
    user_id: CurrentUserId,
) -> None:
    """Delete a purchase line."""
    line = (
        db.query(PurchaseLine)
        .filter(PurchaseLine.id == line_id, PurchaseLine.purchase_id == purchase_id)
        .first()
    )
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase line {line_id} not found",
        )

    if line.qty_received > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete line that has been partially received",
        )

    db.delete(line)
    db.commit()


@router.post("/{purchase_id}/receive", response_model=PurchaseResponse)
async def receive_purchase(
    db: DbSession,
    purchase_id: int,
    receive_in: ReceiveRequest,
    user_id: CurrentUserId,
) -> PurchaseResponse:
    """Receive items against a purchase order."""
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase order {purchase_id} not found",
        )

    if purchase.status not in (PurchaseStatus.ORDERED, PurchaseStatus.PARTIAL):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot receive against purchase in {purchase.status} status",
        )

    old_values = get_model_dict(purchase)

    for recv in receive_in.lines:
        line = (
            db.query(PurchaseLine)
            .filter(PurchaseLine.id == recv.line_id, PurchaseLine.purchase_id == purchase_id)
            .first()
        )
        if not line:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Purchase line {recv.line_id} not found",
            )

        if recv.qty_received <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Received quantity must be positive",
            )

        # Update line received quantity
        line.qty_received += recv.qty_received

        # Get the part to check tracking type
        part = db.query(Part).filter(Part.id == line.part_id).first()

        if part and part.tracking_type == TrackingType.SERIALIZED:
            # Serialized parts: create individual inventory records with unique OPAL numbers
            # Each physical unit gets its own OPAL for full traceability
            qty_to_create = int(recv.qty_received)
            for _ in range(qty_to_create):
                opal_number = generate_opal_number(db)
                inv_record = InventoryRecord(
                    part_id=line.part_id,
                    quantity=1,  # Individual unit
                    location=recv.location,
                    lot_number=recv.lot_number,
                    opal_number=opal_number,
                    source_type=SourceType.PURCHASE,
                    source_purchase_line_id=line.id,
                )
                db.add(inv_record)
                db.flush()  # Ensure OPAL is committed before generating next
        else:
            # Bulk parts: one OPAL number for the entire received quantity
            opal_number = generate_opal_number(db)
            inv_record = InventoryRecord(
                part_id=line.part_id,
                quantity=recv.qty_received,
                location=recv.location,
                lot_number=recv.lot_number,
                opal_number=opal_number,
                source_type=SourceType.PURCHASE,
                source_purchase_line_id=line.id,
            )
            db.add(inv_record)
            db.flush()

    # Update purchase status
    all_complete = all(line.is_complete for line in purchase.lines)
    any_received = any(line.qty_received > 0 for line in purchase.lines)

    if all_complete:
        purchase.status = PurchaseStatus.RECEIVED
        purchase.received_at = datetime.now(timezone.utc)
    elif any_received:
        purchase.status = PurchaseStatus.PARTIAL

    db.commit()
    db.refresh(purchase)

    log_update(db, purchase, old_values, user_id)
    db.commit()

    return purchase_to_response(purchase)

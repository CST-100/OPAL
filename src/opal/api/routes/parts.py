"""Parts management endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_

from opal.api.deps import CurrentUserId, DbSession, PaginationParams
from opal.core.audit import log_create, log_delete, log_update, get_model_dict
from opal.db.models import InventoryRecord, Part

router = APIRouter()


class PartCreate(BaseModel):
    """Schema for creating a part."""

    name: str
    internal_pn: str | None = None  # Auto-generated if not provided
    external_pn: str | None = None
    description: str | None = None
    category: str | None = None
    unit_of_measure: str = "ea"
    tracking_type: str = "bulk"  # "bulk" = one OPAL per batch, "serialized" = one OPAL per unit
    tier: int = 1  # 1=Flight, 2=Ground, 3=Loose by default
    parent_id: int | None = None  # Parent assembly if this is a child part
    metadata: dict[str, Any] | None = None


class PartUpdate(BaseModel):
    """Schema for updating a part."""

    name: str | None = None
    internal_pn: str | None = None
    external_pn: str | None = None
    description: str | None = None
    category: str | None = None
    unit_of_measure: str | None = None
    tracking_type: str | None = None  # "bulk" or "serialized"
    tier: int | None = None
    parent_id: int | None = None
    metadata: dict[str, Any] | None = None


class PartResponse(BaseModel):
    """Schema for part response."""

    id: int
    internal_pn: str | None  # Auto-generated part number (e.g., PO/1-001)
    external_pn: str | None  # Manufacturer/supplier part number
    name: str
    description: str | None
    category: str | None
    unit_of_measure: str
    tracking_type: str  # "bulk" or "serialized"
    tier: int
    tier_name: str | None = None  # Populated from project config if available
    parent_id: int | None
    metadata: dict[str, Any] | None
    total_quantity: Decimal
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class PartListResponse(BaseModel):
    """Schema for part list response."""

    items: list[PartResponse]
    total: int


def get_part_with_quantity(db: DbSession, part: Part) -> PartResponse:
    """Convert part to response with total quantity calculated."""
    from opal.config import get_active_project

    total_qty = (
        db.query(func.coalesce(func.sum(InventoryRecord.quantity), 0))
        .filter(InventoryRecord.part_id == part.id)
        .scalar()
    )

    # Try to get tier name from project config
    tier_name = None
    project = get_active_project()
    if project:
        tier = project.get_tier(part.tier)
        if tier:
            tier_name = tier.name

    return PartResponse(
        id=part.id,
        internal_pn=part.internal_pn,
        external_pn=part.external_pn,
        name=part.name,
        description=part.description,
        category=part.category,
        unit_of_measure=part.unit_of_measure,
        tracking_type=part.tracking_type,
        tier=part.tier,
        tier_name=tier_name,
        parent_id=part.parent_id,
        metadata=part.metadata_,
        total_quantity=total_qty or Decimal(0),
        created_at=part.created_at.isoformat(),
        updated_at=part.updated_at.isoformat(),
    )


@router.get("", response_model=PartListResponse)
async def list_parts(
    db: DbSession,
    pagination: PaginationParams,
    search: str | None = Query(None, description="Search in name, external_pn, description"),
    category: str | None = Query(None, description="Filter by category"),
    tier: int | None = Query(None, description="Filter by tier level (1=Flight, 2=Ground, 3=Loose)"),
    parent_id: int | None = Query(None, description="Filter by parent assembly ID"),
    top_level: bool = Query(False, description="Only show parts with no parent (top-level assemblies)"),
) -> PartListResponse:
    """List all parts with optional filtering."""
    query = db.query(Part).filter(Part.deleted_at.is_(None))

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Part.name.ilike(search_term),
                Part.internal_pn.ilike(search_term),
                Part.external_pn.ilike(search_term),
                Part.description.ilike(search_term),
            )
        )

    # Apply category filter
    if category:
        query = query.filter(Part.category == category)

    # Apply tier filter
    if tier is not None:
        query = query.filter(Part.tier == tier)

    # Apply parent filter
    if parent_id is not None:
        query = query.filter(Part.parent_id == parent_id)
    elif top_level:
        query = query.filter(Part.parent_id.is_(None))

    total = query.count()
    parts = query.order_by(Part.id.desc()).offset(pagination.skip).limit(pagination.limit).all()

    return PartListResponse(
        items=[get_part_with_quantity(db, p) for p in parts],
        total=total,
    )


def generate_internal_pn(db: DbSession, tier: int) -> str:
    """Generate next internal part number for a given tier."""
    from opal.config import get_active_project

    project = get_active_project()
    if not project:
        # Fallback: simple sequential numbering
        count = db.query(Part).filter(Part.tier == tier, Part.deleted_at.is_(None)).count()
        return f"PN-{tier}-{str(count + 1).zfill(4)}"

    # Count existing parts in this tier to get next sequence
    count = db.query(Part).filter(Part.tier == tier, Part.deleted_at.is_(None)).count()
    return project.generate_part_number(tier, count + 1)


@router.post("", response_model=PartResponse, status_code=status.HTTP_201_CREATED)
async def create_part(
    db: DbSession,
    part_in: PartCreate,
    user_id: CurrentUserId,
) -> PartResponse:
    """Create a new part."""
    # Validate parent exists if specified
    if part_in.parent_id is not None:
        parent = db.query(Part).filter(Part.id == part_in.parent_id, Part.deleted_at.is_(None)).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Parent part {part_in.parent_id} not found",
            )

    # Generate internal_pn if not provided
    internal_pn = part_in.internal_pn
    if not internal_pn:
        internal_pn = generate_internal_pn(db, part_in.tier)

    part = Part(
        name=part_in.name,
        internal_pn=internal_pn,
        external_pn=part_in.external_pn,
        description=part_in.description,
        category=part_in.category,
        unit_of_measure=part_in.unit_of_measure,
        tracking_type=part_in.tracking_type,
        tier=part_in.tier,
        parent_id=part_in.parent_id,
        metadata_=part_in.metadata,
    )
    db.add(part)
    db.commit()
    db.refresh(part)

    log_create(db, part, user_id)
    db.commit()

    return get_part_with_quantity(db, part)


@router.get("/categories")
async def list_categories(db: DbSession) -> list[str]:
    """List all unique part categories."""
    categories = (
        db.query(Part.category)
        .filter(Part.deleted_at.is_(None), Part.category.isnot(None))
        .distinct()
        .all()
    )
    return sorted([c[0] for c in categories if c[0]])


@router.get("/{part_id}", response_model=PartResponse)
async def get_part(
    db: DbSession,
    part_id: int,
) -> PartResponse:
    """Get a specific part."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id} not found",
        )

    return get_part_with_quantity(db, part)


@router.patch("/{part_id}", response_model=PartResponse)
async def update_part(
    db: DbSession,
    part_id: int,
    part_in: PartUpdate,
    user_id: CurrentUserId,
) -> PartResponse:
    """Update a part."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id} not found",
        )

    # Validate parent_id if being updated
    if part_in.parent_id is not None:
        # Cannot be own parent
        if part_in.parent_id == part_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A part cannot be its own parent",
            )
        # Parent must exist
        parent = db.query(Part).filter(Part.id == part_in.parent_id, Part.deleted_at.is_(None)).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Parent part {part_in.parent_id} not found",
            )

    old_values = get_model_dict(part)

    update_data = part_in.model_dump(exclude_unset=True)
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for field, value in update_data.items():
        setattr(part, field, value)

    db.commit()
    db.refresh(part)

    log_update(db, part, old_values, user_id)
    db.commit()

    return get_part_with_quantity(db, part)


@router.delete("/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(
    db: DbSession,
    part_id: int,
    user_id: CurrentUserId,
) -> None:
    """Soft delete a part."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id} not found",
        )

    log_delete(db, part, user_id)
    part.soft_delete()
    db.commit()

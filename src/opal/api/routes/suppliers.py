"""Supplier API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_update, get_model_dict
from opal.db.models import Supplier

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


# --- Schemas ---


class SupplierCreate(BaseModel):
    """Schema for creating a supplier."""

    name: str = Field(..., min_length=1, max_length=255)
    code: str | None = Field(None, max_length=50)
    description: str | None = None
    website: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    address: str | None = None
    notes: str | None = None
    is_active: bool = True


class SupplierUpdate(BaseModel):
    """Schema for updating a supplier."""

    name: str | None = Field(None, min_length=1, max_length=255)
    code: str | None = Field(None, max_length=50)
    description: str | None = None
    website: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    address: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class SupplierResponse(BaseModel):
    """Schema for supplier responses."""

    id: int
    name: str
    code: str | None
    description: str | None
    website: str | None
    email: str | None
    phone: str | None
    address: str | None
    notes: str | None
    is_active: bool
    purchase_count: int = 0

    model_config = {"from_attributes": True}


class SupplierListResponse(BaseModel):
    """Schema for paginated supplier list."""

    items: list[SupplierResponse]
    total: int
    page: int
    per_page: int


# --- Routes ---


@router.get("", response_model=SupplierListResponse)
async def list_suppliers(
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: str | None = None,
    is_active: bool | None = None,
):
    """List all suppliers with pagination and filtering."""
    query = select(Supplier).where(Supplier.deleted_at.is_(None))

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (Supplier.name.ilike(search_filter))
            | (Supplier.code.ilike(search_filter))
            | (Supplier.email.ilike(search_filter))
        )

    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    # Get paginated results
    offset = (page - 1) * per_page
    query = query.order_by(Supplier.name).offset(offset).limit(per_page)
    suppliers = db.execute(query).scalars().all()

    # Build response with purchase counts
    items = []
    for s in suppliers:
        items.append(
            SupplierResponse(
                id=s.id,
                name=s.name,
                code=s.code,
                description=s.description,
                website=s.website,
                email=s.email,
                phone=s.phone,
                address=s.address,
                notes=s.notes,
                is_active=s.is_active,
                purchase_count=len(s.purchases) if s.purchases else 0,
            )
        )

    return SupplierListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    db: DbSession,
    data: SupplierCreate,
    user_id: CurrentUserId,
):
    """Create a new supplier."""
    # Check for duplicate code
    if data.code:
        existing = db.execute(
            select(Supplier).where(
                Supplier.code == data.code, Supplier.deleted_at.is_(None)
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Supplier with code '{data.code}' already exists",
            )

    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    db.flush()

    log_create(db, supplier, user_id)
    db.commit()
    db.refresh(supplier)

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        code=supplier.code,
        description=supplier.description,
        website=supplier.website,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        notes=supplier.notes,
        is_active=supplier.is_active,
        purchase_count=0,
    )


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    db: DbSession,
    supplier_id: int,
):
    """Get a supplier by ID."""
    supplier = db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
        )
    ).scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found",
        )

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        code=supplier.code,
        description=supplier.description,
        website=supplier.website,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        notes=supplier.notes,
        is_active=supplier.is_active,
        purchase_count=len(supplier.purchases) if supplier.purchases else 0,
    )


@router.patch("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    db: DbSession,
    supplier_id: int,
    data: SupplierUpdate,
    user_id: CurrentUserId,
):
    """Update a supplier."""
    supplier = db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
        )
    ).scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found",
        )

    # Check for duplicate code if changing
    if data.code and data.code != supplier.code:
        existing = db.execute(
            select(Supplier).where(
                Supplier.code == data.code,
                Supplier.id != supplier_id,
                Supplier.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Supplier with code '{data.code}' already exists",
            )

    old_data = get_model_dict(supplier)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(supplier, key, value)

    db.flush()
    log_update(db, supplier, old_data, user_id)
    db.commit()
    db.refresh(supplier)

    return SupplierResponse(
        id=supplier.id,
        name=supplier.name,
        code=supplier.code,
        description=supplier.description,
        website=supplier.website,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        notes=supplier.notes,
        is_active=supplier.is_active,
        purchase_count=len(supplier.purchases) if supplier.purchases else 0,
    )


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    db: DbSession,
    supplier_id: int,
    user_id: CurrentUserId,
):
    """Soft-delete a supplier."""
    supplier = db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
        )
    ).scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found",
        )

    # Check if supplier has any purchases
    if supplier.purchases:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete supplier with existing purchase orders. Deactivate instead.",
        )

    old_data = get_model_dict(supplier)
    supplier.deleted_at = datetime.now(timezone.utc)
    db.flush()
    log_update(db, supplier, old_data, user_id)
    db.commit()

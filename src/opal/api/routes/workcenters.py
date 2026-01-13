"""Workcenter API routes."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_update, get_model_dict
from opal.db.models import Workcenter

router = APIRouter(prefix="/workcenters", tags=["workcenters"])


class WorkcenterCreate(BaseModel):
    """Schema for creating a workcenter."""

    name: str
    code: str
    description: str | None = None
    location: str | None = None
    is_active: bool = True


class WorkcenterUpdate(BaseModel):
    """Schema for updating a workcenter."""

    name: str | None = None
    code: str | None = None
    description: str | None = None
    location: str | None = None
    is_active: bool | None = None


class WorkcenterResponse(BaseModel):
    """Schema for workcenter response."""

    id: int
    name: str
    code: str
    description: str | None
    location: str | None
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("")
def list_workcenters(
    db: DbSession,
    active_only: bool = Query(True, description="Only show active workcenters"),
    search: str | None = Query(None, description="Search by name or code"),
) -> list[WorkcenterResponse]:
    """List all workcenters."""
    query = db.query(Workcenter)

    if active_only:
        query = query.filter(Workcenter.is_active == True)  # noqa: E712

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Workcenter.name.ilike(search_term)) | (Workcenter.code.ilike(search_term))
        )

    query = query.order_by(Workcenter.name)
    return query.all()


@router.post("", status_code=201)
def create_workcenter(
    data: WorkcenterCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> WorkcenterResponse:
    """Create a new workcenter."""
    # Check for duplicate code
    existing = db.query(Workcenter).filter(
        func.lower(Workcenter.code) == data.code.lower()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Workcenter code '{data.code}' already exists")

    workcenter = Workcenter(
        name=data.name,
        code=data.code.upper(),
        description=data.description,
        location=data.location,
        is_active=data.is_active,
    )
    db.add(workcenter)
    db.commit()
    db.refresh(workcenter)

    log_create(db, workcenter, user_id)
    db.commit()

    return workcenter


@router.get("/{workcenter_id}")
def get_workcenter(
    workcenter_id: int,
    db: DbSession,
) -> WorkcenterResponse:
    """Get a workcenter by ID."""
    workcenter = db.query(Workcenter).filter(Workcenter.id == workcenter_id).first()
    if not workcenter:
        raise HTTPException(status_code=404, detail="Workcenter not found")
    return workcenter


@router.patch("/{workcenter_id}")
def update_workcenter(
    workcenter_id: int,
    data: WorkcenterUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> WorkcenterResponse:
    """Update a workcenter."""
    workcenter = db.query(Workcenter).filter(Workcenter.id == workcenter_id).first()
    if not workcenter:
        raise HTTPException(status_code=404, detail="Workcenter not found")

    old_values = get_model_dict(workcenter)

    update_data = data.model_dump(exclude_unset=True)

    # Check for duplicate code if changing
    if "code" in update_data and update_data["code"].upper() != workcenter.code:
        existing = db.query(Workcenter).filter(
            func.lower(Workcenter.code) == update_data["code"].lower(),
            Workcenter.id != workcenter_id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Workcenter code '{update_data['code']}' already exists",
            )
        update_data["code"] = update_data["code"].upper()

    for field, value in update_data.items():
        setattr(workcenter, field, value)

    db.commit()
    db.refresh(workcenter)

    log_update(db, workcenter, old_values, user_id)
    db.commit()

    return workcenter


@router.delete("/{workcenter_id}", status_code=204)
def delete_workcenter(
    workcenter_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Deactivate a workcenter (soft delete)."""
    workcenter = db.query(Workcenter).filter(Workcenter.id == workcenter_id).first()
    if not workcenter:
        raise HTTPException(status_code=404, detail="Workcenter not found")

    old_values = get_model_dict(workcenter)

    # Soft delete by deactivating
    workcenter.is_active = False
    db.commit()
    db.refresh(workcenter)

    log_update(db, workcenter, old_values, user_id)
    db.commit()

"""Part requirements management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from opal.api.deps import CurrentUserId, DbSession
from opal.config import get_active_project
from opal.core.audit import get_model_dict, log_create, log_update
from opal.db.models import Part, PartRequirement

router = APIRouter()


class RequirementAssign(BaseModel):
    """Schema for assigning a requirement to a part."""

    requirement_id: str
    notes: str | None = None


class RequirementUpdate(BaseModel):
    """Schema for updating a part requirement."""

    status: str | None = None  # open, verified, waived, not_applicable
    notes: str | None = None


class RequirementVerify(BaseModel):
    """Schema for verifying a requirement."""

    notes: str | None = None


class PartRequirementResponse(BaseModel):
    """Schema for part requirement response."""

    id: int
    part_id: int
    requirement_id: str
    requirement_title: str | None = None
    requirement_description: str | None = None
    requirement_category: str | None = None
    status: str
    notes: str | None
    verified_at: str | None
    verified_by_id: int | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ProjectRequirementResponse(BaseModel):
    """Schema for project requirement from config."""

    id: str
    title: str
    description: str
    category: str


def get_requirement_response(pr: PartRequirement) -> PartRequirementResponse:
    """Convert PartRequirement to response with project config info."""
    project = get_active_project()

    req_title = None
    req_desc = None
    req_cat = None

    if project:
        req_config = project.get_requirement(pr.requirement_id)
        if req_config:
            req_title = req_config.title
            req_desc = req_config.description
            req_cat = req_config.category

    return PartRequirementResponse(
        id=pr.id,
        part_id=pr.part_id,
        requirement_id=pr.requirement_id,
        requirement_title=req_title,
        requirement_description=req_desc,
        requirement_category=req_cat,
        status=pr.status,
        notes=pr.notes,
        verified_at=pr.verified_at.isoformat() if pr.verified_at else None,
        verified_by_id=pr.verified_by_id,
        created_at=pr.created_at.isoformat(),
        updated_at=pr.updated_at.isoformat(),
    )


@router.get("/project", response_model=list[ProjectRequirementResponse])
async def list_project_requirements() -> list[ProjectRequirementResponse]:
    """List all requirements defined in the project config."""
    project = get_active_project()
    if not project:
        return []

    return [
        ProjectRequirementResponse(
            id=req.id,
            title=req.title,
            description=req.description,
            category=req.category,
        )
        for req in project.requirements
    ]


@router.get("/parts/{part_id}", response_model=list[PartRequirementResponse])
async def list_part_requirements(
    db: DbSession,
    part_id: int,
) -> list[PartRequirementResponse]:
    """List all requirements assigned to a part."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id} not found",
        )

    reqs = db.query(PartRequirement).filter(PartRequirement.part_id == part_id).all()
    return [get_requirement_response(pr) for pr in reqs]


@router.post("/parts/{part_id}", response_model=PartRequirementResponse, status_code=status.HTTP_201_CREATED)
async def assign_requirement(
    db: DbSession,
    part_id: int,
    req_in: RequirementAssign,
    user_id: CurrentUserId,
) -> PartRequirementResponse:
    """Assign a requirement to a part."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id} not found",
        )

    # Check if requirement exists in project config
    project = get_active_project()
    if project:
        req_config = project.get_requirement(req_in.requirement_id)
        if not req_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Requirement {req_in.requirement_id} not found in project config",
            )

    # Check if already assigned
    existing = (
        db.query(PartRequirement)
        .filter(
            PartRequirement.part_id == part_id,
            PartRequirement.requirement_id == req_in.requirement_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requirement {req_in.requirement_id} already assigned to part {part_id}",
        )

    pr = PartRequirement(
        part_id=part_id,
        requirement_id=req_in.requirement_id,
        notes=req_in.notes,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)

    log_create(db, pr, user_id)
    db.commit()

    return get_requirement_response(pr)


@router.patch("/{requirement_id}", response_model=PartRequirementResponse)
async def update_part_requirement(
    db: DbSession,
    requirement_id: int,
    req_in: RequirementUpdate,
    user_id: CurrentUserId,
) -> PartRequirementResponse:
    """Update a part requirement."""
    pr = db.query(PartRequirement).filter(PartRequirement.id == requirement_id).first()
    if not pr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part requirement {requirement_id} not found",
        )

    old_values = get_model_dict(pr)

    if req_in.status is not None:
        if req_in.status not in ("open", "verified", "waived", "not_applicable"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status must be one of: open, verified, waived, not_applicable",
            )
        pr.status = req_in.status

    if req_in.notes is not None:
        pr.notes = req_in.notes

    db.commit()
    db.refresh(pr)

    log_update(db, pr, old_values, user_id)
    db.commit()

    return get_requirement_response(pr)


@router.post("/{requirement_id}/verify", response_model=PartRequirementResponse)
async def verify_requirement(
    db: DbSession,
    requirement_id: int,
    verify_in: RequirementVerify,
    user_id: CurrentUserId,
) -> PartRequirementResponse:
    """Mark a requirement as verified."""
    pr = db.query(PartRequirement).filter(PartRequirement.id == requirement_id).first()
    if not pr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part requirement {requirement_id} not found",
        )

    old_values = get_model_dict(pr)

    pr.status = "verified"
    pr.verified_at = datetime.now(timezone.utc)
    pr.verified_by_id = user_id
    if verify_in.notes:
        pr.notes = verify_in.notes

    db.commit()
    db.refresh(pr)

    log_update(db, pr, old_values, user_id)
    db.commit()

    return get_requirement_response(pr)


@router.delete("/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_requirement(
    db: DbSession,
    requirement_id: int,
    user_id: CurrentUserId,
) -> None:
    """Remove a requirement assignment from a part."""
    pr = db.query(PartRequirement).filter(PartRequirement.id == requirement_id).first()
    if not pr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part requirement {requirement_id} not found",
        )

    db.delete(pr)
    db.commit()

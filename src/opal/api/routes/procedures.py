"""Procedures API routes."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_delete, log_update, get_model_dict, AuditContext
from opal.db.models import Kit, Part, ProcedureOutput
from opal.db.models.procedure import (
    MasterProcedure,
    ProcedureStatus,
    ProcedureStep,
    ProcedureVersion,
    StepKit,
    UsageType,
)

router = APIRouter(prefix="/procedures", tags=["procedures"])


# ============ Schemas ============


class StepSchema(BaseModel):
    """Procedure step response."""

    id: int
    order: int
    step_number: str
    level: int
    parent_step_id: int | None = None
    title: str
    instructions: str | None = None
    required_data_schema: dict[str, Any] | None = None
    is_contingency: bool = False
    estimated_duration_minutes: int | None = None
    workcenter_id: int | None = None
    sub_steps: list["StepSchema"] = []

    model_config = {"from_attributes": True}


class ProcedureResponse(BaseModel):
    """Procedure response."""

    id: int
    name: str
    description: str | None = None
    status: str
    current_version_id: int | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[StepSchema] = []

    model_config = {"from_attributes": True}


class ProcedureListResponse(BaseModel):
    """Paginated procedure list."""

    items: list[ProcedureResponse]
    total: int
    page: int
    page_size: int


class ProcedureCreate(BaseModel):
    """Create procedure request."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class ProcedureUpdate(BaseModel):
    """Update procedure request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = None


class StepCreate(BaseModel):
    """Create step request."""

    title: str = Field(..., min_length=1, max_length=255)
    instructions: str | None = None
    required_data_schema: dict[str, Any] | None = None
    is_contingency: bool = False
    estimated_duration_minutes: int | None = Field(None, ge=1)
    parent_step_id: int | None = Field(None, description="Parent op ID for sub-steps")


class StepUpdate(BaseModel):
    """Update step request."""

    title: str | None = Field(None, min_length=1, max_length=255)
    instructions: str | None = None
    required_data_schema: dict[str, Any] | None = None
    is_contingency: bool | None = None
    estimated_duration_minutes: int | None = Field(None, ge=1)


class StepReorder(BaseModel):
    """Reorder steps request."""

    step_ids: list[int] = Field(..., description="Step IDs in new order")


class VersionResponse(BaseModel):
    """Procedure version response."""

    id: int
    version_number: int
    created_at: datetime
    created_by_id: int | None = None

    model_config = {"from_attributes": True}


class VersionDetailResponse(BaseModel):
    """Procedure version with content."""

    id: int
    version_number: int
    content: dict[str, Any]
    created_at: datetime
    created_by_id: int | None = None

    model_config = {"from_attributes": True}


class KitItemResponse(BaseModel):
    """Kit item response."""

    id: int
    part_id: int
    part_name: str
    part_external_pn: str | None = None
    quantity_required: float


class KitItemCreate(BaseModel):
    """Add part to kit request."""

    part_id: int
    quantity_required: float = Field(..., gt=0)


class KitItemUpdate(BaseModel):
    """Update kit item request."""

    quantity_required: float = Field(..., gt=0)


# ============ Helpers ============


def _build_step_hierarchy(steps: list[ProcedureStep]) -> list[StepSchema]:
    """Build a hierarchical step structure from flat list."""
    # Group steps by parent
    step_map = {s.id: s for s in steps}
    children_map: dict[int | None, list[ProcedureStep]] = {None: []}

    for step in steps:
        parent_id = step.parent_step_id
        if parent_id not in children_map:
            children_map[parent_id] = []
        children_map[parent_id].append(step)

    def build_schema(step: ProcedureStep) -> StepSchema:
        sub_steps = children_map.get(step.id, [])
        return StepSchema(
            id=step.id,
            order=step.order,
            step_number=step.step_number,
            level=step.level,
            parent_step_id=step.parent_step_id,
            title=step.title,
            instructions=step.instructions,
            required_data_schema=step.required_data_schema,
            is_contingency=step.is_contingency,
            estimated_duration_minutes=step.estimated_duration_minutes,
            workcenter_id=step.workcenter_id,
            sub_steps=[build_schema(s) for s in sorted(sub_steps, key=lambda x: x.order)],
        )

    # Build tree starting from top-level steps
    top_level = children_map.get(None, [])
    # Sort: normal ops first (by step_number), then contingency ops
    normal_ops = sorted([s for s in top_level if not s.is_contingency], key=lambda x: int(x.step_number) if x.step_number.isdigit() else 0)
    contingency_ops = sorted([s for s in top_level if s.is_contingency], key=lambda x: x.step_number)

    return [build_schema(s) for s in normal_ops + contingency_ops]


# ============ Procedure CRUD ============


@router.get("", response_model=ProcedureListResponse)
async def list_procedures(
    db: DbSession,
    search: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> ProcedureListResponse:
    """List procedures with optional search and filter."""
    query = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(MasterProcedure.name.ilike(search_term))

    if status:
        query = query.filter(MasterProcedure.status == status)

    total = query.count()

    procedures = (
        query.order_by(MasterProcedure.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ProcedureListResponse(
        items=[ProcedureResponse.model_validate(p) for p in procedures],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ProcedureResponse, status_code=201)
async def create_procedure(
    data: ProcedureCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> ProcedureResponse:
    """Create a new procedure."""
    procedure = MasterProcedure(
        name=data.name,
        description=data.description,
        status=ProcedureStatus.DRAFT,
    )
    db.add(procedure)
    db.flush()

    log_create(db, procedure, user_id)
    db.commit()
    db.refresh(procedure)

    return ProcedureResponse.model_validate(procedure)


@router.get("/{procedure_id}", response_model=ProcedureResponse)
async def get_procedure(
    procedure_id: int,
    db: DbSession,
) -> ProcedureResponse:
    """Get procedure by ID with hierarchical steps."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    # Build hierarchical step structure
    steps = _build_step_hierarchy(procedure.steps)

    return ProcedureResponse(
        id=procedure.id,
        name=procedure.name,
        description=procedure.description,
        status=procedure.status.value if hasattr(procedure.status, "value") else str(procedure.status),
        current_version_id=procedure.current_version_id,
        created_at=procedure.created_at,
        updated_at=procedure.updated_at,
        steps=steps,
    )


@router.patch("/{procedure_id}", response_model=ProcedureResponse)
async def update_procedure(
    procedure_id: int,
    data: ProcedureUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> ProcedureResponse:
    """Update procedure metadata."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    old_values = get_model_dict(procedure)

    if data.name is not None:
        procedure.name = data.name
    if data.description is not None:
        procedure.description = data.description
    if data.status is not None:
        try:
            procedure.status = ProcedureStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")

    log_update(db, procedure, old_values, user_id)
    db.commit()
    db.refresh(procedure)

    return ProcedureResponse.model_validate(procedure)


@router.delete("/{procedure_id}", status_code=204)
async def delete_procedure(
    procedure_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Soft delete a procedure."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    procedure.deleted_at = datetime.now(timezone.utc)
    log_delete(db, procedure, user_id)
    db.commit()


# ============ Steps ============


def _calculate_step_number(db: DbSession, procedure_id: int, parent_step_id: int | None, is_contingency: bool) -> str:
    """Calculate the next step number based on hierarchy and contingency status."""
    if parent_step_id:
        # Sub-step: get parent's step_number and add sub-number
        parent = db.query(ProcedureStep).filter(ProcedureStep.id == parent_step_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent step not found")

        # Count existing sub-steps under this parent
        sub_count = (
            db.query(func.count(ProcedureStep.id))
            .filter(ProcedureStep.parent_step_id == parent_step_id)
            .scalar()
        )
        return f"{parent.step_number}.{sub_count + 1}"
    else:
        # Top-level op
        if is_contingency:
            # Count existing contingency ops (C1, C2, C3...)
            contingency_count = (
                db.query(func.count(ProcedureStep.id))
                .filter(
                    ProcedureStep.procedure_id == procedure_id,
                    ProcedureStep.parent_step_id.is_(None),
                    ProcedureStep.is_contingency == True,
                )
                .scalar()
            )
            return f"C{contingency_count + 1}"
        else:
            # Count existing normal ops (1, 2, 3...)
            normal_count = (
                db.query(func.count(ProcedureStep.id))
                .filter(
                    ProcedureStep.procedure_id == procedure_id,
                    ProcedureStep.parent_step_id.is_(None),
                    ProcedureStep.is_contingency == False,
                )
                .scalar()
            )
            return str(normal_count + 1)


@router.post("/{procedure_id}/steps", response_model=StepSchema, status_code=201)
async def add_step(
    procedure_id: int,
    data: StepCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepSchema:
    """Add a step to a procedure.

    - Without parent_step_id: creates a top-level OP
    - With parent_step_id: creates a sub-step under that OP
    - Contingency ops are numbered C1, C2, C3 (separate from normal ops)
    """
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    # Validate parent_step_id if provided
    if data.parent_step_id:
        parent = (
            db.query(ProcedureStep)
            .filter(
                ProcedureStep.id == data.parent_step_id,
                ProcedureStep.procedure_id == procedure_id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Parent step not found")
        # Sub-steps inherit contingency status from parent
        is_contingency = parent.is_contingency
        level = 1
    else:
        is_contingency = data.is_contingency
        level = 0

    # Calculate step number
    step_number = _calculate_step_number(db, procedure_id, data.parent_step_id, is_contingency)

    # Get next order number (global across all steps in procedure)
    max_order = (
        db.query(func.max(ProcedureStep.order))
        .filter(ProcedureStep.procedure_id == procedure_id)
        .scalar()
    )
    next_order = (max_order or 0) + 1

    step = ProcedureStep(
        procedure_id=procedure_id,
        parent_step_id=data.parent_step_id,
        order=next_order,
        step_number=step_number,
        level=level,
        title=data.title,
        instructions=data.instructions,
        required_data_schema=data.required_data_schema,
        is_contingency=is_contingency,
        estimated_duration_minutes=data.estimated_duration_minutes,
    )
    db.add(step)
    db.flush()

    log_create(db, step, user_id)
    db.commit()
    db.refresh(step)

    return StepSchema.model_validate(step)


@router.patch("/{procedure_id}/steps/{step_id}", response_model=StepSchema)
async def update_step(
    procedure_id: int,
    step_id: int,
    data: StepUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepSchema:
    """Update a step."""
    step = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.id == step_id, ProcedureStep.procedure_id == procedure_id)
        .first()
    )
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    old_values = get_model_dict(step)

    if data.title is not None:
        step.title = data.title
    if data.instructions is not None:
        step.instructions = data.instructions
    if data.required_data_schema is not None:
        step.required_data_schema = data.required_data_schema
    if data.is_contingency is not None:
        step.is_contingency = data.is_contingency
    if data.estimated_duration_minutes is not None:
        step.estimated_duration_minutes = data.estimated_duration_minutes

    log_update(db, step, old_values, user_id)
    db.commit()
    db.refresh(step)

    return StepSchema.model_validate(step)


@router.delete("/{procedure_id}/steps/{step_id}", status_code=204)
async def delete_step(
    procedure_id: int,
    step_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Delete a step."""
    step = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.id == step_id, ProcedureStep.procedure_id == procedure_id)
        .first()
    )
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    deleted_order = step.order
    log_delete(db, step, user_id)
    db.delete(step)

    # Reorder remaining steps
    remaining = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == procedure_id, ProcedureStep.order > deleted_order)
        .all()
    )
    for s in remaining:
        s.order -= 1

    db.commit()


@router.post("/{procedure_id}/steps/reorder", response_model=list[StepSchema])
async def reorder_steps(
    procedure_id: int,
    data: StepReorder,
    db: DbSession,
    user_id: CurrentUserId,
) -> list[StepSchema]:
    """Reorder steps."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    # Verify all step IDs belong to this procedure
    steps = db.query(ProcedureStep).filter(ProcedureStep.procedure_id == procedure_id).all()
    step_map = {s.id: s for s in steps}

    if set(data.step_ids) != set(step_map.keys()):
        raise HTTPException(status_code=400, detail="Step IDs don't match procedure steps")

    # Update order
    for i, step_id in enumerate(data.step_ids, start=1):
        step_map[step_id].order = i

    db.commit()

    # Return updated steps in order
    steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == procedure_id)
        .order_by(ProcedureStep.order)
        .all()
    )
    return [StepSchema.model_validate(s) for s in steps]


# ============ Versions ============


@router.post("/{procedure_id}/publish", response_model=VersionResponse, status_code=201)
async def publish_version(
    procedure_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> VersionResponse:
    """Publish current steps as a new immutable version."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    # Get current steps
    steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == procedure_id)
        .order_by(ProcedureStep.order)
        .all()
    )

    if not steps:
        raise HTTPException(status_code=400, detail="Cannot publish procedure with no steps")

    # Get next version number
    max_version = (
        db.query(func.max(ProcedureVersion.version_number))
        .filter(ProcedureVersion.procedure_id == procedure_id)
        .scalar()
    )
    next_version = (max_version or 0) + 1

    # Create snapshot with hierarchical structure
    def step_to_dict(step: ProcedureStep) -> dict:
        return {
            "id": step.id,
            "order": step.order,
            "step_number": step.step_number,
            "level": step.level,
            "parent_step_id": step.parent_step_id,
            "title": step.title,
            "instructions": step.instructions,
            "required_data_schema": step.required_data_schema,
            "is_contingency": step.is_contingency,
            "estimated_duration_minutes": step.estimated_duration_minutes,
            "workcenter_id": step.workcenter_id,
        }

    content = {
        "procedure_name": procedure.name,
        "procedure_description": procedure.description,
        "steps": [step_to_dict(s) for s in steps],
    }

    version = ProcedureVersion(
        procedure_id=procedure_id,
        version_number=next_version,
        content=content,
        created_by_id=user_id,
    )
    db.add(version)
    db.flush()

    # Update procedure to point to this version and set to active
    procedure.current_version_id = version.id
    procedure.status = ProcedureStatus.ACTIVE

    log_create(db, version, user_id)
    db.commit()
    db.refresh(version)

    return VersionResponse.model_validate(version)


@router.get("/{procedure_id}/versions", response_model=list[VersionResponse])
async def list_versions(
    procedure_id: int,
    db: DbSession,
) -> list[VersionResponse]:
    """List all published versions of a procedure."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    versions = (
        db.query(ProcedureVersion)
        .filter(ProcedureVersion.procedure_id == procedure_id)
        .order_by(ProcedureVersion.version_number.desc())
        .all()
    )

    return [VersionResponse.model_validate(v) for v in versions]


@router.get("/versions/{version_id}", response_model=VersionDetailResponse)
async def get_version(
    version_id: int,
    db: DbSession,
) -> VersionDetailResponse:
    """Get specific version with full content."""
    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return VersionDetailResponse.model_validate(version)


# ============ Kit ============


@router.get("/{procedure_id}/kit", response_model=list[KitItemResponse])
async def get_kit(
    procedure_id: int,
    db: DbSession,
) -> list[KitItemResponse]:
    """Get kit (bill of materials) for a procedure."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    kit_items = (
        db.query(Kit)
        .join(Part)
        .filter(Kit.procedure_id == procedure_id)
        .order_by(Part.name)
        .all()
    )

    return [
        KitItemResponse(
            id=k.id,
            part_id=k.part_id,
            part_name=k.part.name,
            part_external_pn=k.part.external_pn,
            quantity_required=float(k.quantity_required),
        )
        for k in kit_items
    ]


@router.post("/{procedure_id}/kit", response_model=KitItemResponse, status_code=201)
async def add_kit_item(
    procedure_id: int,
    data: KitItemCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> KitItemResponse:
    """Add a part to the kit."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    part = db.query(Part).filter(Part.id == data.part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    # Check if already in kit
    existing = (
        db.query(Kit)
        .filter(Kit.procedure_id == procedure_id, Kit.part_id == data.part_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Part already in kit")

    kit_item = Kit(
        procedure_id=procedure_id,
        part_id=data.part_id,
        quantity_required=Decimal(str(data.quantity_required)),
    )
    db.add(kit_item)
    db.flush()

    log_create(db, kit_item, user_id)
    db.commit()
    db.refresh(kit_item)

    return KitItemResponse(
        id=kit_item.id,
        part_id=kit_item.part_id,
        part_name=part.name,
        part_external_pn=part.external_pn,
        quantity_required=float(kit_item.quantity_required),
    )


@router.patch("/{procedure_id}/kit/{kit_id}", response_model=KitItemResponse)
async def update_kit_item(
    procedure_id: int,
    kit_id: int,
    data: KitItemUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> KitItemResponse:
    """Update kit item quantity."""
    kit_item = (
        db.query(Kit)
        .filter(Kit.id == kit_id, Kit.procedure_id == procedure_id)
        .first()
    )
    if not kit_item:
        raise HTTPException(status_code=404, detail="Kit item not found")

    with AuditContext(db, kit_item, user_id):
        kit_item.quantity_required = Decimal(str(data.quantity_required))

    db.commit()
    db.refresh(kit_item)

    return KitItemResponse(
        id=kit_item.id,
        part_id=kit_item.part_id,
        part_name=kit_item.part.name,
        part_external_pn=kit_item.part.external_pn,
        quantity_required=float(kit_item.quantity_required),
    )


@router.delete("/{procedure_id}/kit/{part_id}", status_code=204)
async def remove_kit_item(
    procedure_id: int,
    part_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Remove a part from the kit."""
    kit_item = (
        db.query(Kit)
        .filter(Kit.procedure_id == procedure_id, Kit.part_id == part_id)
        .first()
    )
    if not kit_item:
        raise HTTPException(status_code=404, detail="Kit item not found")

    log_delete(db, kit_item, user_id)
    db.delete(kit_item)
    db.commit()


# ============ Procedure Output (Assembly) Management ============


class OutputResponse(BaseModel):
    """Procedure output item response."""

    id: int
    part_id: int
    part_name: str
    part_external_pn: str | None
    quantity_produced: float

    model_config = {"from_attributes": True}


class OutputCreate(BaseModel):
    """Create output item request."""

    part_id: int
    quantity_produced: float = 1.0


class OutputUpdate(BaseModel):
    """Update output item request."""

    quantity_produced: float


@router.get("/{procedure_id}/outputs", response_model=list[OutputResponse])
async def get_outputs(
    procedure_id: int,
    db: DbSession,
) -> list[OutputResponse]:
    """Get all output parts for a procedure (what it produces)."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    return [
        OutputResponse(
            id=o.id,
            part_id=o.part_id,
            part_name=o.part.name,
            part_external_pn=o.part.external_pn,
            quantity_produced=float(o.quantity_produced),
        )
        for o in procedure.outputs
    ]


@router.post("/{procedure_id}/outputs", response_model=OutputResponse, status_code=201)
async def add_output(
    procedure_id: int,
    data: OutputCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> OutputResponse:
    """Add an output part to a procedure (what it produces)."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    # Verify part exists
    part = db.query(Part).filter(Part.id == data.part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    # Check if already in outputs
    existing = (
        db.query(ProcedureOutput)
        .filter(ProcedureOutput.procedure_id == procedure_id, ProcedureOutput.part_id == data.part_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Part already in outputs")

    output = ProcedureOutput(
        procedure_id=procedure_id,
        part_id=data.part_id,
        quantity_produced=data.quantity_produced,
    )
    db.add(output)
    log_create(db, output, user_id)
    db.commit()
    db.refresh(output)

    return OutputResponse(
        id=output.id,
        part_id=output.part_id,
        part_name=part.name,
        part_external_pn=part.external_pn,
        quantity_produced=float(output.quantity_produced),
    )


@router.patch("/{procedure_id}/outputs/{part_id}", response_model=OutputResponse)
async def update_output(
    procedure_id: int,
    part_id: int,
    data: OutputUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> OutputResponse:
    """Update an output item quantity."""
    output = (
        db.query(ProcedureOutput)
        .filter(ProcedureOutput.procedure_id == procedure_id, ProcedureOutput.part_id == part_id)
        .first()
    )
    if not output:
        raise HTTPException(status_code=404, detail="Output item not found")

    old_values = get_model_dict(output)
    output.quantity_produced = data.quantity_produced

    log_update(db, output, old_values, user_id)
    db.commit()
    db.refresh(output)

    return OutputResponse(
        id=output.id,
        part_id=output.part_id,
        part_name=output.part.name,
        part_external_pn=output.part.external_pn,
        quantity_produced=float(output.quantity_produced),
    )


@router.delete("/{procedure_id}/outputs/{part_id}", status_code=204)
async def remove_output(
    procedure_id: int,
    part_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Remove a part from the outputs."""
    output = (
        db.query(ProcedureOutput)
        .filter(ProcedureOutput.procedure_id == procedure_id, ProcedureOutput.part_id == part_id)
        .first()
    )
    if not output:
        raise HTTPException(status_code=404, detail="Output item not found")

    log_delete(db, output, user_id)
    db.delete(output)
    db.commit()


# ============ Step Kit (Step-Level Parts) ============


class StepKitResponse(BaseModel):
    """Step kit item response."""

    id: int
    step_id: int
    part_id: int
    part_name: str
    part_external_pn: str | None
    quantity_required: float
    usage_type: str
    notes: str | None = None

    model_config = {"from_attributes": True}


class StepKitCreate(BaseModel):
    """Add part to step kit."""

    part_id: int
    quantity_required: float = Field(..., gt=0)
    usage_type: str = "consume"  # "consume" or "tooling"
    notes: str | None = None


class StepKitUpdate(BaseModel):
    """Update step kit item."""

    quantity_required: float | None = Field(None, gt=0)
    usage_type: str | None = None
    notes: str | None = None


@router.get("/{procedure_id}/steps/{step_id}/kit", response_model=list[StepKitResponse])
async def get_step_kit(
    procedure_id: int,
    step_id: int,
    db: DbSession,
) -> list[StepKitResponse]:
    """Get parts required for a specific step."""
    step = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.id == step_id, ProcedureStep.procedure_id == procedure_id)
        .first()
    )
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    return [
        StepKitResponse(
            id=sk.id,
            step_id=sk.step_id,
            part_id=sk.part_id,
            part_name=sk.part.name,
            part_external_pn=sk.part.external_pn,
            quantity_required=float(sk.quantity_required),
            usage_type=sk.usage_type.value if hasattr(sk.usage_type, "value") else sk.usage_type,
            notes=sk.notes,
        )
        for sk in step.step_kits
    ]


@router.post("/{procedure_id}/steps/{step_id}/kit", response_model=StepKitResponse, status_code=201)
async def add_step_kit_item(
    procedure_id: int,
    step_id: int,
    data: StepKitCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepKitResponse:
    """Add a part to a step's kit."""
    step = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.id == step_id, ProcedureStep.procedure_id == procedure_id)
        .first()
    )
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    part = db.query(Part).filter(Part.id == data.part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    # Check if already in step kit
    existing = (
        db.query(StepKit)
        .filter(StepKit.step_id == step_id, StepKit.part_id == data.part_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Part already in step kit")

    # Validate usage type
    try:
        usage = UsageType(data.usage_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid usage type: {data.usage_type}")

    step_kit = StepKit(
        step_id=step_id,
        part_id=data.part_id,
        quantity_required=Decimal(str(data.quantity_required)),
        usage_type=usage,
        notes=data.notes,
    )
    db.add(step_kit)
    db.flush()

    log_create(db, step_kit, user_id)
    db.commit()
    db.refresh(step_kit)

    return StepKitResponse(
        id=step_kit.id,
        step_id=step_kit.step_id,
        part_id=step_kit.part_id,
        part_name=part.name,
        part_external_pn=part.external_pn,
        quantity_required=float(step_kit.quantity_required),
        usage_type=step_kit.usage_type.value if hasattr(step_kit.usage_type, "value") else step_kit.usage_type,
        notes=step_kit.notes,
    )


@router.patch("/{procedure_id}/steps/{step_id}/kit/{kit_id}", response_model=StepKitResponse)
async def update_step_kit_item(
    procedure_id: int,
    step_id: int,
    kit_id: int,
    data: StepKitUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepKitResponse:
    """Update a step kit item."""
    step_kit = (
        db.query(StepKit)
        .join(ProcedureStep)
        .filter(
            StepKit.id == kit_id,
            StepKit.step_id == step_id,
            ProcedureStep.procedure_id == procedure_id,
        )
        .first()
    )
    if not step_kit:
        raise HTTPException(status_code=404, detail="Step kit item not found")

    old_values = get_model_dict(step_kit)

    if data.quantity_required is not None:
        step_kit.quantity_required = Decimal(str(data.quantity_required))
    if data.usage_type is not None:
        try:
            step_kit.usage_type = UsageType(data.usage_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid usage type: {data.usage_type}")
    if data.notes is not None:
        step_kit.notes = data.notes

    log_update(db, step_kit, old_values, user_id)
    db.commit()
    db.refresh(step_kit)

    return StepKitResponse(
        id=step_kit.id,
        step_id=step_kit.step_id,
        part_id=step_kit.part_id,
        part_name=step_kit.part.name,
        part_external_pn=step_kit.part.external_pn,
        quantity_required=float(step_kit.quantity_required),
        usage_type=step_kit.usage_type.value if hasattr(step_kit.usage_type, "value") else step_kit.usage_type,
        notes=step_kit.notes,
    )


@router.delete("/{procedure_id}/steps/{step_id}/kit/{part_id}", status_code=204)
async def remove_step_kit_item(
    procedure_id: int,
    step_id: int,
    part_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Remove a part from a step's kit."""
    step_kit = (
        db.query(StepKit)
        .join(ProcedureStep)
        .filter(
            StepKit.step_id == step_id,
            StepKit.part_id == part_id,
            ProcedureStep.procedure_id == procedure_id,
        )
        .first()
    )
    if not step_kit:
        raise HTTPException(status_code=404, detail="Step kit item not found")

    log_delete(db, step_kit, user_id)
    db.delete(step_kit)
    db.commit()


# ============ Procedure Cloning ============


class CloneProcedureRequest(BaseModel):
    """Request to clone a procedure."""

    new_name: str | None = None
    copy_kit: bool = True
    copy_outputs: bool = True


@router.post("/{procedure_id}/clone", response_model=ProcedureResponse, status_code=201)
async def clone_procedure(
    procedure_id: int,
    data: CloneProcedureRequest,
    db: DbSession,
    user_id: CurrentUserId,
) -> ProcedureResponse:
    """Clone an existing procedure to create a new one.

    Creates a copy of the procedure including:
    - All steps (with hierarchy preserved)
    - Step-level kit items (if copy_kit=True)
    - Procedure-level kit items (if copy_kit=True)
    - Output definitions (if copy_outputs=True)

    The new procedure starts in DRAFT status with version 0.
    """
    # Get source procedure
    source = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Procedure not found")

    # Create new procedure
    clone_name = data.new_name or f"Copy of {source.name}"
    new_procedure = MasterProcedure(
        name=clone_name,
        description=source.description,
        status=ProcedureStatus.DRAFT,
        current_version_id=None,
    )
    db.add(new_procedure)
    db.flush()

    # Map old step IDs to new step IDs (for parent references)
    step_id_map: dict[int, int] = {}

    # Get source steps ordered by hierarchy
    source_steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == source.id)
        .order_by(ProcedureStep.order)
        .all()
    )

    # Clone steps (first pass - create all steps without parent references)
    for source_step in source_steps:
        new_step = ProcedureStep(
            procedure_id=new_procedure.id,
            order=source_step.order,
            step_number=source_step.step_number,
            level=source_step.level,
            parent_step_id=None,  # Set in second pass
            title=source_step.title,
            instructions=source_step.instructions,
            required_data_schema=source_step.required_data_schema,
            is_contingency=source_step.is_contingency,
            estimated_duration_minutes=source_step.estimated_duration_minutes,
            workcenter_id=source_step.workcenter_id,
        )
        db.add(new_step)
        db.flush()
        step_id_map[source_step.id] = new_step.id

    # Second pass - set parent references
    for source_step in source_steps:
        if source_step.parent_step_id and source_step.parent_step_id in step_id_map:
            new_step = db.query(ProcedureStep).filter(
                ProcedureStep.id == step_id_map[source_step.id]
            ).first()
            if new_step:
                new_step.parent_step_id = step_id_map[source_step.parent_step_id]

    # Clone step-level kit items
    if data.copy_kit:
        for source_step in source_steps:
            source_step_kits = (
                db.query(StepKit)
                .filter(StepKit.step_id == source_step.id)
                .all()
            )
            for sk in source_step_kits:
                new_step_kit = StepKit(
                    step_id=step_id_map[source_step.id],
                    part_id=sk.part_id,
                    quantity_required=sk.quantity_required,
                    usage_type=sk.usage_type,
                    notes=sk.notes,
                )
                db.add(new_step_kit)

        # Clone procedure-level kit items
        source_kits = db.query(Kit).filter(Kit.procedure_id == source.id).all()
        for kit in source_kits:
            new_kit = Kit(
                procedure_id=new_procedure.id,
                part_id=kit.part_id,
                quantity_required=kit.quantity_required,
            )
            db.add(new_kit)

    # Clone output definitions
    if data.copy_outputs:
        source_outputs = db.query(ProcedureOutput).filter(ProcedureOutput.procedure_id == source.id).all()
        for output in source_outputs:
            new_output = ProcedureOutput(
                procedure_id=new_procedure.id,
                part_id=output.part_id,
                quantity_produced=output.quantity_produced,
            )
            db.add(new_output)

    log_create(db, new_procedure, user_id)
    db.commit()
    db.refresh(new_procedure)

    # Build response with steps
    steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == new_procedure.id)
        .order_by(ProcedureStep.order)
        .all()
    )

    return ProcedureResponse.model_validate(new_procedure)

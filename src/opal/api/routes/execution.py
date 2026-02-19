"""Execution API routes - procedure instances and step execution."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_update, get_model_dict
from opal.core.designators import generate_opal_number, generate_serial_number, generate_work_order_number
from opal.core.events import (
    emit_instance_completed,
    emit_instance_started,
    emit_step_completed,
    emit_step_started,
    emit_user_joined,
    emit_user_left,
)
from opal.core.genealogy import record_assembly_genealogy
from opal.db.models import InventoryRecord, Kit, Part, ProcedureOutput
from opal.db.models.execution import (
    InstanceStatus,
    ProcedureInstance,
    StepExecution,
    StepStatus,
)
from opal.db.models.inventory import (
    ConsumptionType,
    InventoryConsumption,
    InventoryProduction,
    ProductionStatus,
    SourceType,
    UsageType,
)
from opal.db.models.issue import Issue, IssuePriority, IssueStatus, IssueType
from opal.db.models.procedure import MasterProcedure, ProcedureType, ProcedureVersion

router = APIRouter(prefix="/procedure-instances", tags=["execution"])


# ============ Schemas ============


class StepExecutionResponse(BaseModel):
    """Step execution response."""

    id: int
    step_number: int
    step_number_str: str  # Display number like "1", "1.1", "C1"
    level: int  # 0=parent OP, 1+=sub-step
    parent_step_order: int | None = None
    status: str
    data_captured: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by_id: int | None = None
    signed_off_at: datetime | None = None
    signed_off_by_id: int | None = None
    duration_seconds: int | None = None

    model_config = {"from_attributes": True}


class InstanceResponse(BaseModel):
    """Procedure instance response."""

    id: int
    procedure_id: int
    procedure_name: str
    version_id: int
    version_number: int
    work_order_number: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    started_by_id: int | None = None
    duration_seconds: int | None = None
    scheduled_start_at: datetime | None = None
    target_completion_at: datetime | None = None
    priority: int = 0
    created_at: datetime
    step_executions: list[StepExecutionResponse] = []

    model_config = {"from_attributes": True}


class InstanceListResponse(BaseModel):
    """Paginated instance list."""

    items: list[InstanceResponse]
    total: int
    page: int
    page_size: int


class InstanceCreate(BaseModel):
    """Create procedure instance request."""

    procedure_id: int
    version_id: int | None = Field(None, description="If not provided, uses current version")
    work_order_number: str | None = None
    scheduled_start_at: datetime | None = None
    target_completion_at: datetime | None = None
    priority: int = 0


class InstanceUpdate(BaseModel):
    """Update instance request."""

    status: str | None = None
    work_order_number: str | None = None
    scheduled_start_at: datetime | None = None
    target_completion_at: datetime | None = None
    priority: int | None = None


class StepStart(BaseModel):
    """Start step request."""

    pass  # No fields needed, just marks step as started


class StepComplete(BaseModel):
    """Complete step request."""

    data_captured: dict[str, Any] | None = None


class NonConformanceCreate(BaseModel):
    """Log non-conformance during step execution."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: str = "medium"


# ============ Instance CRUD ============


@router.get("", response_model=InstanceListResponse)
async def list_instances(
    db: DbSession,
    procedure_id: int | None = Query(None),
    status: str | None = Query(None),
    work_order: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> InstanceListResponse:
    """List procedure instances with optional filters."""
    query = db.query(ProcedureInstance)

    if procedure_id:
        query = query.filter(ProcedureInstance.procedure_id == procedure_id)
    if status:
        query = query.filter(ProcedureInstance.status == status)
    if work_order:
        query = query.filter(ProcedureInstance.work_order_number.ilike(f"%{work_order}%"))

    total = query.count()

    instances = (
        query.order_by(ProcedureInstance.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for inst in instances:
        version = db.query(ProcedureVersion).filter(ProcedureVersion.id == inst.version_id).first()
        items.append(
            InstanceResponse(
                id=inst.id,
                procedure_id=inst.procedure_id,
                procedure_name=inst.procedure.name,
                version_id=inst.version_id,
                version_number=version.version_number if version else 0,
                work_order_number=inst.work_order_number,
                status=inst.status.value if hasattr(inst.status, 'value') else inst.status,
                started_at=inst.started_at,
                completed_at=inst.completed_at,
                started_by_id=inst.started_by_id,
                duration_seconds=inst.duration_seconds,
                scheduled_start_at=inst.scheduled_start_at,
                target_completion_at=inst.target_completion_at,
                priority=inst.priority,
                created_at=inst.created_at,
                step_executions=[
                    StepExecutionResponse(
                        id=se.id,
                        step_number=se.step_number,
                        step_number_str=se.step_number_str,
                        level=se.level,
                        parent_step_order=se.parent_step_order,
                        status=se.status.value if hasattr(se.status, 'value') else se.status,
                        data_captured=se.data_captured,
                        started_at=se.started_at,
                        completed_at=se.completed_at,
                        completed_by_id=se.completed_by_id,
                        signed_off_at=se.signed_off_at,
                        signed_off_by_id=se.signed_off_by_id,
                        duration_seconds=se.duration_seconds,
                    )
                    for se in inst.step_executions
                ],
            )
        )

    return InstanceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=InstanceResponse, status_code=201)
async def create_instance(
    data: InstanceCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> InstanceResponse:
    """Start a new procedure instance."""
    # Validate procedure exists
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == data.procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        raise HTTPException(status_code=404, detail="Procedure not found")

    # Get version
    if data.version_id:
        version = db.query(ProcedureVersion).filter(ProcedureVersion.id == data.version_id).first()
        if not version or version.procedure_id != data.procedure_id:
            raise HTTPException(status_code=404, detail="Version not found for this procedure")
    else:
        # Use current version
        if not procedure.current_version_id:
            raise HTTPException(status_code=400, detail="Procedure has no published version")
        version = db.query(ProcedureVersion).filter(
            ProcedureVersion.id == procedure.current_version_id
        ).first()

    # Generate work order number if not provided
    work_order_number = data.work_order_number or generate_work_order_number(db)

    # Create instance
    instance = ProcedureInstance(
        procedure_id=data.procedure_id,
        version_id=version.id,
        work_order_number=work_order_number,
        status=InstanceStatus.PENDING,
        started_by_id=user_id,
        scheduled_start_at=data.scheduled_start_at,
        target_completion_at=data.target_completion_at,
        priority=data.priority,
    )
    db.add(instance)
    db.flush()

    # Create step executions from version snapshot, preserving hierarchy
    steps = version.content.get("steps", [])

    # Build a map of step order -> parent step order for hierarchy
    order_to_parent: dict[int, int | None] = {}
    for step in steps:
        parent_id = step.get("parent_step_id")
        if parent_id:
            # Find parent's order
            parent_step = next((s for s in steps if s.get("id") == parent_id), None)
            order_to_parent[step["order"]] = parent_step["order"] if parent_step else None
        else:
            order_to_parent[step["order"]] = None

    for step in steps:
        step_exec = StepExecution(
            instance_id=instance.id,
            step_number=step["order"],
            step_number_str=step.get("step_number", str(step["order"])),
            level=step.get("level", 0),
            parent_step_order=order_to_parent.get(step["order"]),
            status=StepStatus.PENDING,
        )
        db.add(step_exec)

    # Auto-allocate output assemblies for BUILD procedures
    proc_type = procedure.procedure_type
    if hasattr(proc_type, 'value'):
        proc_type = proc_type.value
    if proc_type == ProcedureType.BUILD.value:
        outputs = db.query(ProcedureOutput).filter(
            ProcedureOutput.procedure_id == data.procedure_id
        ).all()
        for output in outputs:
            output_part = db.query(Part).filter(Part.id == output.part_id).first()
            if not output_part:
                continue

            serial = generate_serial_number(db, output_part)
            opal_num = generate_opal_number(db)

            # Create inventory record (qty=0 until finalized)
            inv_record = InventoryRecord(
                part_id=output.part_id,
                quantity=0,
                location="",
                lot_number=work_order_number,
                opal_number=opal_num,
                source_type=SourceType.PRODUCTION,
            )
            db.add(inv_record)
            db.flush()

            # Create production record in PLANNED status
            production = InventoryProduction(
                inventory_record_id=inv_record.id,
                quantity=output.quantity_produced,
                procedure_instance_id=instance.id,
                serial_number=serial,
                produced_opal_number=opal_num,
                status=ProductionStatus.PLANNED,
                produced_by_id=user_id,
            )
            db.add(production)
            db.flush()

            # Link inventory record to its production
            inv_record.source_production_id = production.id

    log_create(db, instance, user_id)
    db.commit()
    db.refresh(instance)

    return InstanceResponse(
        id=instance.id,
        procedure_id=instance.procedure_id,
        procedure_name=procedure.name,
        version_id=instance.version_id,
        version_number=version.version_number,
        work_order_number=instance.work_order_number,
        status=instance.status.value if hasattr(instance.status, 'value') else instance.status,
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        started_by_id=instance.started_by_id,
        duration_seconds=instance.duration_seconds,
        scheduled_start_at=instance.scheduled_start_at,
        target_completion_at=instance.target_completion_at,
        priority=instance.priority,
        created_at=instance.created_at,
        step_executions=[
            StepExecutionResponse(
                id=se.id,
                step_number=se.step_number,
                step_number_str=se.step_number_str,
                level=se.level,
                parent_step_order=se.parent_step_order,
                status=se.status.value if hasattr(se.status, 'value') else se.status,
                data_captured=se.data_captured,
                started_at=se.started_at,
                completed_at=se.completed_at,
                completed_by_id=se.completed_by_id,
                signed_off_at=se.signed_off_at,
                signed_off_by_id=se.signed_off_by_id,
                duration_seconds=se.duration_seconds,
            )
            for se in instance.step_executions
        ],
    )


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: int,
    db: DbSession,
) -> InstanceResponse:
    """Get procedure instance by ID."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == instance.version_id).first()

    return InstanceResponse(
        id=instance.id,
        procedure_id=instance.procedure_id,
        procedure_name=instance.procedure.name,
        version_id=instance.version_id,
        version_number=version.version_number if version else 0,
        work_order_number=instance.work_order_number,
        status=instance.status.value if hasattr(instance.status, 'value') else instance.status,
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        started_by_id=instance.started_by_id,
        duration_seconds=instance.duration_seconds,
        scheduled_start_at=instance.scheduled_start_at,
        target_completion_at=instance.target_completion_at,
        priority=instance.priority,
        created_at=instance.created_at,
        step_executions=[
            StepExecutionResponse(
                id=se.id,
                step_number=se.step_number,
                step_number_str=se.step_number_str,
                level=se.level,
                parent_step_order=se.parent_step_order,
                status=se.status.value if hasattr(se.status, 'value') else se.status,
                data_captured=se.data_captured,
                started_at=se.started_at,
                completed_at=se.completed_at,
                completed_by_id=se.completed_by_id,
                signed_off_at=se.signed_off_at,
                signed_off_by_id=se.signed_off_by_id,
                duration_seconds=se.duration_seconds,
            )
            for se in instance.step_executions
        ],
    )


@router.patch("/{instance_id}", response_model=InstanceResponse)
async def update_instance(
    instance_id: int,
    data: InstanceUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> InstanceResponse:
    """Update instance (status, work order, scheduling)."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    old_values = get_model_dict(instance)

    if data.status is not None:
        try:
            new_status = InstanceStatus(data.status)
            instance.status = new_status

            # Set timestamps based on status
            if new_status == InstanceStatus.IN_PROGRESS and not instance.started_at:
                instance.started_at = datetime.now(timezone.utc)
            elif new_status in [InstanceStatus.COMPLETED, InstanceStatus.ABORTED]:
                instance.completed_at = datetime.now(timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")

    if data.work_order_number is not None:
        instance.work_order_number = data.work_order_number

    # Handle scheduling field updates
    if data.scheduled_start_at is not None:
        instance.scheduled_start_at = data.scheduled_start_at
    if data.target_completion_at is not None:
        instance.target_completion_at = data.target_completion_at
    if data.priority is not None:
        instance.priority = data.priority

    log_update(db, instance, old_values, user_id)
    db.commit()
    db.refresh(instance)

    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == instance.version_id).first()

    return InstanceResponse(
        id=instance.id,
        procedure_id=instance.procedure_id,
        procedure_name=instance.procedure.name,
        version_id=instance.version_id,
        version_number=version.version_number if version else 0,
        work_order_number=instance.work_order_number,
        status=instance.status.value if hasattr(instance.status, 'value') else instance.status,
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        started_by_id=instance.started_by_id,
        duration_seconds=instance.duration_seconds,
        scheduled_start_at=instance.scheduled_start_at,
        target_completion_at=instance.target_completion_at,
        priority=instance.priority,
        created_at=instance.created_at,
        step_executions=[
            StepExecutionResponse(
                id=se.id,
                step_number=se.step_number,
                step_number_str=se.step_number_str,
                level=se.level,
                parent_step_order=se.parent_step_order,
                status=se.status.value if hasattr(se.status, 'value') else se.status,
                data_captured=se.data_captured,
                started_at=se.started_at,
                completed_at=se.completed_at,
                completed_by_id=se.completed_by_id,
                signed_off_at=se.signed_off_at,
                signed_off_by_id=se.signed_off_by_id,
                duration_seconds=se.duration_seconds,
            )
            for se in instance.step_executions
        ],
    )


# ============ Step Execution ============


@router.post("/{instance_id}/steps/{step_number}/start", response_model=StepExecutionResponse)
async def start_step(
    instance_id: int,
    step_number: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepExecutionResponse:
    """Start a step execution."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Check instance is in progress
    status_val = instance.status.value if hasattr(instance.status, 'value') else instance.status
    if status_val not in [InstanceStatus.PENDING.value, InstanceStatus.IN_PROGRESS.value]:
        raise HTTPException(status_code=400, detail="Instance is not active")

    # Start instance if pending
    if status_val == InstanceStatus.PENDING.value:
        instance.status = InstanceStatus.IN_PROGRESS
        instance.started_at = datetime.now(timezone.utc)

        # Transition planned production records to WIP
        db.query(InventoryProduction).filter(
            InventoryProduction.procedure_instance_id == instance_id,
            InventoryProduction.status == ProductionStatus.PLANNED,
        ).update({InventoryProduction.status: ProductionStatus.WIP})

    step_exec = (
        db.query(StepExecution)
        .filter(StepExecution.instance_id == instance_id, StepExecution.step_number == step_number)
        .first()
    )
    if not step_exec:
        raise HTTPException(status_code=404, detail="Step not found")

    step_status = step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status
    if step_status != StepStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Step already started or completed")

    step_exec.status = StepStatus.IN_PROGRESS
    step_exec.started_at = datetime.now(timezone.utc)

    # Get user name for event
    from opal.db.models import User
    user = db.query(User).filter(User.id == user_id).first()
    user_name = user.name if user else None

    db.commit()
    db.refresh(step_exec)

    # Emit real-time events
    await emit_step_started(instance_id, step_number, user_id, user_name)
    if status_val == InstanceStatus.PENDING.value:
        # Instance just started
        await emit_instance_started(instance_id, instance.procedure_id, user_id, user_name)

    return StepExecutionResponse(
        id=step_exec.id,
        step_number=step_exec.step_number,
        step_number_str=step_exec.step_number_str,
        level=step_exec.level,
        parent_step_order=step_exec.parent_step_order,
        status=step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status,
        data_captured=step_exec.data_captured,
        started_at=step_exec.started_at,
        completed_at=step_exec.completed_at,
        completed_by_id=step_exec.completed_by_id,
        signed_off_at=step_exec.signed_off_at,
        signed_off_by_id=step_exec.signed_off_by_id,
        duration_seconds=step_exec.duration_seconds,
    )


@router.post("/{instance_id}/steps/{step_number}/complete", response_model=StepExecutionResponse)
async def complete_step(
    instance_id: int,
    step_number: int,
    data: StepComplete,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepExecutionResponse:
    """Complete a step execution with optional data capture."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    step_exec = (
        db.query(StepExecution)
        .filter(StepExecution.instance_id == instance_id, StepExecution.step_number == step_number)
        .first()
    )
    if not step_exec:
        raise HTTPException(status_code=404, detail="Step not found")

    step_status = step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status
    if step_status == StepStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Step already completed")

    # If step wasn't started, start it now
    if step_status == StepStatus.PENDING.value:
        step_exec.started_at = datetime.now(timezone.utc)

    step_exec.status = StepStatus.COMPLETED
    step_exec.completed_at = datetime.now(timezone.utc)
    step_exec.completed_by_id = user_id
    if data.data_captured:
        step_exec.data_captured = data.data_captured

    # Get user name for event
    from opal.db.models import User
    user = db.query(User).filter(User.id == user_id).first()
    user_name = user.name if user else None

    # Track old status to detect completion
    old_instance_status = instance.status.value if hasattr(instance.status, 'value') else instance.status

    # Check if procedure is complete (considering contingency rules)
    _check_instance_completion(instance, db)

    db.commit()
    db.refresh(step_exec)
    db.refresh(instance)

    # Emit real-time events
    await emit_step_completed(instance_id, step_number, user_id, user_name)

    # Check if instance just completed
    new_instance_status = instance.status.value if hasattr(instance.status, 'value') else instance.status
    if old_instance_status != InstanceStatus.COMPLETED.value and new_instance_status == InstanceStatus.COMPLETED.value:
        await emit_instance_completed(instance_id, instance.procedure_id, new_instance_status)

    return StepExecutionResponse(
        id=step_exec.id,
        step_number=step_exec.step_number,
        step_number_str=step_exec.step_number_str,
        level=step_exec.level,
        parent_step_order=step_exec.parent_step_order,
        status=step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status,
        data_captured=step_exec.data_captured,
        started_at=step_exec.started_at,
        completed_at=step_exec.completed_at,
        completed_by_id=step_exec.completed_by_id,
        signed_off_at=step_exec.signed_off_at,
        signed_off_by_id=step_exec.signed_off_by_id,
        duration_seconds=step_exec.duration_seconds,
    )


class StepSkip(BaseModel):
    """Skip step request."""

    reason: str | None = None


@router.post("/{instance_id}/steps/{step_number}/skip", response_model=StepExecutionResponse)
async def skip_step(
    instance_id: int,
    step_number: int,
    data: StepSkip,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepExecutionResponse:
    """Skip a step (mark as N/A or intentionally skipped)."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    step_exec = (
        db.query(StepExecution)
        .filter(StepExecution.instance_id == instance_id, StepExecution.step_number == step_number)
        .first()
    )
    if not step_exec:
        raise HTTPException(status_code=404, detail="Step not found")

    step_status = step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status
    if step_status == StepStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Cannot skip completed step")

    step_exec.status = StepStatus.SKIPPED
    step_exec.completed_at = datetime.now(timezone.utc)
    step_exec.completed_by_id = user_id
    if data.reason:
        step_exec.data_captured = {"skip_reason": data.reason}

    # Check if procedure is complete (considering contingency rules)
    _check_instance_completion(instance, db)

    db.commit()
    db.refresh(step_exec)

    return StepExecutionResponse(
        id=step_exec.id,
        step_number=step_exec.step_number,
        step_number_str=step_exec.step_number_str,
        level=step_exec.level,
        parent_step_order=step_exec.parent_step_order,
        status=step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status,
        data_captured=step_exec.data_captured,
        started_at=step_exec.started_at,
        completed_at=step_exec.completed_at,
        completed_by_id=step_exec.completed_by_id,
        signed_off_at=step_exec.signed_off_at,
        signed_off_by_id=step_exec.signed_off_by_id,
        duration_seconds=step_exec.duration_seconds,
    )


@router.post("/{instance_id}/steps/{step_number}/signoff", response_model=StepExecutionResponse)
async def signoff_step(
    instance_id: int,
    step_number: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> StepExecutionResponse:
    """Sign off on a parent step (OP) after all sub-steps are complete.

    This is used to formally acknowledge that all work under a parent OP
    has been completed and verified. Only steps in AWAITING_SIGNOFF status
    can be signed off.
    """
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    step_exec = (
        db.query(StepExecution)
        .filter(StepExecution.instance_id == instance_id, StepExecution.step_number == step_number)
        .first()
    )
    if not step_exec:
        raise HTTPException(status_code=404, detail="Step not found")

    step_status = step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status

    # Can only sign off steps that are awaiting sign-off
    if step_status != StepStatus.AWAITING_SIGNOFF.value:
        if step_status == StepStatus.SIGNED_OFF.value:
            raise HTTPException(status_code=400, detail="Step already signed off")
        elif step_status in [StepStatus.PENDING.value, StepStatus.IN_PROGRESS.value]:
            raise HTTPException(status_code=400, detail="Step has sub-steps that are not yet complete")
        else:
            raise HTTPException(status_code=400, detail=f"Cannot sign off step in {step_status} status")

    step_exec.status = StepStatus.SIGNED_OFF
    step_exec.signed_off_at = datetime.now(timezone.utc)
    step_exec.signed_off_by_id = user_id

    # Track old status to detect completion
    old_instance_status = instance.status.value if hasattr(instance.status, 'value') else instance.status

    # Check if procedure is complete
    _check_instance_completion(instance, db)

    db.commit()
    db.refresh(step_exec)
    db.refresh(instance)

    # Check if instance just completed
    new_instance_status = instance.status.value if hasattr(instance.status, 'value') else instance.status
    if old_instance_status != InstanceStatus.COMPLETED.value and new_instance_status == InstanceStatus.COMPLETED.value:
        await emit_instance_completed(instance_id, instance.procedure_id, new_instance_status)

    return StepExecutionResponse(
        id=step_exec.id,
        step_number=step_exec.step_number,
        step_number_str=step_exec.step_number_str,
        level=step_exec.level,
        parent_step_order=step_exec.parent_step_order,
        status=step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status,
        data_captured=step_exec.data_captured,
        started_at=step_exec.started_at,
        completed_at=step_exec.completed_at,
        completed_by_id=step_exec.completed_by_id,
        signed_off_at=step_exec.signed_off_at,
        signed_off_by_id=step_exec.signed_off_by_id,
        duration_seconds=step_exec.duration_seconds,
    )


def _check_instance_completion(instance: ProcedureInstance, db: DbSession) -> None:
    """Check if instance should be marked as completed.

    Rules:
    - All non-contingency steps must be completed, signed_off, or skipped
    - Parent steps (level=0 with children) must be SIGNED_OFF or SKIPPED
    - Leaf steps (no children or level>0) can be COMPLETED or SKIPPED
    - Parent steps automatically become AWAITING_SIGNOFF when all children complete
    - Contingency steps are optional (only required if explicitly started)
    """
    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == instance.version_id).first()
    if not version:
        return

    version_steps = {s["order"]: s for s in version.content.get("steps", [])}
    all_steps = db.query(StepExecution).filter(StepExecution.instance_id == instance.id).all()
    step_by_number = {s.step_number: s for s in all_steps}

    # First pass: check if any parent steps should become AWAITING_SIGNOFF
    for step_exec in all_steps:
        if step_exec.level == 0:  # This is a parent OP
            # Find all children of this parent
            children = [s for s in all_steps if s.parent_step_order == step_exec.step_number]

            if children:  # Has sub-steps
                step_status = step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status

                # If parent is still PENDING or IN_PROGRESS, check if all children are done
                if step_status in [StepStatus.PENDING.value, StepStatus.IN_PROGRESS.value]:
                    all_children_done = all(
                        (c.status.value if hasattr(c.status, 'value') else c.status)
                        in [StepStatus.COMPLETED.value, StepStatus.SKIPPED.value]
                        for c in children
                    )
                    if all_children_done:
                        step_exec.status = StepStatus.AWAITING_SIGNOFF

    # Second pass: check instance completion
    for step_exec in all_steps:
        step_data = version_steps.get(step_exec.step_number, {})
        is_contingency = step_data.get("is_contingency", False)
        step_status = step_exec.status.value if hasattr(step_exec.status, 'value') else step_exec.status

        # Find if this step has children
        children = [s for s in all_steps if s.parent_step_order == step_exec.step_number]
        is_parent = len(children) > 0

        # Completed/done statuses depend on step type
        if is_parent:
            # Parent steps must be SIGNED_OFF or SKIPPED
            done_statuses = [StepStatus.SIGNED_OFF.value, StepStatus.SKIPPED.value]
        else:
            # Leaf steps can be COMPLETED, SIGNED_OFF, or SKIPPED
            done_statuses = [StepStatus.COMPLETED.value, StepStatus.SIGNED_OFF.value, StepStatus.SKIPPED.value]

        # Non-contingency steps must be done
        if not is_contingency and step_status not in done_statuses:
            return  # Not complete yet

        # Contingency steps that were started must be completed
        if is_contingency and step_status == StepStatus.IN_PROGRESS.value:
            return  # In-progress contingency blocks completion

    # All required steps are done
    instance.status = InstanceStatus.COMPLETED
    instance.completed_at = datetime.now(timezone.utc)


@router.post("/{instance_id}/steps/{step_number}/nc", status_code=201)
async def log_non_conformance(
    instance_id: int,
    step_number: int,
    data: NonConformanceCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> dict:
    """Log a non-conformance during step execution, creates an Issue."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    step_exec = (
        db.query(StepExecution)
        .filter(StepExecution.instance_id == instance_id, StepExecution.step_number == step_number)
        .first()
    )
    if not step_exec:
        raise HTTPException(status_code=404, detail="Step not found")

    # Create issue
    try:
        priority = IssuePriority(data.priority)
    except ValueError:
        priority = IssuePriority.MEDIUM

    issue = Issue(
        title=data.title,
        description=data.description,
        issue_type=IssueType.NON_CONFORMANCE,
        status=IssueStatus.OPEN,
        priority=priority,
        procedure_id=instance.procedure_id,
        procedure_instance_id=instance_id,
        step_execution_id=step_exec.id,
    )
    db.add(issue)
    db.flush()

    log_create(db, issue, user_id)
    db.commit()
    db.refresh(issue)

    return {
        "id": issue.id,
        "title": issue.title,
        "issue_type": issue.issue_type.value if hasattr(issue.issue_type, 'value') else issue.issue_type,
        "status": issue.status.value if hasattr(issue.status, 'value') else issue.status,
        "priority": issue.priority.value if hasattr(issue.priority, 'value') else issue.priority,
        "procedure_instance_id": instance_id,
        "step_number": step_number,
    }


@router.get("/{instance_id}/version-content")
async def get_instance_version_content(
    instance_id: int,
    db: DbSession,
) -> dict:
    """Get the version content (steps) for an instance."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == instance.version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return version.content


# ============ Kit and Consumption ============


class KitAvailabilityItem(BaseModel):
    """Kit item availability check."""

    part_id: int
    part_name: str
    quantity_required: float
    quantity_available: float
    is_available: bool
    available_locations: list[dict]


class KitAvailabilityResponse(BaseModel):
    """Kit availability response."""

    procedure_id: int
    all_available: bool
    items: list[KitAvailabilityItem]


class ConsumptionItem(BaseModel):
    """Single item to consume."""

    inventory_record_id: int
    quantity: float


class ConsumeKitRequest(BaseModel):
    """Request to consume kit parts."""

    items: list[ConsumptionItem]
    notes: str | None = None


class ConsumptionResponse(BaseModel):
    """Consumption record response."""

    id: int
    part_id: int
    part_name: str
    quantity: float
    location: str
    lot_number: str | None


@router.get("/{instance_id}/kit-availability", response_model=KitAvailabilityResponse)
async def check_kit_availability(
    instance_id: int,
    db: DbSession,
) -> KitAvailabilityResponse:
    """Check if kit parts are available in inventory for this procedure.

    Returns availability status for each kit item with available locations.
    """
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Get kit for this procedure
    kit_items = db.query(Kit).filter(Kit.procedure_id == instance.procedure_id).all()

    items = []
    all_available = True

    for kit_item in kit_items:
        # Get all inventory records for this part
        inv_records = (
            db.query(InventoryRecord)
            .filter(InventoryRecord.part_id == kit_item.part_id, InventoryRecord.quantity > 0)
            .all()
        )

        total_available = sum(float(r.quantity) for r in inv_records)
        qty_required = float(kit_item.quantity_required)
        is_available = total_available >= qty_required

        if not is_available:
            all_available = False

        items.append(
            KitAvailabilityItem(
                part_id=kit_item.part_id,
                part_name=kit_item.part.name,
                quantity_required=qty_required,
                quantity_available=total_available,
                is_available=is_available,
                available_locations=[
                    {
                        "inventory_record_id": r.id,
                        "location": r.location,
                        "lot_number": r.lot_number,
                        "quantity": float(r.quantity),
                    }
                    for r in inv_records
                ],
            )
        )

    return KitAvailabilityResponse(
        procedure_id=instance.procedure_id,
        all_available=all_available,
        items=items,
    )


@router.post("/{instance_id}/consume", response_model=list[ConsumptionResponse])
async def consume_kit(
    instance_id: int,
    data: ConsumeKitRequest,
    db: DbSession,
    user_id: CurrentUserId,
) -> list[ConsumptionResponse]:
    """Consume parts from inventory for this procedure instance.

    This should be called after procedure completion to deduct parts from inventory.
    Creates traceability records linking consumed parts to the procedure.
    """
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    consumptions = []

    for item in data.items:
        inv_record = db.query(InventoryRecord).filter(InventoryRecord.id == item.inventory_record_id).first()
        if not inv_record:
            raise HTTPException(
                status_code=404,
                detail=f"Inventory record {item.inventory_record_id} not found",
            )

        if float(inv_record.quantity) < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient quantity at {inv_record.location} (have {inv_record.quantity}, need {item.quantity})",
            )

        # Deduct from inventory
        inv_record.quantity = float(inv_record.quantity) - item.quantity

        # Create consumption record
        consumption = InventoryConsumption(
            inventory_record_id=inv_record.id,
            quantity=item.quantity,
            consumption_type=ConsumptionType.PROCEDURE,
            procedure_instance_id=instance_id,
            notes=data.notes,
            consumed_by_id=user_id,
        )
        db.add(consumption)
        db.flush()

        consumptions.append(
            ConsumptionResponse(
                id=consumption.id,
                part_id=inv_record.part_id,
                part_name=inv_record.part.name,
                quantity=item.quantity,
                location=inv_record.location,
                lot_number=inv_record.lot_number,
            )
        )

    db.commit()

    return consumptions


class StepConsumeItem(BaseModel):
    """Single step consumption item."""

    inventory_record_id: int
    quantity: float = Field(..., gt=0)
    usage_type: str = "consume"  # "consume" or "tooling"


class StepConsumeRequest(BaseModel):
    """Request to consume parts at a specific step."""

    items: list[StepConsumeItem]
    notes: str | None = None


@router.post("/{instance_id}/steps/{step_number}/consume", response_model=list[ConsumptionResponse])
async def consume_step_parts(
    instance_id: int,
    step_number: int,
    data: StepConsumeRequest,
    db: DbSession,
    user_id: CurrentUserId,
) -> list[ConsumptionResponse]:
    """Consume parts at a specific step during execution.

    This allows tracking which parts were used at which step for traceability.
    Usage types:
    - consume: Part is installed/used up (decrements inventory)
    - tooling: Part is GSE/fixture (tracked but not decremented)
    """
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    step_exec = (
        db.query(StepExecution)
        .filter(StepExecution.instance_id == instance_id, StepExecution.step_number == step_number)
        .first()
    )
    if not step_exec:
        raise HTTPException(status_code=404, detail="Step not found")

    consumptions = []

    for item in data.items:
        inv_record = db.query(InventoryRecord).filter(InventoryRecord.id == item.inventory_record_id).first()
        if not inv_record:
            raise HTTPException(
                status_code=404,
                detail=f"Inventory record {item.inventory_record_id} not found",
            )

        # Validate usage type
        try:
            usage = UsageType(item.usage_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid usage type: {item.usage_type}")

        # Only deduct from inventory if consume type (not tooling)
        if usage == UsageType.CONSUME:
            if float(inv_record.quantity) < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient quantity at {inv_record.location} (have {inv_record.quantity}, need {item.quantity})",
                )
            inv_record.quantity = float(inv_record.quantity) - item.quantity

        # Create consumption record linked to step
        consumption = InventoryConsumption(
            inventory_record_id=inv_record.id,
            quantity=item.quantity,
            consumption_type=ConsumptionType.PROCEDURE,
            usage_type=usage,
            procedure_instance_id=instance_id,
            step_execution_id=step_exec.id,
            notes=data.notes,
            consumed_by_id=user_id,
        )
        db.add(consumption)
        db.flush()

        consumptions.append(
            ConsumptionResponse(
                id=consumption.id,
                part_id=inv_record.part_id,
                part_name=inv_record.part.name,
                quantity=item.quantity,
                location=inv_record.location,
                lot_number=inv_record.lot_number,
            )
        )

    db.commit()

    return consumptions


@router.get("/{instance_id}/steps/{step_number}/consumptions", response_model=list[ConsumptionResponse])
async def get_step_consumptions(
    instance_id: int,
    step_number: int,
    db: DbSession,
) -> list[ConsumptionResponse]:
    """Get all consumptions for a specific step."""
    step_exec = (
        db.query(StepExecution)
        .filter(StepExecution.instance_id == instance_id, StepExecution.step_number == step_number)
        .first()
    )
    if not step_exec:
        raise HTTPException(status_code=404, detail="Step not found")

    consumptions = (
        db.query(InventoryConsumption)
        .filter(InventoryConsumption.step_execution_id == step_exec.id)
        .all()
    )

    return [
        ConsumptionResponse(
            id=c.id,
            part_id=c.inventory_record.part_id,
            part_name=c.inventory_record.part.name,
            quantity=float(c.quantity),
            location=c.inventory_record.location,
            lot_number=c.inventory_record.lot_number,
        )
        for c in consumptions
    ]


@router.get("/{instance_id}/consumptions", response_model=list[ConsumptionResponse])
async def get_consumptions(
    instance_id: int,
    db: DbSession,
) -> list[ConsumptionResponse]:
    """Get all consumption records for this procedure instance."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    consumptions = (
        db.query(InventoryConsumption)
        .filter(InventoryConsumption.procedure_instance_id == instance_id)
        .all()
    )

    return [
        ConsumptionResponse(
            id=c.id,
            part_id=c.inventory_record.part_id,
            part_name=c.inventory_record.part.name,
            quantity=float(c.quantity),
            location=c.inventory_record.location,
            lot_number=c.inventory_record.lot_number,
        )
        for c in consumptions
    ]


# ============ Production (Assembly Output) ============


class OutputItem(BaseModel):
    """Procedure output definition."""

    part_id: int
    part_name: str
    quantity_produced: float


class ProduceItem(BaseModel):
    """Single item to produce."""

    part_id: int
    quantity: float
    location: str
    lot_number: str | None = None
    serial_number: str | None = None


class ProduceRequest(BaseModel):
    """Request to produce output items."""

    items: list[ProduceItem]
    notes: str | None = None


class ProductionResponse(BaseModel):
    """Production record response."""

    id: int
    part_id: int
    part_name: str
    quantity: float
    location: str
    lot_number: str | None
    serial_number: str | None


@router.get("/{instance_id}/outputs", response_model=list[OutputItem])
async def get_procedure_outputs(
    instance_id: int,
    db: DbSession,
) -> list[OutputItem]:
    """Get the expected outputs for this procedure."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    outputs = db.query(ProcedureOutput).filter(ProcedureOutput.procedure_id == instance.procedure_id).all()

    return [
        OutputItem(
            part_id=o.part_id,
            part_name=o.part.name,
            quantity_produced=float(o.quantity_produced),
        )
        for o in outputs
    ]


@router.post("/{instance_id}/produce", response_model=list[ProductionResponse])
async def produce_output(
    instance_id: int,
    data: ProduceRequest,
    db: DbSession,
    user_id: CurrentUserId,
) -> list[ProductionResponse]:
    """Produce output items (assemblies) from this procedure instance.

    Creates inventory records for the produced items and links them to this instance.
    """
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    productions = []

    for item in data.items:
        part = db.query(Part).filter(Part.id == item.part_id).first()
        if not part:
            raise HTTPException(status_code=404, detail=f"Part {item.part_id} not found")

        opal_num = generate_opal_number(db)

        # Always create a new inventory record for produced items (unique OPAL number)
        inv_record = InventoryRecord(
            part_id=item.part_id,
            quantity=item.quantity,
            location=item.location,
            lot_number=item.lot_number,
            opal_number=opal_num,
            source_type=SourceType.PRODUCTION,
        )
        db.add(inv_record)
        db.flush()

        # Create production record
        production = InventoryProduction(
            inventory_record_id=inv_record.id,
            quantity=item.quantity,
            procedure_instance_id=instance_id,
            serial_number=item.serial_number,
            produced_opal_number=opal_num,
            status=ProductionStatus.COMPLETED,
            notes=data.notes,
            produced_by_id=user_id,
        )
        db.add(production)
        db.flush()

        # Link inventory record to its production
        inv_record.source_production_id = production.id

        log_create(db, production, user_id)

        productions.append(
            ProductionResponse(
                id=production.id,
                part_id=item.part_id,
                part_name=part.name,
                quantity=item.quantity,
                location=item.location,
                lot_number=item.lot_number,
                serial_number=item.serial_number,
            )
        )

    db.commit()

    return productions


@router.get("/{instance_id}/productions", response_model=list[ProductionResponse])
async def get_productions(
    instance_id: int,
    db: DbSession,
) -> list[ProductionResponse]:
    """Get all production records for this procedure instance."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    productions = (
        db.query(InventoryProduction)
        .filter(InventoryProduction.procedure_instance_id == instance_id)
        .all()
    )

    return [
        ProductionResponse(
            id=p.id,
            part_id=p.inventory_record.part_id,
            part_name=p.inventory_record.part.name,
            quantity=float(p.quantity),
            location=p.inventory_record.location,
            lot_number=p.inventory_record.lot_number,
            serial_number=p.serial_number,
        )
        for p in productions
    ]


# ============ BOM Reconciliation & Finalization ============


class BOMKitItem(BaseModel):
    """Kit vs actual consumption comparison."""

    part_id: int
    part_name: str
    qty_required: float
    qty_consumed: float
    variance: float


class BOMUnplannedItem(BaseModel):
    """Consumption not in the original kit."""

    part_id: int
    part_name: str
    qty_consumed: float


class BOMOutputItem(BaseModel):
    """Planned output status."""

    part_id: int
    part_name: str
    serial_number: str | None
    opal_number: str | None
    quantity: float
    status: str


class BOMReconciliationResponse(BaseModel):
    """BOM reconciliation comparison."""

    kit_items: list[BOMKitItem]
    unplanned_consumptions: list[BOMUnplannedItem]
    outputs: list[BOMOutputItem]


class FinalizeRequest(BaseModel):
    """Request to finalize production after execution."""

    location: str = Field(..., min_length=1, description="Where the produced assembly is stored")
    notes: str | None = None


@router.get("/{instance_id}/bom-reconciliation", response_model=BOMReconciliationResponse)
async def get_bom_reconciliation(
    instance_id: int,
    db: DbSession,
) -> BOMReconciliationResponse:
    """Get BOM reconciliation: kit (expected) vs actual consumptions."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    return _build_bom_reconciliation(db, instance)


def _build_bom_reconciliation(db, instance) -> BOMReconciliationResponse:
    """Build BOM reconciliation data for an instance."""
    # Get kit (expected) parts
    kit_items = db.query(Kit).filter(Kit.procedure_id == instance.procedure_id).all()
    kit_by_part: dict[int, float] = {k.part_id: float(k.quantity_required) for k in kit_items}
    kit_part_names: dict[int, str] = {k.part_id: k.part.name for k in kit_items}

    # Get actual consumptions (only CONSUME type, not tooling)
    consumptions = (
        db.query(InventoryConsumption)
        .filter(
            InventoryConsumption.procedure_instance_id == instance.id,
            InventoryConsumption.usage_type == UsageType.CONSUME,
        )
        .all()
    )

    # Aggregate consumed quantities by part
    consumed_by_part: dict[int, float] = {}
    consumed_part_names: dict[int, str] = {}
    for c in consumptions:
        pid = c.inventory_record.part_id
        consumed_by_part[pid] = consumed_by_part.get(pid, 0) + float(c.quantity)
        consumed_part_names[pid] = c.inventory_record.part.name

    # Build kit comparison
    bom_kit_items = []
    for part_id, qty_required in kit_by_part.items():
        qty_consumed = consumed_by_part.pop(part_id, 0)
        bom_kit_items.append(BOMKitItem(
            part_id=part_id,
            part_name=kit_part_names[part_id],
            qty_required=qty_required,
            qty_consumed=qty_consumed,
            variance=qty_consumed - qty_required,
        ))

    # Remaining consumed parts not in kit
    unplanned = [
        BOMUnplannedItem(
            part_id=pid,
            part_name=consumed_part_names.get(pid, "Unknown"),
            qty_consumed=qty,
        )
        for pid, qty in consumed_by_part.items()
    ]

    # Get production outputs
    productions = (
        db.query(InventoryProduction)
        .filter(InventoryProduction.procedure_instance_id == instance.id)
        .all()
    )
    outputs = []
    for p in productions:
        prod_status = p.status.value if hasattr(p.status, 'value') else p.status
        outputs.append(BOMOutputItem(
            part_id=p.inventory_record.part_id,
            part_name=p.inventory_record.part.name,
            serial_number=p.serial_number,
            opal_number=p.produced_opal_number,
            quantity=float(p.quantity),
            status=prod_status,
        ))

    return BOMReconciliationResponse(
        kit_items=bom_kit_items,
        unplanned_consumptions=unplanned,
        outputs=outputs,
    )


@router.post("/{instance_id}/finalize", status_code=200)
async def finalize_production(
    instance_id: int,
    data: FinalizeRequest,
    db: DbSession,
    user_id: CurrentUserId,
) -> dict:
    """Finalize production after execution is complete.

    Sets production records to COMPLETED, assigns quantity and location
    to inventory records, and records assembly genealogy.
    """
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    inst_status = instance.status.value if hasattr(instance.status, 'value') else instance.status
    if inst_status != InstanceStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Instance must be COMPLETED before finalizing production")

    # Get WIP production records for this instance
    productions = (
        db.query(InventoryProduction)
        .filter(
            InventoryProduction.procedure_instance_id == instance_id,
            InventoryProduction.status == ProductionStatus.WIP,
        )
        .all()
    )

    if not productions:
        raise HTTPException(status_code=400, detail="No WIP production records to finalize")

    # Get all CONSUME-type consumption records for genealogy
    consumption_ids = [
        c.id for c in
        db.query(InventoryConsumption).filter(
            InventoryConsumption.procedure_instance_id == instance_id,
            InventoryConsumption.usage_type == UsageType.CONSUME,
        ).all()
    ]

    finalized = []
    for production in productions:
        old_values = get_model_dict(production)

        production.status = ProductionStatus.COMPLETED

        # Update inventory record with actual quantity and location
        inv_record = production.inventory_record
        inv_record.quantity = production.quantity
        inv_record.location = data.location

        log_update(db, production, old_values, user_id)

        # Record assembly genealogy
        if consumption_ids:
            record_assembly_genealogy(db, production.id, consumption_ids)

        finalized.append({
            "production_id": production.id,
            "opal_number": production.produced_opal_number,
            "serial_number": production.serial_number,
            "part_name": inv_record.part.name,
            "quantity": float(production.quantity),
            "location": data.location,
        })

    db.commit()

    return {
        "status": "finalized",
        "instance_id": instance_id,
        "productions": finalized,
    }


# ============ Collaboration (Multi-user Execution) ============


class ParticipantInfo(BaseModel):
    """Participant in an execution."""

    user_id: int
    user_name: str
    joined_at: str
    last_step: int | None = None
    is_active: bool = True


class ParticipantsResponse(BaseModel):
    """Response for execution participants."""

    instance_id: int
    participants: list[ParticipantInfo]


@router.post("/{instance_id}/join", response_model=ParticipantsResponse)
async def join_execution(
    instance_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> ParticipantsResponse:
    """Join an execution as a participant.

    This allows multiple users to collaborate on the same procedure execution.
    """
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Get user info
    from opal.db.models import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Initialize participants if None
    participants = instance.participants or []

    # Check if already a participant
    existing = next((p for p in participants if p.get("user_id") == user_id), None)
    if existing:
        # Update last seen, already joined
        existing["last_active"] = datetime.now(timezone.utc).isoformat()
    else:
        # Add new participant
        participants.append({
            "user_id": user_id,
            "user_name": user.name,
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "last_step": None,
        })

    instance.participants = participants
    db.commit()
    db.refresh(instance)

    # Emit user joined event (only if newly joined)
    if not existing:
        await emit_user_joined(instance_id, user_id, user.name)

    return ParticipantsResponse(
        instance_id=instance.id,
        participants=[
            ParticipantInfo(
                user_id=p["user_id"],
                user_name=p.get("user_name", "Unknown"),
                joined_at=p["joined_at"],
                last_step=p.get("last_step"),
                is_active=True,
            )
            for p in (instance.participants or [])
        ],
    )


@router.post("/{instance_id}/leave")
async def leave_execution(
    instance_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> dict:
    """Leave an execution (stop participating)."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    participants = instance.participants or []

    # Find the leaving user's name before removing
    leaving_user = next((p for p in participants if p.get("user_id") == user_id), None)
    user_name = leaving_user.get("user_name", "Unknown") if leaving_user else "Unknown"

    # Remove user from participants
    instance.participants = [p for p in participants if p.get("user_id") != user_id]
    db.commit()

    # Emit user left event
    if leaving_user:
        await emit_user_left(instance_id, user_id, user_name)

    return {"status": "left", "instance_id": instance_id}


@router.get("/{instance_id}/participants", response_model=ParticipantsResponse)
async def get_participants(
    instance_id: int,
    db: DbSession,
) -> ParticipantsResponse:
    """Get current participants in an execution."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    return ParticipantsResponse(
        instance_id=instance.id,
        participants=[
            ParticipantInfo(
                user_id=p["user_id"],
                user_name=p.get("user_name", "Unknown"),
                joined_at=p["joined_at"],
                last_step=p.get("last_step"),
                is_active=True,
            )
            for p in (instance.participants or [])
        ],
    )

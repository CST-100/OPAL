"""Undo last action endpoint."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import inspect

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import get_model_dict, log_update
from opal.db.models.audit import AuditAction, AuditLog

router = APIRouter(prefix="/undo", tags=["undo"])

# Map table_name -> SQLAlchemy model class
_TABLE_MODEL_MAP: dict[str, type] = {}


def _get_model_map() -> dict[str, type]:
    """Lazily build the table-to-model mapping."""
    if _TABLE_MODEL_MAP:
        return _TABLE_MODEL_MAP

    from opal.db.models import (
        Attachment,
        Dataset,
        DataPoint,
        Issue,
        Kit,
        MasterProcedure,
        Part,
        ProcedureInstance,
        ProcedureStep,
        Purchase,
        PurchaseLine,
        Risk,
        StepExecution,
        Supplier,
        User,
        Workcenter,
    )
    from opal.db.models.inventory import InventoryRecord

    models = [
        Part, InventoryRecord, MasterProcedure, ProcedureStep,
        ProcedureInstance, StepExecution, Issue, Risk, Dataset,
        DataPoint, Purchase, PurchaseLine, Supplier, User,
        Workcenter, Kit, Attachment,
    ]
    for model in models:
        table_name = inspect(model).mapped_table.name
        _TABLE_MODEL_MAP[table_name] = model

    return _TABLE_MODEL_MAP


class UndoPreview(BaseModel):
    """Preview of what will be undone."""

    audit_id: int
    action: str
    table_name: str
    record_id: int
    summary: str
    timestamp: str
    can_undo: bool
    reason: str | None = None


class UndoResult(BaseModel):
    """Result of an undo operation."""

    success: bool
    summary: str


@router.get("/last", response_model=UndoPreview)
async def get_last_undoable(
    db: DbSession,
    user_id: CurrentUserId,
) -> UndoPreview:
    """Get the most recent undoable action for the current user."""
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    entry = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == user_id,
            AuditLog.timestamp >= one_hour_ago,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    if not entry:
        raise HTTPException(status_code=404, detail="No recent actions to undo")

    action = entry.action.value if hasattr(entry.action, "value") else entry.action
    table = entry.table_name
    record_id = entry.record_id

    # Check if undo is possible
    model_map = _get_model_map()
    can_undo = True
    reason = None

    if table not in model_map:
        can_undo = False
        reason = f"Unknown table: {table}"
    elif action == "create":
        model_cls = model_map[table]
        if not hasattr(model_cls, "deleted_at"):
            can_undo = False
            reason = f"Cannot undo creation of {table} (no soft-delete support)"
    elif action == "delete":
        if not entry.old_values:
            can_undo = False
            reason = "No old values recorded for restore"
    elif action == "update":
        if not entry.old_values:
            can_undo = False
            reason = "No old values recorded for revert"

    # Build summary
    summary = f"{action.upper()} {table} #{record_id}"
    if action == "update" and entry.old_values and entry.new_values:
        changed = [k for k in entry.new_values if k in (entry.old_values or {})]
        if changed:
            summary += f" (changed: {', '.join(changed[:5])})"

    return UndoPreview(
        audit_id=entry.id,
        action=action,
        table_name=table,
        record_id=record_id,
        summary=summary,
        timestamp=entry.timestamp.isoformat(),
        can_undo=can_undo,
        reason=reason,
    )


@router.post("/last", response_model=UndoResult)
async def undo_last(
    db: DbSession,
    user_id: CurrentUserId,
) -> UndoResult:
    """Execute undo of the most recent action."""
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    entry = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == user_id,
            AuditLog.timestamp >= one_hour_ago,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )

    if not entry:
        raise HTTPException(status_code=404, detail="No recent actions to undo")

    action = entry.action.value if hasattr(entry.action, "value") else entry.action
    table = entry.table_name
    record_id = entry.record_id

    model_map = _get_model_map()
    if table not in model_map:
        raise HTTPException(status_code=400, detail=f"Cannot undo: unknown table {table}")

    model_cls = model_map[table]

    if action == "create":
        # Undo create -> soft-delete the record
        if not hasattr(model_cls, "deleted_at"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot undo creation of {table} (no soft-delete support)",
            )
        record = db.query(model_cls).filter(model_cls.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"{table} #{record_id} not found")

        old_values = get_model_dict(record)
        record.soft_delete()
        db.flush()
        log_update(db, record, old_values, user_id)
        db.commit()

        return UndoResult(success=True, summary=f"Soft-deleted {table} #{record_id}")

    elif action == "update":
        # Undo update -> revert to old_values
        if not entry.old_values:
            raise HTTPException(status_code=400, detail="No old values to revert to")

        record = db.query(model_cls).filter(model_cls.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"{table} #{record_id} not found")

        # Safety: check record hasn't been modified since the audit entry
        if hasattr(record, "updated_at") and entry.timestamp:
            if record.updated_at > entry.timestamp:
                raise HTTPException(
                    status_code=409,
                    detail="Record has been modified since this action — cannot safely undo",
                )

        old_values = get_model_dict(record)

        # Apply old values back
        skip_fields = {"id", "created_at", "updated_at"}
        for field, value in entry.old_values.items():
            if field in skip_fields:
                continue
            if hasattr(record, field):
                setattr(record, field, value)

        db.flush()
        log_update(db, record, old_values, user_id)
        db.commit()

        reverted = [k for k in entry.old_values if k not in skip_fields]
        return UndoResult(
            success=True,
            summary=f"Reverted {table} #{record_id} ({', '.join(reverted[:5])})",
        )

    elif action == "delete":
        # Undo delete -> restore soft-deleted record
        if not hasattr(model_cls, "deleted_at"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot undo deletion of {table} (no soft-delete support)",
            )

        record = db.query(model_cls).filter(model_cls.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"{table} #{record_id} not found")

        if not record.is_deleted:
            raise HTTPException(status_code=400, detail=f"{table} #{record_id} is not deleted")

        old_values = get_model_dict(record)
        record.restore()
        db.flush()
        log_update(db, record, old_values, user_id)
        db.commit()

        return UndoResult(success=True, summary=f"Restored {table} #{record_id}")

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action type: {action}")

"""Reports API routes - CSV exports and analytics."""

import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from opal.api.deps import DbSession
from opal.db.models import InventoryRecord, Part
from opal.db.models.execution import InstanceStatus, ProcedureInstance, StepExecution
from opal.db.models.issue import Issue
from opal.db.models.risk import Risk

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportSummary(BaseModel):
    """Summary statistics for reports."""

    generated_at: datetime
    total_records: int
    filters_applied: dict[str, Any]


# ============ Parts Report ============


@router.get("/parts/csv")
async def export_parts_csv(
    db: DbSession,
    category: str | None = Query(None),
    low_stock: bool = Query(False, description="Only parts below minimum stock"),
) -> StreamingResponse:
    """Export parts inventory as CSV."""
    query = db.query(Part).filter(Part.deleted_at.is_(None))

    if category:
        query = query.filter(Part.category == category)

    parts = query.all()

    # Build CSV
    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "ID", "External PN", "Name", "Category", "Description",
        "Unit", "Total Quantity", "Locations"
    ])

    for part in parts:
        # Calculate total inventory
        total_qty = sum(float(inv.quantity) for inv in part.inventory_records)
        locations = ", ".join(set(inv.location for inv in part.inventory_records if inv.quantity > 0))

        # Low stock filter (skip if not low stock when filter is active)
        if low_stock and total_qty > 0:
            continue

        writer.writerow([
            part.id,
            part.external_pn or "",
            part.name,
            part.category or "",
            (part.description or "")[:100],
            part.unit_of_measure or "",
            total_qty,
            locations,
        ])

    output.seek(0)

    filename = f"parts_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ Inventory Report ============


@router.get("/inventory/csv")
async def export_inventory_csv(
    db: DbSession,
    location: str | None = Query(None),
) -> StreamingResponse:
    """Export inventory records as CSV."""
    query = db.query(InventoryRecord)

    if location:
        query = query.filter(InventoryRecord.location.ilike(f"%{location}%"))

    records = query.all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "External PN", "Part Name", "Quantity", "Location",
        "Lot Number", "Last Counted", "Last Updated"
    ])

    for inv in records:
        writer.writerow([
            inv.id,
            inv.part.external_pn if inv.part else "",
            inv.part.name if inv.part else "",
            float(inv.quantity),
            inv.location,
            inv.lot_number or "",
            inv.last_counted_at.isoformat() if inv.last_counted_at else "",
            inv.updated_at.isoformat() if inv.updated_at else "",
        ])

    output.seek(0)

    filename = f"inventory_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ Executions Report ============


@router.get("/executions/csv")
async def export_executions_csv(
    db: DbSession,
    status: str | None = Query(None),
    procedure_id: int | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
) -> StreamingResponse:
    """Export procedure executions as CSV."""
    query = db.query(ProcedureInstance)

    if status:
        query = query.filter(ProcedureInstance.status == status)
    if procedure_id:
        query = query.filter(ProcedureInstance.procedure_id == procedure_id)
    if from_date:
        query = query.filter(ProcedureInstance.created_at >= from_date)
    if to_date:
        query = query.filter(ProcedureInstance.created_at <= to_date)

    instances = query.order_by(ProcedureInstance.id.desc()).all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Procedure", "Version", "Work Order", "Status",
        "Created At", "Started At", "Completed At", "Duration (min)",
        "Steps Completed", "Total Steps", "Priority"
    ])

    for inst in instances:
        duration_min = None
        if inst.started_at and inst.completed_at:
            duration_min = round((inst.completed_at - inst.started_at).total_seconds() / 60, 1)

        completed_steps = sum(
            1 for s in inst.step_executions
            if (s.status.value if hasattr(s.status, 'value') else s.status) in ["completed", "skipped"]
        )
        total_steps = len(inst.step_executions)

        writer.writerow([
            inst.id,
            inst.procedure.name if inst.procedure else "",
            inst.version_id,
            inst.work_order_number or "",
            inst.status.value if hasattr(inst.status, 'value') else inst.status,
            inst.created_at.isoformat() if inst.created_at else "",
            inst.started_at.isoformat() if inst.started_at else "",
            inst.completed_at.isoformat() if inst.completed_at else "",
            duration_min or "",
            completed_steps,
            total_steps,
            inst.priority,
        ])

    output.seek(0)

    filename = f"executions_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ Issues Report ============


@router.get("/issues/csv")
async def export_issues_csv(
    db: DbSession,
    status: str | None = Query(None),
    issue_type: str | None = Query(None),
    priority: str | None = Query(None),
) -> StreamingResponse:
    """Export issues as CSV."""
    query = db.query(Issue).filter(Issue.deleted_at.is_(None))

    if status:
        query = query.filter(Issue.status == status)
    if issue_type:
        query = query.filter(Issue.issue_type == issue_type)
    if priority:
        query = query.filter(Issue.priority == priority)

    issues = query.order_by(Issue.id.desc()).all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Title", "Type", "Status", "Priority",
        "Description", "Linked Part", "Linked Procedure",
        "Created At", "Updated At"
    ])

    for issue in issues:
        writer.writerow([
            issue.id,
            issue.title,
            issue.issue_type.value if hasattr(issue.issue_type, 'value') else issue.issue_type,
            issue.status.value if hasattr(issue.status, 'value') else issue.status,
            issue.priority.value if hasattr(issue.priority, 'value') else issue.priority,
            (issue.description or "")[:200],
            issue.part_id or "",
            issue.procedure_id or "",
            issue.created_at.isoformat() if issue.created_at else "",
            issue.updated_at.isoformat() if issue.updated_at else "",
        ])

    output.seek(0)

    filename = f"issues_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ Risks Report ============


@router.get("/risks/csv")
async def export_risks_csv(
    db: DbSession,
    status: str | None = Query(None),
    min_score: int | None = Query(None, description="Minimum risk score"),
) -> StreamingResponse:
    """Export risks as CSV."""
    query = db.query(Risk).filter(Risk.deleted_at.is_(None))

    if status:
        query = query.filter(Risk.status == status)

    risks = query.order_by(Risk.id.desc()).all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Title", "Status", "Probability", "Impact", "Score", "Severity",
        "Description", "Mitigation Plan", "Created At"
    ])

    for risk in risks:
        if min_score and risk.score < min_score:
            continue

        writer.writerow([
            risk.id,
            risk.title,
            risk.status.value if hasattr(risk.status, 'value') else risk.status,
            risk.probability,
            risk.impact,
            risk.score,
            risk.severity,
            (risk.description or "")[:200],
            (risk.mitigation_plan or "")[:200],
            risk.created_at.isoformat() if risk.created_at else "",
        ])

    output.seek(0)

    filename = f"risks_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============ Analytics Endpoints ============


class ExecutionMetrics(BaseModel):
    """Execution performance metrics."""

    total_executions: int
    completed: int
    in_progress: int
    pending: int
    aborted: int
    avg_duration_minutes: float | None
    completion_rate: float


@router.get("/analytics/executions", response_model=ExecutionMetrics)
async def get_execution_metrics(
    db: DbSession,
    procedure_id: int | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
) -> ExecutionMetrics:
    """Get execution performance metrics."""
    query = db.query(ProcedureInstance)

    if procedure_id:
        query = query.filter(ProcedureInstance.procedure_id == procedure_id)
    if from_date:
        query = query.filter(ProcedureInstance.created_at >= from_date)
    if to_date:
        query = query.filter(ProcedureInstance.created_at <= to_date)

    instances = query.all()

    total = len(instances)
    completed = sum(1 for i in instances if _get_status(i) == "completed")
    in_progress = sum(1 for i in instances if _get_status(i) == "in_progress")
    pending = sum(1 for i in instances if _get_status(i) == "pending")
    aborted = sum(1 for i in instances if _get_status(i) == "aborted")

    # Calculate average duration for completed instances
    durations = []
    for inst in instances:
        if inst.started_at and inst.completed_at:
            durations.append((inst.completed_at - inst.started_at).total_seconds() / 60)

    avg_duration = sum(durations) / len(durations) if durations else None
    completion_rate = (completed / total * 100) if total > 0 else 0.0

    return ExecutionMetrics(
        total_executions=total,
        completed=completed,
        in_progress=in_progress,
        pending=pending,
        aborted=aborted,
        avg_duration_minutes=round(avg_duration, 1) if avg_duration else None,
        completion_rate=round(completion_rate, 1),
    )


class IssueMetrics(BaseModel):
    """Issue tracking metrics."""

    total_issues: int
    open: int
    in_progress: int
    resolved: int
    closed: int
    by_type: dict[str, int]
    by_priority: dict[str, int]


@router.get("/analytics/issues", response_model=IssueMetrics)
async def get_issue_metrics(
    db: DbSession,
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
) -> IssueMetrics:
    """Get issue tracking metrics."""
    query = db.query(Issue).filter(Issue.deleted_at.is_(None))

    if from_date:
        query = query.filter(Issue.created_at >= from_date)
    if to_date:
        query = query.filter(Issue.created_at <= to_date)

    issues = query.all()

    total = len(issues)
    open_count = sum(1 for i in issues if _get_issue_status(i) == "open")
    in_progress = sum(1 for i in issues if _get_issue_status(i) == "in_progress")
    resolved = sum(1 for i in issues if _get_issue_status(i) == "resolved")
    closed = sum(1 for i in issues if _get_issue_status(i) == "closed")

    by_type: dict[str, int] = {}
    by_priority: dict[str, int] = {}

    for issue in issues:
        issue_type = issue.issue_type.value if hasattr(issue.issue_type, 'value') else issue.issue_type
        priority = issue.priority.value if hasattr(issue.priority, 'value') else issue.priority

        by_type[issue_type] = by_type.get(issue_type, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1

    return IssueMetrics(
        total_issues=total,
        open=open_count,
        in_progress=in_progress,
        resolved=resolved,
        closed=closed,
        by_type=by_type,
        by_priority=by_priority,
    )


def _get_status(instance: ProcedureInstance) -> str:
    """Get status as string."""
    status = instance.status
    return status.value if hasattr(status, 'value') else status


def _get_issue_status(issue: Issue) -> str:
    """Get issue status as string."""
    status = issue.status
    return status.value if hasattr(status, 'value') else status

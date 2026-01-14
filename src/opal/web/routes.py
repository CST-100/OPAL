"""Web UI routes."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_

from opal.api.deps import DbSession
from opal.db.models import InventoryRecord, Kit, Part, Purchase, Supplier, User, Workcenter
from opal.db.models.dataset import Dataset, DataPoint
from opal.db.models.execution import InstanceStatus, ProcedureInstance, StepStatus
from opal.db.models.issue import Issue, IssuePriority, IssueStatus, IssueType
from opal.db.models.procedure import MasterProcedure, ProcedureStatus, ProcedureVersion
from opal.db.models.purchase import PurchaseStatus
from opal.db.models.risk import Risk, RiskStatus
from opal.project import DEFAULT_TIERS

# Template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def status_value(status) -> str:
    """Get string value from status (handles both enum and string)."""
    if hasattr(status, "value"):
        return status.value
    return str(status) if status else ""


# Register custom filter
templates.env.filters["status_value"] = status_value

router = APIRouter()


def get_base_context(request: Request, db: DbSession, title: str) -> dict[str, Any]:
    """Get base context for all pages."""
    from opal import __version__
    from opal.config import get_active_project

    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    project = get_active_project()
    return {
        "request": request,
        "users": users,
        "title": title,
        "project_name": project.name if project else None,
        "opal_version": __version__,
        "app_version": f"v{__version__}",
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: DbSession) -> HTMLResponse:
    """Home page."""
    from opal.db.models.audit import AuditLog

    context = get_base_context(request, db, "OPAL")

    # Get counts for dashboard
    context["parts_count"] = db.query(Part).filter(Part.deleted_at.is_(None)).count()
    context["procedures_count"] = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None)).count()
    context["open_issues_count"] = db.query(Issue).filter(
        Issue.deleted_at.is_(None),
        Issue.status.in_(["open", "in_progress"])
    ).count()
    context["in_progress_count"] = db.query(ProcedureInstance).filter(
        ProcedureInstance.status == "in_progress"
    ).count()
    context["risks_count"] = db.query(Risk).filter(
        Risk.deleted_at.is_(None),
        Risk.status != "closed"
    ).count()
    context["high_risks_count"] = len([
        r for r in db.query(Risk).filter(Risk.deleted_at.is_(None), Risk.status != "closed").all()
        if r.severity == "high"
    ])

    # Get recent audit activity
    recent_activity = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(10)
        .all()
    )
    context["recent_activity"] = recent_activity

    return templates.TemplateResponse("index.html", context)


# ============ PARTS ============

@router.get("/parts", response_class=HTMLResponse)
async def parts_list(request: Request, db: DbSession) -> HTMLResponse:
    """Parts list page."""
    context = get_base_context(request, db, "Parts - OPAL")

    # Get categories for filter dropdown
    categories = (
        db.query(Part.category)
        .filter(Part.deleted_at.is_(None), Part.category.isnot(None))
        .distinct()
        .all()
    )
    context["categories"] = sorted([c[0] for c in categories if c[0]])

    return templates.TemplateResponse("parts/list.html", context)


@router.get("/parts/table", response_class=HTMLResponse)
async def parts_table(
    request: Request,
    db: DbSession,
    search: str | None = Query(None),
    category: str | None = Query(None),
) -> HTMLResponse:
    """Parts table rows (HTMX partial)."""
    query = db.query(Part).filter(Part.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Part.name.ilike(search_term),
                Part.external_pn.ilike(search_term),
                Part.description.ilike(search_term),
            )
        )

    if category:
        query = query.filter(Part.category == category)

    parts = query.order_by(Part.id.desc()).limit(100).all()

    # Calculate total quantities and attach to part-like objects
    parts_with_qty = []
    for part in parts:
        total_qty = (
            db.query(func.coalesce(func.sum(InventoryRecord.quantity), 0))
            .filter(InventoryRecord.part_id == part.id)
            .scalar()
        )
        # Create a dict with all part attributes plus total_quantity
        part_data = {
            "id": part.id,
            "internal_pn": part.internal_pn,
            "external_pn": part.external_pn,
            "name": part.name,
            "category": part.category,
            "tier": part.tier,
            "unit_of_measure": part.unit_of_measure,
            "total_quantity": total_qty or 0,
        }
        parts_with_qty.append(type("PartWithQty", (), part_data)())

    return templates.TemplateResponse(
        "parts/table_rows.html",
        {"request": request, "parts": parts_with_qty},
    )


@router.get("/parts/search", response_class=HTMLResponse)
async def parts_search_dropdown(
    request: Request,
    db: DbSession,
    q: str = Query("", min_length=0),
    limit: int = Query(5, ge=1, le=10),
) -> HTMLResponse:
    """Search parts and return dropdown results (HTMX partial)."""
    if not q or len(q) < 1:
        return HTMLResponse("")

    search_term = f"%{q}%"
    parts = (
        db.query(Part)
        .filter(
            Part.deleted_at.is_(None),
            or_(
                Part.name.ilike(search_term),
                Part.internal_pn.ilike(search_term),
                Part.external_pn.ilike(search_term),
            ),
        )
        .order_by(Part.id.desc())
        .limit(limit)
        .all()
    )

    return templates.TemplateResponse(
        "components/part_search_results.html",
        {"request": request, "parts": parts, "query": q},
    )


@router.get("/parts/new", response_class=HTMLResponse)
async def parts_new(request: Request, db: DbSession) -> HTMLResponse:
    """New part form page."""
    from opal.config import get_active_project
    from opal.project import DEFAULT_TIERS

    context = get_base_context(request, db, "New Part - OPAL")

    # Get categories for dropdown
    categories = (
        db.query(Part.category)
        .filter(Part.deleted_at.is_(None), Part.category.isnot(None))
        .distinct()
        .all()
    )
    context["categories"] = sorted([c[0] for c in categories if c[0]])

    # Get tiers from project config or use defaults
    project = get_active_project()
    if project:
        context["tiers"] = project.tiers
    else:
        context["tiers"] = DEFAULT_TIERS

    # Get existing parts for parent selector
    assemblies = (
        db.query(Part)
        .filter(Part.deleted_at.is_(None))
        .order_by(Part.name)
        .all()
    )
    context["assemblies"] = assemblies

    return templates.TemplateResponse("parts/new.html", context)


@router.get("/parts/{part_id}", response_class=HTMLResponse)
async def parts_detail(request: Request, db: DbSession, part_id: int) -> HTMLResponse:
    """Part detail page."""
    from opal.config import get_active_project

    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Part {part_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Part {part_id} - OPAL")
    context["part"] = part

    # Get tier name from project config
    project = get_active_project()
    tier_name = None
    if project:
        tier_config = project.get_tier(part.tier)
        if tier_config:
            tier_name = tier_config.name
    context["tier_name"] = tier_name

    # Get inventory records
    inventory = db.query(InventoryRecord).filter(InventoryRecord.part_id == part_id).all()
    context["inventory"] = inventory
    context["total_qty"] = sum(r.quantity for r in inventory)

    return templates.TemplateResponse("parts/detail.html", context)


@router.get("/parts/{part_id}/edit", response_class=HTMLResponse)
async def parts_edit(request: Request, db: DbSession, part_id: int) -> HTMLResponse:
    """Part edit form page."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Part {part_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Edit Part {part_id} - OPAL")
    context["part"] = part

    # Get categories for dropdown
    categories = (
        db.query(Part.category)
        .filter(Part.deleted_at.is_(None), Part.category.isnot(None))
        .distinct()
        .all()
    )
    context["categories"] = sorted([c[0] for c in categories if c[0]])

    return templates.TemplateResponse("parts/edit.html", context)


# ============ INVENTORY ============

@router.get("/inventory", response_class=HTMLResponse)
async def inventory_list(request: Request, db: DbSession) -> HTMLResponse:
    """Inventory list page."""
    context = get_base_context(request, db, "Inventory - OPAL")

    # Get locations for filter
    locations = db.query(InventoryRecord.location).distinct().all()
    context["locations"] = sorted([l[0] for l in locations])

    return templates.TemplateResponse("inventory/list.html", context)


@router.get("/inventory/table", response_class=HTMLResponse)
async def inventory_table(
    request: Request,
    db: DbSession,
    location: str | None = Query(None),
    part_id: int | None = Query(None),
    opal_search: str | None = Query(None),
    source_type: str | None = Query(None),
) -> HTMLResponse:
    """Inventory table rows (HTMX partial)."""
    query = db.query(InventoryRecord).join(Part).filter(Part.deleted_at.is_(None))

    if location:
        query = query.filter(InventoryRecord.location == location)
    if part_id:
        query = query.filter(InventoryRecord.part_id == part_id)
    if opal_search:
        query = query.filter(InventoryRecord.opal_number.ilike(f"%{opal_search}%"))
    if source_type:
        query = query.filter(InventoryRecord.source_type == source_type)

    # Order by OPAL number (most recent first)
    records = query.order_by(InventoryRecord.opal_number.desc()).limit(100).all()

    return templates.TemplateResponse(
        "inventory/table_rows.html",
        {"request": request, "records": records},
    )


@router.get("/inventory/opal/{opal_number}", response_class=HTMLResponse)
async def inventory_opal_detail(
    request: Request,
    db: DbSession,
    opal_number: str,
) -> HTMLResponse:
    """OPAL item detail page with full traceability history."""
    from opal.db.models.inventory import InventoryConsumption, InventoryProduction
    from opal.db.models.purchase import PurchaseLine

    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(InventoryRecord.opal_number == opal_number, Part.deleted_at.is_(None))
        .first()
    )

    if not record:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"OPAL {opal_number} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"{opal_number} - OPAL")
    context["record"] = record
    context["opal_number"] = opal_number

    # Build history timeline
    history = []

    # Creation event
    source_info = {}
    if record.source_purchase_line_id:
        po_line = db.query(PurchaseLine).filter(PurchaseLine.id == record.source_purchase_line_id).first()
        if po_line:
            source_info = {
                "po_id": po_line.purchase_id,
                "po_number": po_line.purchase.po_number if po_line.purchase else None,
            }

    history.append({
        "event": "created",
        "timestamp": record.created_at,
        "details": {
            "source_type": record.source_type.value if record.source_type and hasattr(record.source_type, 'value') else record.source_type,
            "quantity": float(record.quantity),
            **source_info,
        },
    })

    # Consumptions
    for c in record.consumptions:
        history.append({
            "event": "consumed",
            "timestamp": c.created_at,
            "details": {
                "quantity": float(c.quantity),
                "usage_type": c.usage_type.value if hasattr(c.usage_type, 'value') else c.usage_type,
                "procedure_instance_id": c.procedure_instance_id,
            },
        })

    # Sort by timestamp
    history.sort(key=lambda h: h["timestamp"], reverse=True)
    context["history"] = history

    return templates.TemplateResponse("inventory/opal_detail.html", context)


# ============ PURCHASES ============

@router.get("/purchases", response_class=HTMLResponse)
async def purchases_list(request: Request, db: DbSession) -> HTMLResponse:
    """Purchases list page."""
    context = get_base_context(request, db, "Purchases - OPAL")
    context["statuses"] = [s.value for s in PurchaseStatus]
    return templates.TemplateResponse("purchases/list.html", context)


@router.get("/purchases/table", response_class=HTMLResponse)
async def purchases_table(
    request: Request,
    db: DbSession,
    status: str | None = Query(None),
) -> HTMLResponse:
    """Purchases table rows (HTMX partial)."""
    query = db.query(Purchase)

    if status:
        query = query.filter(Purchase.status == status)

    purchases = query.order_by(Purchase.id.desc()).limit(100).all()

    return templates.TemplateResponse(
        "purchases/table_rows.html",
        {"request": request, "purchases": purchases},
    )


@router.get("/purchases/new", response_class=HTMLResponse)
async def purchases_new(
    request: Request,
    db: DbSession,
    supplier_id: int | None = None,
) -> HTMLResponse:
    """New purchase form page."""
    context = get_base_context(request, db, "New Purchase - OPAL")

    # Get parts for line items - convert to dicts for JSON serialization
    parts = db.query(Part).filter(Part.deleted_at.is_(None)).order_by(Part.name).all()
    context["parts"] = [
        {"id": p.id, "name": p.name, "external_pn": p.external_pn}
        for p in parts
    ]

    # Get suppliers for dropdown - convert to dicts for JSON serialization
    suppliers = db.query(Supplier).filter(
        Supplier.deleted_at.is_(None),
        Supplier.is_active == True  # noqa: E712
    ).order_by(Supplier.name).all()
    context["suppliers"] = [
        {"id": s.id, "name": s.name, "code": s.code}
        for s in suppliers
    ]
    context["preselected_supplier_id"] = supplier_id

    return templates.TemplateResponse("purchases/new.html", context)


@router.get("/purchases/{purchase_id}", response_class=HTMLResponse)
async def purchases_detail(request: Request, db: DbSession, purchase_id: int) -> HTMLResponse:
    """Purchase detail page."""
    purchase = db.query(Purchase).filter(Purchase.id == purchase_id).first()
    if not purchase:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Purchase {purchase_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"PO-{purchase_id} - OPAL")
    context["purchase"] = purchase
    context["statuses"] = [s.value for s in PurchaseStatus]

    # Get parts for adding new lines - convert to dicts for JSON serialization in modal
    parts = db.query(Part).filter(Part.deleted_at.is_(None)).order_by(Part.name).all()
    context["parts"] = parts  # Keep full objects for template rendering
    context["parts_json"] = [
        {"id": p.id, "name": p.name, "external_pn": p.external_pn}
        for p in parts
    ]

    return templates.TemplateResponse("purchases/detail.html", context)


# ============ PROCEDURES ============

@router.get("/procedures", response_class=HTMLResponse)
async def procedures_list(request: Request, db: DbSession) -> HTMLResponse:
    """Procedures list page."""
    context = get_base_context(request, db, "Procedures - OPAL")
    context["statuses"] = [s.value for s in ProcedureStatus]
    return templates.TemplateResponse("procedures/list.html", context)


@router.get("/procedures/table", response_class=HTMLResponse)
async def procedures_table(
    request: Request,
    db: DbSession,
    search: str | None = Query(None),
    status: str | None = Query(None),
) -> HTMLResponse:
    """Procedures table rows (HTMX partial)."""
    query = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(MasterProcedure.name.ilike(search_term))

    if status:
        query = query.filter(MasterProcedure.status == status)

    procedures = query.order_by(MasterProcedure.id.desc()).limit(100).all()

    # Add version number and step count
    procs_with_info = []
    for p in procedures:
        version_number = None
        if p.current_version_id:
            version = db.query(ProcedureVersion).filter(ProcedureVersion.id == p.current_version_id).first()
            if version:
                version_number = version.version_number
        # Handle status - may be enum or string depending on context
        status_val = p.status.value if hasattr(p.status, 'value') else p.status
        procs_with_info.append({
            "id": p.id,
            "name": p.name,
            "status": status_val,
            "current_version_id": p.current_version_id,
            "version_number": version_number,
            "step_count": len(p.steps),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        })

    return templates.TemplateResponse(
        "procedures/table_rows.html",
        {"request": request, "procedures": procs_with_info},
    )


@router.get("/procedures/new", response_class=HTMLResponse)
async def procedures_new(request: Request, db: DbSession) -> HTMLResponse:
    """New procedure form page."""
    context = get_base_context(request, db, "New Procedure - OPAL")
    return templates.TemplateResponse("procedures/new.html", context)


@router.get("/procedures/{procedure_id}", response_class=HTMLResponse)
async def procedures_detail(request: Request, db: DbSession, procedure_id: int) -> HTMLResponse:
    """Procedure detail page."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Procedure {procedure_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"{procedure.name} - OPAL")
    context["procedure"] = procedure
    context["statuses"] = [s.value for s in ProcedureStatus]

    # Get versions
    versions = (
        db.query(ProcedureVersion)
        .filter(ProcedureVersion.procedure_id == procedure_id)
        .order_by(ProcedureVersion.version_number.desc())
        .all()
    )
    context["versions"] = versions

    # Get current version number
    current_version_num = None
    if procedure.current_version_id:
        current_ver = db.query(ProcedureVersion).filter(ProcedureVersion.id == procedure.current_version_id).first()
        if current_ver:
            current_version_num = current_ver.version_number
    context["current_version_num"] = current_version_num

    # Get kit items
    kit_items = (
        db.query(Kit)
        .join(Part)
        .filter(Kit.procedure_id == procedure_id)
        .order_by(Part.name)
        .all()
    )
    context["kit_items"] = [
        {
            "id": k.id,
            "part_id": k.part_id,
            "part_name": k.part.name,
            "part_external_pn": k.part.external_pn,
            "quantity_required": float(k.quantity_required),
        }
        for k in kit_items
    ]

    # Get parts for kit modal
    parts = db.query(Part).filter(Part.deleted_at.is_(None)).order_by(Part.name).all()
    context["parts"] = parts

    # Organize steps hierarchically
    all_steps = procedure.steps
    ops = []  # Top-level normal ops
    contingency_ops = []  # Top-level contingency ops

    # Build step lookup for sub-steps
    step_children: dict[int, list] = {}
    for step in all_steps:
        if step.parent_step_id:
            if step.parent_step_id not in step_children:
                step_children[step.parent_step_id] = []
            step_children[step.parent_step_id].append(step)

    # Separate top-level ops
    for step in all_steps:
        if step.parent_step_id is None:
            step_data = {
                "step": step,
                "sub_steps": sorted(step_children.get(step.id, []), key=lambda s: s.order),
            }
            if step.is_contingency:
                contingency_ops.append(step_data)
            else:
                ops.append(step_data)

    # Sort ops by step_number
    ops.sort(key=lambda x: int(x["step"].step_number) if x["step"].step_number.isdigit() else 0)
    contingency_ops.sort(key=lambda x: x["step"].step_number)

    context["ops"] = ops
    context["contingency_ops"] = contingency_ops

    return templates.TemplateResponse("procedures/detail.html", context)


@router.get("/procedures/{procedure_id}/edit", response_class=HTMLResponse)
async def procedures_edit(request: Request, db: DbSession, procedure_id: int) -> HTMLResponse:
    """Procedure edit form page."""
    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Procedure {procedure_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Edit {procedure.name} - OPAL")
    context["procedure"] = procedure
    return templates.TemplateResponse("procedures/edit.html", context)


@router.get("/procedures/{procedure_id}/steps/{step_id}/edit", response_class=HTMLResponse)
async def procedures_step_edit(
    request: Request, db: DbSession, procedure_id: int, step_id: int
) -> HTMLResponse:
    """Edit a procedure step."""
    from opal.db.models.procedure import ProcedureStep

    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == procedure_id, MasterProcedure.deleted_at.is_(None))
        .first()
    )
    if not procedure:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Procedure {procedure_id} not found"},
            status_code=404,
        )

    step = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.id == step_id, ProcedureStep.procedure_id == procedure_id)
        .first()
    )
    if not step:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Step {step_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Edit Step - {procedure.name} - OPAL")
    context["procedure"] = procedure
    context["step"] = step

    # Get step kit items
    from opal.db.models.procedure import StepKit
    step_kit_items = db.query(StepKit).filter(StepKit.step_id == step_id).all()
    context["step_kit"] = [
        {
            "id": sk.id,
            "part_id": sk.part_id,
            "part_name": sk.part.name,
            "quantity_required": float(sk.quantity_required),
            "usage_type": sk.usage_type.value if hasattr(sk.usage_type, "value") else sk.usage_type,
            "notes": sk.notes,
        }
        for sk in step_kit_items
    ]

    # Get parts for dropdown
    parts = db.query(Part).filter(Part.deleted_at.is_(None)).order_by(Part.name).all()
    context["parts"] = parts

    return templates.TemplateResponse("procedures/step_edit.html", context)


@router.get("/procedures/versions/{version_id}", response_class=HTMLResponse)
async def procedures_version_detail(request: Request, db: DbSession, version_id: int) -> HTMLResponse:
    """View a specific procedure version."""
    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == version_id).first()
    if not version:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Version {version_id} not found"},
            status_code=404,
        )

    procedure = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.id == version.procedure_id)
        .first()
    )

    context = get_base_context(request, db, f"v{version.version_number} - {procedure.name} - OPAL")
    context["version"] = version
    context["procedure"] = procedure
    return templates.TemplateResponse("procedures/version_detail.html", context)


# ============ EXECUTION ============

@router.get("/executions", response_class=HTMLResponse)
async def executions_list(request: Request, db: DbSession) -> HTMLResponse:
    """Procedure executions list page."""
    context = get_base_context(request, db, "Executions - OPAL")
    context["statuses"] = [s.value for s in InstanceStatus]

    # Get procedures for filter
    procedures = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.deleted_at.is_(None))
        .order_by(MasterProcedure.name)
        .all()
    )
    context["procedures"] = procedures

    return templates.TemplateResponse("executions/list.html", context)


@router.get("/executions/table", response_class=HTMLResponse)
async def executions_table(
    request: Request,
    db: DbSession,
    procedure_id: int | None = Query(None),
    status: str | None = Query(None),
) -> HTMLResponse:
    """Executions table rows (HTMX partial)."""
    query = db.query(ProcedureInstance)

    if procedure_id:
        query = query.filter(ProcedureInstance.procedure_id == procedure_id)
    if status:
        query = query.filter(ProcedureInstance.status == status)

    instances = query.order_by(ProcedureInstance.id.desc()).limit(100).all()

    # Build response data
    instances_data = []
    for inst in instances:
        version = db.query(ProcedureVersion).filter(ProcedureVersion.id == inst.version_id).first()
        status_val = inst.status.value if hasattr(inst.status, 'value') else inst.status
        completed_steps = sum(
            1 for se in inst.step_executions
            if (se.status.value if hasattr(se.status, 'value') else se.status) == 'completed'
        )
        instances_data.append({
            "id": inst.id,
            "procedure_name": inst.procedure.name,
            "version_number": version.version_number if version else 0,
            "work_order": inst.work_order_number or "-",
            "status": status_val,
            "completed_steps": completed_steps,
            "total_steps": len(inst.step_executions),
            "started_at": inst.started_at,
            "created_at": inst.created_at,
        })

    return templates.TemplateResponse(
        "executions/table_rows.html",
        {"request": request, "instances": instances_data},
    )


@router.get("/executions/new", response_class=HTMLResponse)
async def executions_new(request: Request, db: DbSession) -> HTMLResponse:
    """Start new execution page."""
    context = get_base_context(request, db, "New Execution - OPAL")

    # Get active procedures with published versions
    procedures = (
        db.query(MasterProcedure)
        .filter(
            MasterProcedure.deleted_at.is_(None),
            MasterProcedure.current_version_id.isnot(None),
        )
        .order_by(MasterProcedure.name)
        .all()
    )
    context["procedures"] = [
        {"id": p.id, "name": p.name, "current_version_id": p.current_version_id}
        for p in procedures
    ]

    return templates.TemplateResponse("executions/new.html", context)


@router.get("/executions/{instance_id}", response_class=HTMLResponse)
async def executions_detail(request: Request, db: DbSession, instance_id: int) -> HTMLResponse:
    """Execution detail/run page."""
    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Execution {instance_id} not found"},
            status_code=404,
        )

    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == instance.version_id).first()

    context = get_base_context(request, db, f"Execution {instance_id} - OPAL")
    context["instance"] = instance
    context["version"] = version
    context["statuses"] = [s.value for s in InstanceStatus]

    # Build steps with execution status and organize hierarchically
    version_steps = version.content.get("steps", []) if version else []

    # Create a lookup for step executions by step order
    exec_lookup = {se.step_number: se for se in instance.step_executions}

    # Build step data with execution info
    def build_step_data(vs):
        step_exec = exec_lookup.get(vs["order"])
        return {
            "order": vs["order"],
            "step_number": vs.get("step_number", str(vs["order"])),
            "level": vs.get("level", 0),
            "parent_step_id": vs.get("parent_step_id"),
            "id": vs.get("id"),  # For linking sub-steps to parents
            "title": vs["title"],
            "instructions": vs.get("instructions"),
            "is_contingency": vs.get("is_contingency", False),
            "required_data_schema": vs.get("required_data_schema"),
            "execution": step_exec,
            "status": (step_exec.status.value if step_exec and hasattr(step_exec.status, 'value')
                       else (step_exec.status if step_exec else 'pending')),
        }

    all_steps = [build_step_data(vs) for vs in version_steps]
    context["steps"] = all_steps  # Flat list for backward compatibility

    # Organize into ops and sub-steps hierarchy
    ops = []  # Normal ops
    contingency_ops = []  # Contingency ops

    # Build lookup by step ID
    step_by_id: dict[int, dict] = {s["id"]: s for s in all_steps if s.get("id")}

    # Group sub-steps by parent
    children_map: dict[int, list] = {}
    for step in all_steps:
        parent_id = step.get("parent_step_id")
        if parent_id:
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(step)

    # Build hierarchical structure
    for step in all_steps:
        if step.get("parent_step_id") is None:  # Top-level op
            sub_steps = sorted(children_map.get(step.get("id"), []), key=lambda s: s["order"])
            # Calculate progress for this op
            total = len(sub_steps) if sub_steps else 1
            completed = sum(1 for s in sub_steps if s["status"] in ["completed", "skipped"]) if sub_steps else (1 if step["status"] in ["completed", "skipped"] else 0)
            op_data = {
                "step": step,
                "sub_steps": sub_steps,
                "total_steps": total,
                "completed_steps": completed,
            }
            if step["is_contingency"]:
                contingency_ops.append(op_data)
            else:
                ops.append(op_data)

    # Sort ops
    def sort_key_normal(x):
        sn = x["step"].get("step_number", "0")
        return int(sn) if sn.isdigit() else 0
    def sort_key_contingency(x):
        return x["step"].get("step_number", "C0")

    ops.sort(key=sort_key_normal)
    contingency_ops.sort(key=sort_key_contingency)

    context["ops"] = ops
    context["contingency_ops"] = contingency_ops

    # Get kit information
    kit_items = db.query(Kit).filter(Kit.procedure_id == instance.procedure_id).all()
    context["kit_items"] = kit_items

    # Get existing consumptions
    from opal.db.models.inventory import InventoryConsumption, InventoryProduction
    from opal.db.models.procedure import ProcedureOutput
    consumptions = (
        db.query(InventoryConsumption)
        .filter(InventoryConsumption.procedure_instance_id == instance_id)
        .all()
    )
    context["consumptions"] = consumptions

    # Get outputs (what this procedure produces)
    output_items = db.query(ProcedureOutput).filter(ProcedureOutput.procedure_id == instance.procedure_id).all()
    context["output_items"] = output_items

    # Get existing productions
    productions = (
        db.query(InventoryProduction)
        .filter(InventoryProduction.procedure_instance_id == instance_id)
        .all()
    )
    context["productions"] = productions

    return templates.TemplateResponse("executions/detail.html", context)


# ============ ISSUES ============

@router.get("/issues", response_class=HTMLResponse)
async def issues_list(request: Request, db: DbSession) -> HTMLResponse:
    """Issues list page."""
    context = get_base_context(request, db, "Issues - OPAL")
    context["types"] = [t.value for t in IssueType]
    context["statuses"] = [s.value for s in IssueStatus]
    context["priorities"] = [p.value for p in IssuePriority]
    return templates.TemplateResponse("issues/list.html", context)


@router.get("/issues/table", response_class=HTMLResponse)
async def issues_table(
    request: Request,
    db: DbSession,
    search: str | None = Query(None),
    issue_type: str | None = Query(None),
    status: str | None = Query(None),
    priority: str | None = Query(None),
) -> HTMLResponse:
    """Issues table rows (HTMX partial)."""
    query = db.query(Issue).filter(Issue.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(Issue.title.ilike(search_term))
    if issue_type:
        query = query.filter(Issue.issue_type == issue_type)
    if status:
        query = query.filter(Issue.status == status)
    if priority:
        query = query.filter(Issue.priority == priority)

    issues = query.order_by(Issue.id.desc()).limit(100).all()

    def get_val(obj, attr):
        val = getattr(obj, attr)
        return val.value if hasattr(val, 'value') else val

    issues_data = [
        {
            "id": i.id,
            "title": i.title,
            "issue_type": get_val(i, 'issue_type'),
            "status": get_val(i, 'status'),
            "priority": get_val(i, 'priority'),
            "created_at": i.created_at,
            "procedure_id": i.procedure_id,
            "procedure_instance_id": i.procedure_instance_id,
        }
        for i in issues
    ]

    return templates.TemplateResponse(
        "issues/table_rows.html",
        {"request": request, "issues": issues_data},
    )


@router.get("/issues/new", response_class=HTMLResponse)
async def issues_new(request: Request, db: DbSession) -> HTMLResponse:
    """New issue form page."""
    context = get_base_context(request, db, "New Issue - OPAL")
    context["types"] = [t.value for t in IssueType]
    context["priorities"] = [p.value for p in IssuePriority]

    # Get parts and procedures for linking
    parts = db.query(Part).filter(Part.deleted_at.is_(None)).order_by(Part.name).all()
    procedures = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None)).order_by(MasterProcedure.name).all()
    context["parts"] = parts
    context["procedures"] = procedures

    return templates.TemplateResponse("issues/new.html", context)


@router.get("/issues/{issue_id}", response_class=HTMLResponse)
async def issues_detail(request: Request, db: DbSession, issue_id: int) -> HTMLResponse:
    """Issue detail page."""
    issue = db.query(Issue).filter(Issue.id == issue_id, Issue.deleted_at.is_(None)).first()
    if not issue:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Issue {issue_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Issue {issue_id} - OPAL")
    context["issue"] = issue
    context["types"] = [t.value for t in IssueType]
    context["statuses"] = [s.value for s in IssueStatus]
    context["priorities"] = [p.value for p in IssuePriority]

    return templates.TemplateResponse("issues/detail.html", context)


# ============ RISKS ============

@router.get("/risks", response_class=HTMLResponse)
async def risks_list(request: Request, db: DbSession) -> HTMLResponse:
    """Risks list page."""
    context = get_base_context(request, db, "Risks - OPAL")
    context["statuses"] = [s.value for s in RiskStatus]
    return templates.TemplateResponse("risks/list.html", context)


@router.get("/risks/table", response_class=HTMLResponse)
async def risks_table(
    request: Request,
    db: DbSession,
    search: str | None = Query(None),
    status: str | None = Query(None),
    severity: str | None = Query(None),
) -> HTMLResponse:
    """Risks table rows (HTMX partial)."""
    query = db.query(Risk).filter(Risk.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(Risk.title.ilike(search_term))
    if status:
        query = query.filter(Risk.status == status)

    risks = query.order_by(Risk.id.desc()).limit(100).all()

    # Filter by severity in Python (computed property)
    if severity:
        risks = [r for r in risks if r.severity == severity]

    return templates.TemplateResponse(
        "risks/table_rows.html",
        {"request": request, "risks": risks},
    )


@router.get("/risks/matrix", response_class=HTMLResponse)
async def risks_matrix(request: Request, db: DbSession) -> HTMLResponse:
    """Risk matrix page."""
    import json

    context = get_base_context(request, db, "Risk Matrix - OPAL")

    # Get active risks
    risks = (
        db.query(Risk)
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.status != RiskStatus.CLOSED)
        .all()
    )

    # Build 5x5 matrix
    matrix = [[0 for _ in range(5)] for _ in range(5)]
    for risk in risks:
        prob_idx = risk.probability - 1
        impact_idx = risk.impact - 1
        matrix[prob_idx][impact_idx] += 1

    context["matrix"] = matrix
    context["total_risks"] = len(risks)
    context["high_count"] = sum(1 for r in risks if r.severity == "high")
    context["medium_count"] = sum(1 for r in risks if r.severity == "medium")
    context["low_count"] = sum(1 for r in risks if r.severity == "low")

    # Convert risks to JSON for filtering
    context["risks_json"] = json.dumps([
        {"id": r.id, "title": r.title, "probability": r.probability, "impact": r.impact}
        for r in risks
    ])

    return templates.TemplateResponse("risks/matrix.html", context)


@router.get("/risks/new", response_class=HTMLResponse)
async def risks_new(request: Request, db: DbSession) -> HTMLResponse:
    """New risk form page."""
    context = get_base_context(request, db, "New Risk - OPAL")

    # Get issues for linking
    issues = db.query(Issue).filter(Issue.deleted_at.is_(None)).order_by(Issue.id.desc()).limit(100).all()
    context["issues"] = issues

    return templates.TemplateResponse("risks/new.html", context)


@router.get("/risks/{risk_id}", response_class=HTMLResponse)
async def risks_detail(request: Request, db: DbSession, risk_id: int) -> HTMLResponse:
    """Risk detail page."""
    risk = db.query(Risk).filter(Risk.id == risk_id, Risk.deleted_at.is_(None)).first()
    if not risk:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Risk {risk_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Risk {risk_id} - OPAL")
    context["risk"] = risk
    context["statuses"] = [s.value for s in RiskStatus]

    return templates.TemplateResponse("risks/detail.html", context)


# ============ DATASETS ============

@router.get("/datasets", response_class=HTMLResponse)
async def datasets_list(request: Request, db: DbSession) -> HTMLResponse:
    """Datasets list page."""
    context = get_base_context(request, db, "Datasets - OPAL")

    # Get procedures for filter
    procedures = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None)).order_by(MasterProcedure.name).all()
    context["procedures"] = procedures

    return templates.TemplateResponse("datasets/list.html", context)


@router.get("/datasets/table", response_class=HTMLResponse)
async def datasets_table(
    request: Request,
    db: DbSession,
    search: str | None = Query(None),
    procedure_id: int | None = Query(None),
) -> HTMLResponse:
    """Datasets table rows (HTMX partial)."""
    query = db.query(Dataset).filter(Dataset.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(Dataset.name.ilike(search_term))
    if procedure_id:
        query = query.filter(Dataset.procedure_id == procedure_id)

    datasets = query.order_by(Dataset.id.desc()).limit(100).all()

    return templates.TemplateResponse(
        "datasets/table_rows.html",
        {"request": request, "datasets": datasets},
    )


@router.get("/datasets/new", response_class=HTMLResponse)
async def datasets_new(request: Request, db: DbSession) -> HTMLResponse:
    """New dataset form page."""
    context = get_base_context(request, db, "New Dataset - OPAL")

    # Get procedures for linking
    procedures = db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None)).order_by(MasterProcedure.name).all()
    context["procedures"] = procedures

    return templates.TemplateResponse("datasets/new.html", context)


@router.get("/datasets/{dataset_id}", response_class=HTMLResponse)
async def datasets_detail(request: Request, db: DbSession, dataset_id: int) -> HTMLResponse:
    """Dataset detail page with chart."""
    import json

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None)).first()
    if not dataset:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Dataset {dataset_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"{dataset.name} - OPAL")
    context["dataset"] = dataset

    # Get data points
    data_points = (
        db.query(DataPoint)
        .filter(DataPoint.dataset_id == dataset_id)
        .order_by(DataPoint.recorded_at.asc())
        .limit(1000)
        .all()
    )
    context["data_points"] = data_points

    # Convert to JSON for chart
    context["data_points_json"] = json.dumps([
        {
            "id": p.id,
            "recorded_at": p.recorded_at.isoformat(),
            "values": p.values,
        }
        for p in data_points
    ])

    return templates.TemplateResponse("datasets/detail.html", context)


# ============ SUPPLIERS ============


@router.get("/suppliers", response_class=HTMLResponse)
async def suppliers_list(request: Request, db: DbSession) -> HTMLResponse:
    """Suppliers list page."""
    context = get_base_context(request, db, "Suppliers - OPAL")
    return templates.TemplateResponse("suppliers/list.html", context)


@router.get("/suppliers/table", response_class=HTMLResponse)
async def suppliers_table(
    request: Request,
    db: DbSession,
    search: str | None = None,
    is_active: str | None = None,
) -> HTMLResponse:
    """Suppliers table rows (HTMX partial)."""
    query = db.query(Supplier).filter(Supplier.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Supplier.name.ilike(search_term),
                Supplier.code.ilike(search_term),
                Supplier.email.ilike(search_term),
            )
        )

    if is_active == "true":
        query = query.filter(Supplier.is_active == True)  # noqa: E712
    elif is_active == "false":
        query = query.filter(Supplier.is_active == False)  # noqa: E712

    suppliers = query.order_by(Supplier.name).limit(100).all()

    # Build response with purchase counts
    supplier_data = []
    for s in suppliers:
        supplier_data.append({
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "email": s.email,
            "phone": s.phone,
            "is_active": s.is_active,
            "purchase_count": len(s.purchases) if s.purchases else 0,
        })

    return templates.TemplateResponse(
        "suppliers/table_rows.html",
        {"request": request, "suppliers": supplier_data},
    )


@router.get("/suppliers/new", response_class=HTMLResponse)
async def suppliers_new(request: Request, db: DbSession) -> HTMLResponse:
    """New supplier form page."""
    context = get_base_context(request, db, "New Supplier - OPAL")
    return templates.TemplateResponse("suppliers/new.html", context)


@router.get("/suppliers/{supplier_id}", response_class=HTMLResponse)
async def suppliers_detail(request: Request, db: DbSession, supplier_id: int) -> HTMLResponse:
    """Supplier detail page."""
    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
    ).first()
    if not supplier:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Supplier {supplier_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"{supplier.name} - OPAL")
    context["supplier"] = supplier
    context["purchases"] = supplier.purchases

    return templates.TemplateResponse("suppliers/detail.html", context)


@router.get("/suppliers/{supplier_id}/edit", response_class=HTMLResponse)
async def suppliers_edit(request: Request, db: DbSession, supplier_id: int) -> HTMLResponse:
    """Supplier edit page."""
    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
    ).first()
    if not supplier:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Supplier {supplier_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Edit {supplier.name} - OPAL")
    context["supplier"] = supplier

    return templates.TemplateResponse("suppliers/edit.html", context)


# ============ WORKCENTERS ============


@router.get("/workcenters", response_class=HTMLResponse)
async def workcenters_list(request: Request, db: DbSession) -> HTMLResponse:
    """Workcenters list page."""
    context = get_base_context(request, db, "Workcenters - OPAL")
    return templates.TemplateResponse("workcenters/list.html", context)


@router.get("/workcenters/table", response_class=HTMLResponse)
async def workcenters_table(
    request: Request,
    db: DbSession,
    search: str | None = None,
    is_active: str | None = None,
) -> HTMLResponse:
    """Workcenters table rows (HTMX partial)."""
    query = db.query(Workcenter)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Workcenter.name.ilike(search_term),
                Workcenter.code.ilike(search_term),
                Workcenter.location.ilike(search_term),
            )
        )

    if is_active == "true":
        query = query.filter(Workcenter.is_active == True)  # noqa: E712
    elif is_active == "false":
        query = query.filter(Workcenter.is_active == False)  # noqa: E712

    workcenters = query.order_by(Workcenter.code).limit(100).all()

    return templates.TemplateResponse(
        "workcenters/table_rows.html",
        {"request": request, "workcenters": workcenters},
    )


@router.get("/workcenters/new", response_class=HTMLResponse)
async def workcenters_new(request: Request, db: DbSession) -> HTMLResponse:
    """New workcenter form page."""
    context = get_base_context(request, db, "New Workcenter - OPAL")
    return templates.TemplateResponse("workcenters/new.html", context)


@router.get("/workcenters/{workcenter_id}", response_class=HTMLResponse)
async def workcenters_detail(request: Request, db: DbSession, workcenter_id: int) -> HTMLResponse:
    """Workcenter detail page."""
    workcenter = db.query(Workcenter).filter(Workcenter.id == workcenter_id).first()
    if not workcenter:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Workcenter {workcenter_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"{workcenter.code} - OPAL")
    context["workcenter"] = workcenter

    return templates.TemplateResponse("workcenters/detail.html", context)


@router.get("/workcenters/{workcenter_id}/edit", response_class=HTMLResponse)
async def workcenters_edit(request: Request, db: DbSession, workcenter_id: int) -> HTMLResponse:
    """Workcenter edit page."""
    workcenter = db.query(Workcenter).filter(Workcenter.id == workcenter_id).first()
    if not workcenter:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Workcenter {workcenter_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Edit {workcenter.code} - OPAL")
    context["workcenter"] = workcenter

    return templates.TemplateResponse("workcenters/edit.html", context)


# ============ USERS ============


@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, db: DbSession) -> HTMLResponse:
    """Users list page."""
    context = get_base_context(request, db, "Users - OPAL")
    return templates.TemplateResponse("users/list.html", context)


@router.get("/users/table", response_class=HTMLResponse)
async def users_table(
    request: Request,
    db: DbSession,
    search: str | None = None,
    is_active: str | None = None,
) -> HTMLResponse:
    """Users table rows (HTMX partial)."""
    query = db.query(User)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.name.ilike(search_term),
                User.email.ilike(search_term),
            )
        )

    if is_active == "true":
        query = query.filter(User.is_active == True)  # noqa: E712
    elif is_active == "false":
        query = query.filter(User.is_active == False)  # noqa: E712

    users = query.order_by(User.name).limit(100).all()

    return templates.TemplateResponse(
        "users/table_rows.html",
        {"request": request, "users_list": users},
    )


@router.get("/users/new", response_class=HTMLResponse)
async def users_new(request: Request, db: DbSession) -> HTMLResponse:
    """New user form page."""
    context = get_base_context(request, db, "New User - OPAL")
    return templates.TemplateResponse("users/new.html", context)


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def users_detail(request: Request, db: DbSession, user_id: int) -> HTMLResponse:
    """User detail page."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"User {user_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"{user.name} - OPAL")
    context["user"] = user

    return templates.TemplateResponse("users/detail.html", context)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def users_edit(request: Request, db: DbSession, user_id: int) -> HTMLResponse:
    """User edit page."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"User {user_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Edit {user.name} - OPAL")
    context["user"] = user

    return templates.TemplateResponse("users/edit.html", context)


# ============ DOCUMENTATION ============


@router.get("/docs", response_class=HTMLResponse)
async def docs(request: Request, db: DbSession) -> HTMLResponse:
    """Documentation page."""
    context = get_base_context(request, db, "Documentation - OPAL")
    return templates.TemplateResponse("docs.html", context)


# ============ PROJECT CONFIGURATION ============


@router.get("/project/new", response_class=HTMLResponse)
async def project_new(request: Request, db: DbSession) -> HTMLResponse:
    """New project wizard page."""
    import os

    context = get_base_context(request, db, "New Project - OPAL")
    context["existing_config"] = None
    context["tiers"] = DEFAULT_TIERS
    context["categories"] = []
    context["requirements"] = []
    context["default_directory"] = os.getcwd()

    return templates.TemplateResponse("project/wizard.html", context)


@router.get("/project/edit", response_class=HTMLResponse)
async def project_edit(request: Request, db: DbSession) -> HTMLResponse:
    """Edit existing project configuration."""
    from opal.config import get_active_project

    project = get_active_project()
    if not project:
        # No existing project, redirect to new
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/project/new", status_code=302)

    context = get_base_context(request, db, "Edit Project - OPAL")
    context["existing_config"] = project
    context["tiers"] = project.tiers
    context["categories"] = project.categories
    context["requirements"] = project.requirements

    return templates.TemplateResponse("project/wizard.html", context)

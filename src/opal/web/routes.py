"""Web UI routes."""

import contextlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_

from opal.api.deps import DbSession
from opal.db.models import InventoryRecord, Kit, Part, Purchase, Supplier, User, Workcenter
from opal.db.models.dataset import DataPoint, Dataset
from opal.db.models.execution import InstanceStatus, ProcedureInstance
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

# Audit log display helpers
_TABLE_URL_MAP: dict[str, str] = {
    "part": "/parts",
    "inventory_record": "/inventory/opal",
    "master_procedure": "/procedures",
    "procedure_instance": "/executions",
    "issue": "/issues",
    "risk": "/risks",
    "purchase": "/purchases",
    "supplier": "/suppliers",
    "dataset": "/datasets",
    "workcenter": "/workcenters",
    "user": "/users",
}

TABLE_DISPLAY_NAMES: dict[str, str] = {
    "part": "Part",
    "inventory_record": "Inventory",
    "master_procedure": "Procedure",
    "procedure_step": "Step",
    "procedure_version": "Version",
    "procedure_instance": "Execution",
    "step_execution": "Step Exec",
    "issue": "Issue",
    "risk": "Risk",
    "purchase": "Purchase",
    "purchase_line": "PO Line",
    "supplier": "Supplier",
    "dataset": "Dataset",
    "data_point": "Data Point",
    "workcenter": "Workcenter",
    "user": "User",
    "kit": "Kit",
    "step_kit": "Step Kit",
    "inventory_consumption": "Consumption",
    "inventory_production": "Production",
    "attachment": "Attachment",
    "stock_transfer": "Transfer",
    "stock_test_result": "Test Result",
    "test_template": "Test Template",
}

templates.env.globals["TABLE_DISPLAY_NAMES"] = TABLE_DISPLAY_NAMES


def _build_change_summary(entry) -> str:
    """Build short text summary of audit log changes."""
    action_val = entry.action.value if hasattr(entry.action, "value") else entry.action
    if action_val == "create":
        if entry.new_values and "name" in entry.new_values:
            return f"Created: {entry.new_values['name']}"
        return "Created"
    elif action_val == "update" and entry.new_values:
        fields = list(entry.new_values.keys())[:3]
        suffix = f" +{len(entry.new_values) - 3}" if len(entry.new_values) > 3 else ""
        return f"Changed: {', '.join(fields)}{suffix}"
    elif action_val == "delete":
        if entry.old_values and "name" in entry.old_values:
            return f"Deleted: {entry.old_values['name']}"
        return "Deleted"
    return ""


router = APIRouter()


def _get_current_user(request: Request, db) -> User | None:
    """Get current user from cookie."""
    cookie_user_id = request.cookies.get("opal_user_id")
    if not cookie_user_id:
        return None
    try:
        return db.query(User).filter(User.id == int(cookie_user_id), User.is_active == True).first()  # noqa: E712
    except (ValueError, TypeError):
        return None


def _require_admin_web(request: Request, db) -> RedirectResponse | None:
    """Return redirect if current user is not admin, else None."""
    user = _get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse(url="/", status_code=302)
    return None


def get_base_context(request: Request, db: DbSession, title: str) -> dict[str, Any]:
    """Get base context for all pages."""
    from opal import __version__
    from opal.config import get_active_project, get_active_settings

    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    project = get_active_project()
    settings = get_active_settings()

    # Resolve current user from cookie
    current_user = None
    is_admin = False
    cookie_user_id = request.cookies.get("opal_user_id")
    if cookie_user_id:
        with contextlib.suppress(ValueError, TypeError):
            current_user = (
                db.query(User)
                .filter(User.id == int(cookie_user_id), User.is_active.is_(True))
                .first()
            )
    if current_user:
        is_admin = current_user.is_admin

    return {
        "request": request,
        "users": users,
        "title": title,
        "project_name": project.name if project else None,
        "opal_version": __version__,
        "app_version": f"v{__version__}",
        "current_user": current_user,
        "is_admin": is_admin,
        "auth_mode": settings.auth_mode,
    }


# ============ LOGIN / LOGOUT ============


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: DbSession) -> HTMLResponse:
    """User selection page."""
    from opal.config import get_active_settings

    settings = get_active_settings()

    # In exe mode, redirect to exe.dev login
    if settings.auth_mode == "exe":
        return RedirectResponse(url="/__exe.dev/login?redirect=/", status_code=302)

    # If already logged in, redirect to home
    if request.cookies.get("opal_user_id"):
        return RedirectResponse(url="/", status_code=302)

    users = db.query(User).filter(User.is_active == True).order_by(User.name).all()  # noqa: E712
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "users": users,
            "auth_mode": settings.auth_mode,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request, db: DbSession, user_id: int = Form(...)
) -> RedirectResponse:
    """Set user identity cookies."""
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    redirect_url = "/welcome" if user.needs_onboarding else "/"
    response = RedirectResponse(url=redirect_url, status_code=302)
    max_age = 365 * 24 * 3600  # 1 year
    response.set_cookie("opal_user_id", str(user.id), max_age=max_age)
    response.set_cookie("opal_user_name", user.name, max_age=max_age)
    response.set_cookie("opal_user_email", user.email or "", max_age=max_age)
    response.set_cookie("opal_user_is_admin", "1" if user.is_admin else "0", max_age=max_age)
    return response


@router.post("/login/new-user")
async def login_new_user(
    request: Request,
    db: DbSession,
    name: str = Form(...),
    email: str = Form(""),
) -> RedirectResponse:
    """Create a new user and log in. First user auto-becomes admin."""
    # First user ever created is auto-admin
    is_first_user = db.query(User).count() == 0
    user = User(
        name=name,
        email=email or None,
        is_active=True,
        is_admin=is_first_user,
        needs_onboarding=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response = RedirectResponse(url="/welcome", status_code=302)
    max_age = 365 * 24 * 3600
    response.set_cookie("opal_user_id", str(user.id), max_age=max_age)
    response.set_cookie("opal_user_name", user.name, max_age=max_age)
    response.set_cookie("opal_user_email", user.email or "", max_age=max_age)
    response.set_cookie("opal_user_is_admin", "1" if user.is_admin else "0", max_age=max_age)
    return response


@router.get("/logout", response_model=None)
async def logout(request: Request) -> HTMLResponse | RedirectResponse:
    """Clear user identity cookies."""
    from opal.config import get_active_settings

    settings = get_active_settings()

    if settings.auth_mode == "exe":
        # Exe logout requires POST to /__exe.dev/logout — serve an auto-submit page
        html = """<!DOCTYPE html>
<html><head><title>Signing out...</title></head>
<body>
<p>Signing out...</p>
<form id="exeLogout" method="POST" action="/__exe.dev/logout"></form>
<script>document.getElementById('exeLogout').submit();</script>
</body></html>"""
        response = HTMLResponse(content=html)
    else:
        response = RedirectResponse(url="/login", status_code=302)

    response.delete_cookie("opal_user_id")
    response.delete_cookie("opal_user_name")
    response.delete_cookie("opal_user_email")
    response.delete_cookie("opal_user_is_admin")
    return response


@router.get("/setup-profile", response_class=HTMLResponse)
async def setup_profile_page(request: Request, db: DbSession) -> HTMLResponse:
    """Profile setup page for new exe-auth users to set their display name."""
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.needs_profile_setup:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        "setup_profile.html",
        {
            "request": request,
            "user": user,
        },
    )


@router.post("/setup-profile")
async def setup_profile_submit(
    request: Request,
    db: DbSession,
    name: str = Form(...),
) -> RedirectResponse:
    """Save display name and clear the profile setup flag."""
    user = _get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.name = name.strip()
    user.needs_profile_setup = False
    db.commit()

    # Update cookies with the new name
    response = RedirectResponse(url="/", status_code=302)
    max_age = 365 * 24 * 3600
    response.set_cookie("opal_user_id", str(user.id), max_age=max_age)
    response.set_cookie("opal_user_name", user.name, max_age=max_age)
    response.set_cookie("opal_user_email", user.email or "", max_age=max_age)
    response.set_cookie("opal_user_is_admin", "1" if user.is_admin else "0", max_age=max_age)
    return response


@router.get("/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request, db: DbSession) -> HTMLResponse:
    """Welcome / onboarding page."""
    context = get_base_context(request, db, "Welcome")
    current_user = context.get("current_user")
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    # First admin on a fresh system → project setup wizard
    is_fresh = db.query(Part).filter(Part.deleted_at.is_(None)).count() == 0
    if current_user.is_admin and is_fresh:
        return templates.TemplateResponse("welcome/setup.html", context)

    # Everyone else → orientation tutorial
    return templates.TemplateResponse("welcome/tutorial.html", context)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: DbSession) -> HTMLResponse:
    """Home page."""
    from opal.db.models.audit import AuditLog

    context = get_base_context(request, db, "OPAL")

    # Redirect new users to onboarding
    current_user = context.get("current_user")
    if current_user and current_user.needs_onboarding:
        return RedirectResponse(url="/welcome", status_code=302)

    # Get counts for dashboard
    context["parts_count"] = db.query(Part).filter(Part.deleted_at.is_(None)).count()
    context["procedures_count"] = (
        db.query(MasterProcedure).filter(MasterProcedure.deleted_at.is_(None)).count()
    )
    context["open_issues_count"] = (
        db.query(Issue)
        .filter(
            Issue.deleted_at.is_(None),
            Issue.status.in_(["open", "investigating", "disposition_pending"]),
        )
        .count()
    )
    context["in_progress_count"] = (
        db.query(ProcedureInstance).filter(ProcedureInstance.status == "in_progress").count()
    )
    context["risks_count"] = (
        db.query(Risk).filter(Risk.deleted_at.is_(None), Risk.status != "closed").count()
    )
    context["high_risks_count"] = len(
        [
            r
            for r in db.query(Risk).filter(Risk.deleted_at.is_(None), Risk.status != "closed").all()
            if r.severity == "high"
        ]
    )

    # Low stock count
    low_stock_parts = (
        db.query(Part)
        .filter(
            Part.deleted_at.is_(None),
            Part.reorder_point.isnot(None),
        )
        .all()
    )
    low_stock_count = 0
    for p in low_stock_parts:
        total_qty = (
            db.query(func.coalesce(func.sum(InventoryRecord.quantity), 0))
            .filter(InventoryRecord.part_id == p.id)
            .scalar()
        ) or 0
        if total_qty < p.reorder_point:
            low_stock_count += 1
    context["low_stock_count"] = low_stock_count

    # Expiring soon count (within 30 days)
    today = date.today()
    threshold = today + timedelta(days=30)
    expiring_soon_count = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(
            Part.deleted_at.is_(None),
            InventoryRecord.expiration_date.isnot(None),
            InventoryRecord.expiration_date <= threshold,
        )
        .count()
    )
    context["expiring_soon_count"] = expiring_soon_count

    # Calibration overdue count
    cal_overdue_count = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(
            Part.deleted_at.is_(None),
            Part.is_tooling == True,  # noqa: E712
            InventoryRecord.calibration_due_at.isnot(None),
            InventoryRecord.calibration_due_at <= datetime.now(UTC),
        )
        .count()
    )
    context["cal_overdue_count"] = cal_overdue_count

    # Get recent audit activity
    recent_activity = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(15).all()
    context["recent_activity"] = recent_activity

    return templates.TemplateResponse("index.html", context)


# ============ PARTS ============


@router.get("/parts", response_class=HTMLResponse)
async def parts_list(request: Request, db: DbSession) -> HTMLResponse:
    """Parts list page."""
    from opal.config import get_active_project

    context = get_base_context(request, db, "Parts - OPAL")

    # Get categories for filter dropdown
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

    return templates.TemplateResponse("parts/list.html", context)


@router.get("/parts/table", response_class=HTMLResponse)
async def parts_table(
    request: Request,
    db: DbSession,
    search: str | None = Query(None),
    category: str | None = Query(None),
    tier: str | None = Query(None),
    top_level: str | None = Query(None),
    low_stock: str | None = Query(None),
    sort_by: str | None = Query("id"),
    sort_order: str | None = Query("desc"),
) -> HTMLResponse:
    """Parts table rows (HTMX partial)."""
    query = db.query(Part).filter(Part.deleted_at.is_(None))

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

    if category:
        query = query.filter(Part.category == category)

    if tier:
        with contextlib.suppress(ValueError):
            query = query.filter(Part.tier == int(tier))

    if top_level:
        if top_level == "true":
            query = query.filter(Part.parent_id.is_(None))
        elif top_level == "false":
            query = query.filter(Part.parent_id.isnot(None))

    if low_stock == "true":
        query = query.filter(Part.reorder_point.isnot(None))

    # Apply sorting
    sort_columns = {
        "id": Part.id,
        "internal_pn": Part.internal_pn,
        "external_pn": Part.external_pn,
        "name": Part.name,
        "category": Part.category,
        "tier": Part.tier,
        "unit_of_measure": Part.unit_of_measure,
    }

    sort_col = sort_columns.get(sort_by, Part.id)
    if sort_order == "asc":
        parts = query.order_by(sort_col.asc()).limit(100).all()
    else:
        parts = query.order_by(sort_col.desc()).limit(100).all()

    # Calculate total quantities and attach to part-like objects
    parts_with_qty = []
    for part in parts:
        total_qty = (
            db.query(func.coalesce(func.sum(InventoryRecord.quantity), 0))
            .filter(InventoryRecord.part_id == part.id)
            .scalar()
        )
        # Create a dict with all part attributes plus total_quantity
        tq = total_qty or 0
        is_low = bool(part.reorder_point is not None and tq < part.reorder_point)
        part_data = {
            "id": part.id,
            "internal_pn": part.internal_pn,
            "external_pn": part.external_pn,
            "name": part.name,
            "category": part.category,
            "tier": part.tier,
            "unit_of_measure": part.unit_of_measure,
            "total_quantity": tq,
            "reorder_point": part.reorder_point,
            "is_low_stock": is_low,
        }
        parts_with_qty.append(type("PartWithQty", (), part_data)())

    # Filter low stock parts in Python (stock is computed per-row)
    if low_stock == "true":
        parts_with_qty = [p for p in parts_with_qty if p.is_low_stock]

    return templates.TemplateResponse(
        "parts/table_rows.html",
        {
            "request": request,
            "parts": parts_with_qty,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
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


@router.get("/parts/import", response_class=HTMLResponse)
async def parts_import(request: Request, db: DbSession) -> HTMLResponse:
    """CSV import page for parts."""
    context = get_base_context(request, db, "Import Parts - OPAL")
    return templates.TemplateResponse("parts/import.html", context)


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
        if project.categories:
            context["categories"] = sorted(set(context["categories"]) | set(project.categories))
    else:
        context["tiers"] = DEFAULT_TIERS

    # Get existing parts for parent selector
    assemblies = db.query(Part).filter(Part.deleted_at.is_(None)).order_by(Part.name).all()
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
    inventory_records = db.query(InventoryRecord).filter(InventoryRecord.part_id == part_id).all()
    context["inventory_records"] = inventory_records

    # Calculate total quantity for display
    total_quantity = sum(r.quantity for r in inventory_records)
    part.total_quantity = total_quantity  # Attach to part for template access

    # Where Used: procedure kit usage
    from opal.db.models.procedure import StepKit

    kit_usages = (
        db.query(Kit)
        .join(MasterProcedure)
        .filter(Kit.part_id == part.id, MasterProcedure.deleted_at.is_(None))
        .all()
    )
    context["kit_usages"] = kit_usages

    # Where Used: step-level kit usage
    step_kit_usages = db.query(StepKit).filter(StepKit.part_id == part.id).all()
    context["step_kit_usages"] = step_kit_usages

    # Where Used: consumption history
    from opal.db.models.inventory import InventoryConsumption

    consumption_history = (
        db.query(InventoryConsumption)
        .join(InventoryRecord)
        .filter(InventoryRecord.part_id == part.id)
        .order_by(InventoryConsumption.created_at.desc())
        .limit(50)
        .all()
    )
    context["consumption_history"] = consumption_history

    # BOM: components of this assembly (design-level)
    from opal.db.models.part import BOMLine

    bom_lines = db.query(BOMLine).filter(BOMLine.assembly_id == part.id).all()
    context["bom_lines"] = bom_lines

    # BOM: assemblies this part is used in (where-used)
    where_used = db.query(BOMLine).filter(BOMLine.component_id == part.id).all()
    context["where_used"] = where_used

    # Test templates
    from opal.db.models.inventory import TestTemplate

    test_templates = (
        db.query(TestTemplate)
        .filter(TestTemplate.part_id == part.id)
        .order_by(TestTemplate.sort_order)
        .all()
    )
    context["test_templates"] = test_templates

    # Onshape link (if integration is active)
    onshape_link = None
    try:
        from opal.db.models.onshape_link import OnshapeLink

        onshape_link = db.query(OnshapeLink).filter(OnshapeLink.part_id == part.id).first()
    except Exception:
        pass
    context["onshape_link"] = onshape_link

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

    # Merge in project-configured categories
    from opal.config import get_active_project

    project = get_active_project()
    if project and project.categories:
        context["categories"] = sorted(set(context["categories"]) | set(project.categories))

    return templates.TemplateResponse("parts/edit.html", context)


# ============ INVENTORY ============


@router.get("/inventory", response_class=HTMLResponse)
async def inventory_list(request: Request, db: DbSession) -> HTMLResponse:
    """Inventory list page."""
    context = get_base_context(request, db, "Inventory - OPAL")

    # Get locations for filter
    locations = db.query(InventoryRecord.location).distinct().all()
    context["locations"] = sorted([loc[0] for loc in locations])

    return templates.TemplateResponse("inventory/list.html", context)


@router.get("/inventory/new", response_class=HTMLResponse)
async def inventory_new(
    request: Request,
    db: DbSession,
    part_id: int | None = Query(None),
) -> HTMLResponse:
    """New inventory record form page."""
    context = get_base_context(request, db, "Add Inventory - OPAL")

    # Get locations for autocomplete
    locations = db.query(InventoryRecord.location).distinct().all()
    context["locations"] = sorted([loc[0] for loc in locations if loc[0]])

    # If part_id provided, load the part
    selected_part = None
    if part_id:
        selected_part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    context["selected_part"] = selected_part

    return templates.TemplateResponse("inventory/new.html", context)


@router.get("/inventory/table", response_class=HTMLResponse)
async def inventory_table(
    request: Request,
    db: DbSession,
    location: str | None = Query(None),
    part_id: int | None = Query(None),
    opal_search: str | None = Query(None),
    source_type: str | None = Query(None),
    expiration: str | None = Query(None),
    calibration: str | None = Query(None),
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
    if expiration == "expired":
        query = query.filter(
            InventoryRecord.expiration_date.isnot(None),
            InventoryRecord.expiration_date < date.today(),
        )
    elif expiration == "expiring":
        today = date.today()
        threshold = today + timedelta(days=30)
        query = query.filter(
            InventoryRecord.expiration_date.isnot(None),
            InventoryRecord.expiration_date <= threshold,
        )
    if calibration == "overdue":
        now = datetime.now(UTC)
        query = query.filter(
            Part.is_tooling == True,  # noqa: E712
            InventoryRecord.calibration_due_at.isnot(None),
            InventoryRecord.calibration_due_at <= now,
        )

    # Order by OPAL number (most recent first)
    records = query.order_by(InventoryRecord.opal_number.desc()).limit(100).all()

    return templates.TemplateResponse(
        "inventory/table_rows.html",
        {"request": request, "records": records, "today": date.today(), "now": datetime.now(UTC)},
    )


@router.get("/inventory/opal/{opal_number}", response_class=HTMLResponse)
async def inventory_opal_detail(
    request: Request,
    db: DbSession,
    opal_number: str,
) -> HTMLResponse:
    """OPAL item detail page with full traceability history."""
    from opal.db.models.inventory import InventoryProduction
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
    context["today"] = date.today()
    context["now"] = datetime.now(UTC)

    # Build history timeline
    history = []

    # Track source PO for display
    source_po = None
    source_info = {}
    if record.source_purchase_line_id:
        po_line = (
            db.query(PurchaseLine).filter(PurchaseLine.id == record.source_purchase_line_id).first()
        )
        if po_line and po_line.purchase:
            source_po = {
                "id": po_line.purchase_id,
                "number": po_line.purchase.reference,
            }
            source_info = {
                "po_id": po_line.purchase_id,
                "po_number": po_line.purchase.reference,
            }
    context["source_po"] = source_po

    history.append(
        {
            "event": "created",
            "timestamp": record.created_at,
            "details": {
                "source_type": record.source_type.value
                if record.source_type and hasattr(record.source_type, "value")
                else record.source_type,
                "quantity": float(record.quantity),
                **source_info,
            },
        }
    )

    # Consumptions
    for c in record.consumptions:
        history.append(
            {
                "event": "consumed",
                "timestamp": c.created_at,
                "details": {
                    "quantity": float(c.quantity),
                    "usage_type": c.usage_type.value
                    if hasattr(c.usage_type, "value")
                    else c.usage_type,
                    "procedure_instance_id": c.procedure_instance_id,
                    "notes": c.notes,
                },
            }
        )

    # Sort by timestamp
    history.sort(key=lambda h: h["timestamp"], reverse=True)
    context["history"] = history

    # Source production info (if this item was produced)
    source_wo = None
    if record.source_production_id:
        production = (
            db.query(InventoryProduction)
            .filter(InventoryProduction.id == record.source_production_id)
            .first()
        )
        if production and production.procedure_instance:
            source_wo = {
                "instance_id": production.procedure_instance_id,
                "work_order_number": production.procedure_instance.work_order_number,
                "serial_number": production.serial_number,
            }
    context["source_wo"] = source_wo

    # Genealogy data
    from opal.core.genealogy import get_full_genealogy

    genealogy = get_full_genealogy(db, opal_number)
    context["genealogy_components"] = genealogy["components"]
    context["genealogy_assemblies"] = genealogy["assemblies_containing"]

    # Test results and templates
    from opal.db.models.inventory import StockTestResult, TestTemplate

    test_results = (
        db.query(StockTestResult)
        .filter(StockTestResult.inventory_record_id == record.id)
        .order_by(StockTestResult.created_at.desc())
        .all()
    )
    context["test_results"] = test_results

    test_templates = (
        db.query(TestTemplate)
        .filter(TestTemplate.part_id == record.part_id)
        .order_by(TestTemplate.sort_order)
        .all()
    )
    context["test_templates"] = test_templates

    return templates.TemplateResponse("inventory/opal_detail.html", context)


@router.get("/inventory/{inventory_id}/adjust", response_class=HTMLResponse)
async def inventory_adjust(
    request: Request,
    db: DbSession,
    inventory_id: int,
) -> HTMLResponse:
    """Inventory adjustment form page."""
    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(InventoryRecord.id == inventory_id, Part.deleted_at.is_(None))
        .first()
    )
    if not record:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Inventory record {inventory_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"Adjust {record.opal_number or inventory_id} - OPAL")
    context["record"] = record
    return templates.TemplateResponse("inventory/adjust.html", context)


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
    context["parts"] = [{"id": p.id, "name": p.name, "external_pn": p.external_pn} for p in parts]

    # Get suppliers for dropdown - convert to dicts for JSON serialization
    suppliers = (
        db.query(Supplier)
        .filter(
            Supplier.deleted_at.is_(None),
            Supplier.is_active == True,  # noqa: E712
        )
        .order_by(Supplier.name)
        .all()
    )
    context["suppliers"] = [{"id": s.id, "name": s.name, "code": s.code} for s in suppliers]
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
        {"id": p.id, "name": p.name, "external_pn": p.external_pn} for p in parts
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
            version = (
                db.query(ProcedureVersion)
                .filter(ProcedureVersion.id == p.current_version_id)
                .first()
            )
            if version:
                version_number = version.version_number
        # Handle status - may be enum or string depending on context
        status_val = p.status.value if hasattr(p.status, "value") else p.status
        procs_with_info.append(
            {
                "id": p.id,
                "name": p.name,
                "procedure_type": p.procedure_type.value
                if hasattr(p.procedure_type, "value")
                else p.procedure_type,
                "status": status_val,
                "current_version_id": p.current_version_id,
                "version_number": version_number,
                "step_count": len(p.steps),
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
        )

    return templates.TemplateResponse(
        "procedures/table_rows.html",
        {"request": request, "procedures": procs_with_info},
    )


@router.get("/procedures/new", response_class=HTMLResponse)
async def procedures_new(request: Request, db: DbSession) -> HTMLResponse:
    """New procedure form page."""
    context = get_base_context(request, db, "New Procedure - OPAL")

    # Get workcenters for the form
    workcenters = (
        db.query(Workcenter).filter(Workcenter.is_active.is_(True)).order_by(Workcenter.name).all()
    )
    context["workcenters"] = workcenters

    return templates.TemplateResponse("procedures/new.html", context)


_PROCEDURE_TABS = ("meta", "operations", "flow", "kit", "outputs", "versions")


@router.get("/procedures/{procedure_id}", response_class=HTMLResponse)
async def procedures_detail(
    request: Request,
    db: DbSession,
    procedure_id: int,
    tab: str = "meta",
    op: int | None = None,
    step: int | None = None,
) -> HTMLResponse:
    """Procedure detail / editor page."""
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
        current_ver = (
            db.query(ProcedureVersion)
            .filter(ProcedureVersion.id == procedure.current_version_id)
            .first()
        )
        if current_ver:
            current_version_num = current_ver.version_number
    context["current_version_num"] = current_version_num

    # Get kit items
    kit_items = (
        db.query(Kit).join(Part).filter(Kit.procedure_id == procedure_id).order_by(Part.name).all()
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

    # Get output items (what this procedure produces)
    from opal.db.models.procedure import ProcedureOutput

    output_items = (
        db.query(ProcedureOutput)
        .join(Part)
        .filter(ProcedureOutput.procedure_id == procedure_id)
        .order_by(Part.name)
        .all()
    )
    context["output_items"] = [
        {
            "id": o.id,
            "part_id": o.part_id,
            "part_name": o.part.name,
            "part_external_pn": o.part.external_pn,
            "quantity_produced": float(o.quantity_produced),
        }
        for o in output_items
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

    # Sort by `order` (the sequence field the reorder API updates). `step_number`
    # is a stable display label and never changes when ops are rearranged.
    ops.sort(key=lambda x: x["step"].order)
    contingency_ops.sort(key=lambda x: x["step"].order)

    context["ops"] = ops
    context["contingency_ops"] = contingency_ops

    # Validate tab + pick selected op for the Operations tab.
    context["tab"] = tab if tab in _PROCEDURE_TABS else "meta"
    all_ops = ops + contingency_ops
    valid_op_orders = {o["step"].order for o in all_ops}

    def _default_op_order() -> int | None:
        if not all_ops:
            return None
        return all_ops[0]["step"].order

    context["selected_op_order"] = op if op in valid_op_orders else _default_op_order()
    context["selected_step_id"] = step

    # Per-step kit lookup keyed by step.id for the inline editor.
    from opal.db.models.procedure import ProcedureStep, StepDependency, StepKit

    step_kit_rows = (
        db.query(StepKit)
        .join(ProcedureStep, StepKit.step_id == ProcedureStep.id)
        .filter(ProcedureStep.procedure_id == procedure_id)
        .all()
    )
    step_kit_by_step: dict[int, list[dict]] = {}
    for sk in step_kit_rows:
        step_kit_by_step.setdefault(sk.step_id, []).append(
            {
                "id": sk.id,
                "part_id": sk.part_id,
                "part_name": sk.part.name,
                "quantity_required": float(sk.quantity_required),
                "usage_type": sk.usage_type.value
                if hasattr(sk.usage_type, "value")
                else sk.usage_type,
                "notes": sk.notes,
            }
        )
    context["step_kit_by_step"] = step_kit_by_step

    # Dependency edges for the Flow tab — only top-level op-to-op edges.
    dep_rows = (
        db.query(StepDependency)
        .join(ProcedureStep, StepDependency.step_id == ProcedureStep.id)
        .filter(ProcedureStep.procedure_id == procedure_id)
        .all()
    )
    context["dependencies"] = [
        {"step_id": d.step_id, "depends_on_step_id": d.depends_on_step_id} for d in dep_rows
    ]

    # Reference documents (drawings, PDFs, datasheets) attached at template level.
    from opal.db.models.attachment import Attachment

    context["reference_attachments"] = (
        db.query(Attachment)
        .filter(
            Attachment.procedure_id == procedure_id,
            Attachment.kind == "reference",
        )
        .order_by(Attachment.original_filename.asc())
        .all()
    )

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


@router.get("/procedures/{procedure_id}/steps/{step_id}/edit")
async def procedures_step_edit(db: DbSession, procedure_id: int, step_id: int) -> RedirectResponse:
    """Redirect the deep-link step editor URL to the inline editor in the
    Operations tab. Keeps old bookmarks working."""
    from opal.db.models.procedure import ProcedureStep

    step = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.id == step_id, ProcedureStep.procedure_id == procedure_id)
        .first()
    )
    parent_order = None
    if step is not None:
        if step.parent_step_id is not None:
            parent = db.query(ProcedureStep).filter(ProcedureStep.id == step.parent_step_id).first()
            if parent is not None:
                parent_order = parent.order
        else:
            parent_order = step.order

    target = f"/procedures/{procedure_id}?tab=operations"
    if parent_order is not None:
        target += f"&op={parent_order}"
    target += f"&step={step_id}"
    return RedirectResponse(url=target, status_code=302)


@router.get("/procedures/{proc_id}/versions/{v1_id}/diff/{v2_id}", response_class=HTMLResponse)
async def procedures_version_diff(
    request: Request, db: DbSession, proc_id: int, v1_id: int, v2_id: int
) -> HTMLResponse:
    """Side-by-side diff of two procedure versions."""
    from opal.core.diff import diff_procedure_versions

    procedure = db.query(MasterProcedure).filter(MasterProcedure.id == proc_id).first()
    if not procedure:
        return HTMLResponse("Procedure not found", status_code=404)

    version_a = db.query(ProcedureVersion).filter(ProcedureVersion.id == v1_id).first()
    version_b = db.query(ProcedureVersion).filter(ProcedureVersion.id == v2_id).first()
    if not version_a or not version_b:
        return HTMLResponse("Version not found", status_code=404)

    proc_changes, step_diffs = diff_procedure_versions(version_a.content, version_b.content)

    context = get_base_context(
        request, db, f"Diff v{version_a.version_number} → v{version_b.version_number} - OPAL"
    )
    context["procedure"] = procedure
    context["version_a"] = version_a
    context["version_b"] = version_b
    context["proc_changes"] = proc_changes
    context["step_diffs"] = step_diffs
    context["added_count"] = sum(1 for d in step_diffs if d.status == "added")
    context["removed_count"] = sum(1 for d in step_diffs if d.status == "removed")
    context["modified_count"] = sum(1 for d in step_diffs if d.status == "modified")
    context["unchanged_count"] = sum(1 for d in step_diffs if d.status == "unchanged")

    return templates.TemplateResponse("procedures/version_diff.html", context)


@router.get("/procedures/{proc_id}/versions/{ver_id}/print", response_class=HTMLResponse)
async def procedures_version_print(
    request: Request, db: DbSession, proc_id: int, ver_id: int
) -> HTMLResponse:
    """Print-friendly procedure traveler."""
    import base64
    import io

    import segno

    version = (
        db.query(ProcedureVersion)
        .filter(
            ProcedureVersion.id == ver_id,
            ProcedureVersion.procedure_id == proc_id,
        )
        .first()
    )
    if not version:
        return HTMLResponse("Version not found", status_code=404)

    procedure = db.query(MasterProcedure).filter(MasterProcedure.id == proc_id).first()

    # Generate QR code as data URI
    url = f"{request.base_url}procedures/{proc_id}/versions/{ver_id}"
    qr = segno.make(url)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=3, border=1)
    qr_data_uri = "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()

    # Get kit items for this procedure
    kit_items_raw = (
        db.query(Kit).join(Part).filter(Kit.procedure_id == proc_id).order_by(Part.name).all()
    )
    kit_items = [
        {
            "part_name": k.part.name,
            "part_pn": k.part.internal_pn,
            "quantity": float(k.quantity_required),
        }
        for k in kit_items_raw
    ]

    # Extract steps from version content
    steps = version.content.get("steps", [])

    return templates.TemplateResponse(
        "procedures/print_traveler.html",
        {
            "request": request,
            "procedure_name": version.content.get("procedure_name", procedure.name),
            "version_number": version.version_number,
            "description": version.content.get("procedure_description"),
            "published_at": version.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if version.created_at
            else "",
            "qr_data_uri": qr_data_uri,
            "kit_items": kit_items,
            "steps": steps,
        },
    )


@router.get("/procedures/versions/{version_id}", response_class=HTMLResponse)
async def procedures_version_detail(
    request: Request, db: DbSession, version_id: int
) -> HTMLResponse:
    """View a specific procedure version."""
    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == version_id).first()
    if not version:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Version {version_id} not found"},
            status_code=404,
        )

    procedure = db.query(MasterProcedure).filter(MasterProcedure.id == version.procedure_id).first()

    # Get all versions for this procedure (for compare links)
    versions = (
        db.query(ProcedureVersion)
        .filter(ProcedureVersion.procedure_id == procedure.id)
        .order_by(ProcedureVersion.version_number.desc())
        .all()
    )

    context = get_base_context(request, db, f"v{version.version_number} - {procedure.name} - OPAL")
    context["version"] = version
    context["procedure"] = procedure
    context["versions"] = versions

    # Build hierarchical step structure from version content
    version_steps = version.content.get("steps", [])
    children_map: dict[int, list[dict]] = {}
    for step in version_steps:
        parent_id = step.get("parent_step_id")
        if parent_id is not None:
            children_map.setdefault(parent_id, []).append(step)

    ops: list[dict[str, Any]] = []
    contingency_ops: list[dict[str, Any]] = []
    for step in version_steps:
        if step.get("parent_step_id") is None:
            step_data = {
                "step": step,
                "sub_steps": sorted(
                    children_map.get(step.get("id"), []),
                    key=lambda s: s["order"],
                ),
            }
            if step.get("is_contingency"):
                contingency_ops.append(step_data)
            else:
                ops.append(step_data)

    context["ops"] = ops
    context["contingency_ops"] = contingency_ops

    # Resolve part names for kit/output items in snapshot
    part_ids: set[int] = set()
    for item in version.content.get("kit_items", []):
        part_ids.add(item["part_id"])
    for item in version.content.get("output_items", []):
        part_ids.add(item["part_id"])

    kit_parts: dict[int, dict[str, str]] = {}
    if part_ids:
        parts = db.query(Part).filter(Part.id.in_(part_ids)).all()
        kit_parts = {p.id: {"name": p.name, "internal_pn": p.internal_pn} for p in parts}
    context["kit_parts"] = kit_parts

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
        status_val = inst.status.value if hasattr(inst.status, "value") else inst.status
        completed_steps = sum(
            1
            for se in inst.step_executions
            if (se.status.value if hasattr(se.status, "value") else se.status) == "completed"
        )
        instances_data.append(
            {
                "id": inst.id,
                "procedure_name": inst.procedure.name,
                "version_number": version.version_number if version else 0,
                "work_order": inst.work_order_number or "-",
                "status": status_val,
                "completed_steps": completed_steps,
                "total_steps": len(inst.step_executions),
                "started_at": inst.started_at,
                "created_at": inst.created_at,
            }
        )

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
        {"id": p.id, "name": p.name, "current_version_id": p.current_version_id} for p in procedures
    ]

    return templates.TemplateResponse("executions/new.html", context)


_EXECUTION_TABS = ("meta", "operations", "data", "bom", "issues", "kitting")


@router.get("/executions/{instance_id}", response_class=HTMLResponse)
async def executions_detail(
    request: Request,
    db: DbSession,
    instance_id: int,
    op: int | None = None,
    tab: str = "meta",
) -> HTMLResponse:
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
            "status": (
                step_exec.status.value
                if step_exec and hasattr(step_exec.status, "value")
                else (step_exec.status if step_exec else "pending")
            ),
        }

    all_steps = [build_step_data(vs) for vs in version_steps]
    context["steps"] = all_steps  # Flat list for backward compatibility

    # Organize into ops and sub-steps hierarchy
    ops = []  # Normal ops
    contingency_ops = []  # Contingency ops

    # Build lookup by step ID

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
            completed = (
                sum(1 for s in sub_steps if s["status"] in ["completed", "skipped"])
                if sub_steps
                else (1 if step["status"] in ["completed", "skipped"] else 0)
            )
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

    # Build redline op_data from ad-hoc StepExecution rows. These have no
    # corresponding snapshot entry — title/instructions live directly on the
    # row. Interleave them before their host op in the sidebar.
    redline_op_rows = [
        se for se in instance.step_executions if se.ad_hoc_issue_id is not None and se.level == 0
    ]
    redlines_by_host: dict[int, list] = {}
    if redline_op_rows:
        # Bulk-fetch the issues so we can show their issue_number / link.
        issue_ids = {se.ad_hoc_issue_id for se in redline_op_rows if se.ad_hoc_issue_id}
        issue_lookup = {i.id: i for i in db.query(Issue).filter(Issue.id.in_(issue_ids)).all()}
        for op_row in redline_op_rows:
            sub_rows = sorted(
                [s for s in instance.step_executions if s.parent_step_order == op_row.step_number],
                key=lambda s: s.step_number,
            )

            def _se_status(se):
                return se.status.value if hasattr(se.status, "value") else se.status

            sub_steps = [
                {
                    "order": s.step_number,
                    "step_number": s.step_number_str,
                    "level": s.level,
                    "parent_step_id": None,
                    "id": None,
                    "title": s.title or "",
                    "instructions": s.instructions,
                    "is_contingency": False,
                    "required_data_schema": s.required_data_schema,
                    "execution": s,
                    "status": _se_status(s),
                }
                for s in sub_rows
            ]
            total = len(sub_steps) if sub_steps else 1
            completed = (
                sum(1 for s in sub_steps if s["status"] in ["completed", "skipped"])
                if sub_steps
                else (1 if _se_status(op_row) in ["completed", "skipped"] else 0)
            )
            op_step = {
                "order": op_row.step_number,
                "step_number": op_row.step_number_str,
                "level": 0,
                "parent_step_id": None,
                "id": None,
                "title": op_row.title or "",
                "instructions": op_row.instructions,
                "is_contingency": False,
                "required_data_schema": op_row.required_data_schema,
                "execution": op_row,
                "status": _se_status(op_row),
                "is_ad_hoc": True,
                "ad_hoc_issue": issue_lookup.get(op_row.ad_hoc_issue_id),
                "ad_hoc_host_order": op_row.ad_hoc_host_order,
            }
            op_data = {
                "step": op_step,
                "sub_steps": sub_steps,
                "total_steps": total,
                "completed_steps": completed,
                "is_ad_hoc": True,
            }
            redlines_by_host.setdefault(op_row.ad_hoc_host_order, []).append(op_data)

    # Interleave: for each normal op, insert its redlines just before it.
    if redlines_by_host:
        interleaved: list = []
        for op_data in ops:
            host_order = op_data["step"].get("order")
            for r in redlines_by_host.get(host_order, []):
                interleaved.append(r)
            interleaved.append(op_data)
        ops = interleaved

    context["ops"] = ops
    context["contingency_ops"] = contingency_ops

    # Pick which op's steps to render on the right pane.
    all_ops = ops + contingency_ops
    valid_orders = {o["step"]["order"] for o in all_ops}

    def _pick_default_order() -> int | None:
        if not all_ops:
            return None
        for o in all_ops:
            if o["step"]["status"] == "in_progress":
                return o["step"]["order"]
        for o in all_ops:
            if o["step"]["status"] not in ("completed", "signed_off", "skipped"):
                return o["step"]["order"]
        return all_ops[0]["step"]["order"]

    context["selected_op_order"] = op if op in valid_orders else _pick_default_order()

    context["tab"] = tab if tab in _EXECUTION_TABS else "meta"

    # Map step order -> version step data (for data capture schemas, requires_signoff)
    context["version_steps_map"] = {s["order"]: s for s in version_steps}

    # Get kit information
    kit_items = db.query(Kit).filter(Kit.procedure_id == instance.procedure_id).all()
    context["kit_items"] = kit_items

    # Get existing consumptions
    from opal.db.models.inventory import (
        InventoryConsumption,
        InventoryProduction,
    )
    from opal.db.models.procedure import ProcedureOutput

    consumptions = (
        db.query(InventoryConsumption)
        .filter(InventoryConsumption.procedure_instance_id == instance_id)
        .all()
    )
    context["consumptions"] = consumptions

    # Group consumptions by step execution ID for step-level display
    step_consumptions: dict[int, list] = {}
    for c in consumptions:
        if c.step_execution_id:
            step_consumptions.setdefault(c.step_execution_id, []).append(c)
    context["step_consumptions"] = step_consumptions

    # Step execution ID -> step number lookup
    step_exec_lookup = {
        se.id: se.step_number_str or str(se.step_number) for se in instance.step_executions
    }
    context["step_exec_lookup"] = step_exec_lookup

    # Get outputs (what this procedure produces)
    output_items = (
        db.query(ProcedureOutput)
        .filter(ProcedureOutput.procedure_id == instance.procedure_id)
        .all()
    )
    context["output_items"] = output_items

    # Get existing productions
    productions = (
        db.query(InventoryProduction)
        .filter(InventoryProduction.procedure_instance_id == instance_id)
        .all()
    )
    context["productions"] = productions

    # BOM reconciliation data
    kit_items = context["kit_items"]
    consume_consumptions = [
        c
        for c in consumptions
        if (c.usage_type.value if hasattr(c.usage_type, "value") else c.usage_type) == "consume"
    ]
    consumed_by_part: dict[int, float] = {}
    for c in consume_consumptions:
        pid = c.inventory_record.part_id
        consumed_by_part[pid] = consumed_by_part.get(pid, 0) + float(c.quantity)

    bom_items = []
    for k in kit_items:
        qty_consumed = consumed_by_part.pop(k.part_id, 0)
        qty_required = float(k.quantity_required)
        bom_items.append(
            {
                "part_id": k.part_id,
                "part_name": k.part.name,
                "qty_required": qty_required,
                "qty_consumed": qty_consumed,
                "variance": qty_consumed - qty_required,
            }
        )
    # Unplanned consumptions (consumed but not in kit)
    unplanned = []
    for pid, qty in consumed_by_part.items():
        inv_c = next((c for c in consume_consumptions if c.inventory_record.part_id == pid), None)
        unplanned.append(
            {
                "part_id": pid,
                "part_name": inv_c.inventory_record.part.name if inv_c else "Unknown",
                "qty_consumed": qty,
            }
        )
    context["bom_items"] = bom_items
    context["unplanned_consumptions"] = unplanned

    # Can finalize: instance completed + has WIP productions
    inst_status = instance.status.value if hasattr(instance.status, "value") else instance.status
    has_wip = any(
        (p.status.value if hasattr(p.status, "value") else p.status) == "wip" for p in productions
    )
    context["can_finalize"] = inst_status == "completed" and has_wip

    # Linked issues
    linked_issues = (
        db.query(Issue)
        .filter(
            Issue.procedure_instance_id == instance.id,
            Issue.deleted_at.is_(None),
        )
        .all()
    )
    context["linked_issues"] = linked_issues

    # Step-hold lookup: open NCs that put their step on hold, keyed by step_execution_id.
    holding_ncs_by_step: dict[int, list[Issue]] = {}
    for iss in linked_issues:
        iss_type = iss.issue_type.value if hasattr(iss.issue_type, "value") else iss.issue_type
        iss_status = iss.status.value if hasattr(iss.status, "value") else iss.status
        if (
            iss_type == "non_conformance"
            and iss.step_execution_id
            and iss_status not in ("disposition_approved", "closed")
        ):
            holding_ncs_by_step.setdefault(iss.step_execution_id, []).append(iss)
    context["step_holding_ncs"] = holding_ncs_by_step

    # Per-op aggregate of open NCs (op-level + any of its sub-steps). Used to
    # decide when to show the "+ ADD REDLINE OP" button and to populate the
    # modal's NC dropdown. Keyed by op.order.
    open_ncs_by_op_order: dict[int, list[Issue]] = {}
    for op_data in ops + contingency_ops:
        op_step = op_data["step"]
        if op_data.get("is_ad_hoc"):
            continue
        op_exec = op_step.get("execution")
        bucket: list[Issue] = []
        if op_exec is not None:
            bucket.extend(holding_ncs_by_step.get(op_exec.id, []))
        for sub in op_data.get("sub_steps", []):
            sub_exec = sub.get("execution")
            if sub_exec is not None:
                bucket.extend(holding_ncs_by_step.get(sub_exec.id, []))
        if bucket:
            open_ncs_by_op_order[op_step["order"]] = bucket
    context["op_open_ncs_by_order"] = open_ncs_by_op_order

    # Gating lookup: top-level ops whose prerequisite ops haven't reached
    # a terminal status yet. Keyed by op.order → list of blocking step_number_str.
    terminal_step_statuses = {"completed", "signed_off", "skipped"}
    exec_by_order = {se.step_number: se for se in instance.step_executions}
    gated_ops_by_order: dict[int, list[str]] = {}
    version_steps_for_gating = version.content.get("steps", []) if version else []
    for vs in version_steps_for_gating:
        if vs.get("level", 0) != 0:
            continue
        deps = vs.get("depends_on") or []
        if not deps:
            continue
        blockers: list[str] = []
        for dep_order in deps:
            prereq = exec_by_order.get(dep_order)
            if prereq is None:
                continue
            prereq_status = (
                prereq.status.value if hasattr(prereq.status, "value") else prereq.status
            )
            if prereq_status not in terminal_step_statuses:
                blockers.append(prereq.step_number_str or str(dep_order))
        if blockers:
            gated_ops_by_order[vs["order"]] = blockers
    context["gated_ops_by_order"] = gated_ops_by_order

    # Reference documents on the procedure template (eng drawings, PDFs, etc.).
    from opal.db.models.attachment import Attachment as _Attachment

    context["reference_attachments"] = (
        db.query(_Attachment)
        .filter(
            _Attachment.procedure_id == instance.procedure_id,
            _Attachment.kind == "reference",
        )
        .order_by(_Attachment.original_filename.asc())
        .all()
    )

    # Meta tab extras: last-activity timestamp + flat data-capture audit rows.
    step_update_times = [
        se.updated_at for se in instance.step_executions if se.updated_at is not None
    ]
    candidate_times = [t for t in [instance.updated_at, *step_update_times] if t is not None]
    context["last_activity_at"] = max(candidate_times) if candidate_times else None

    data_rows = []
    for se in instance.step_executions:
        if not se.data_captured:
            continue
        step_num = se.step_number_str or str(se.step_number)
        by_name = se.completed_by_user.name if se.completed_by_user else None
        at = se.completed_at or se.updated_at
        for field, value in se.data_captured.items():
            if isinstance(value, bool):
                display = "YES" if value else "NO"
            elif value is None or value == "":
                display = "—"
            elif isinstance(value, list):
                # Multi-photo (and any future list-valued capture) — render
                # as "N image(s) (#12, #17)" rather than leaking the raw
                # storage format "[12, 17]" into the audit table.
                if value:
                    display = f"{len(value)} image(s) (" + ", ".join(f"#{v}" for v in value) + ")"
                else:
                    display = "—"
            else:
                display = str(value)
            data_rows.append(
                {
                    "step_number": step_num,
                    "step_sort": se.step_number,
                    "field": field,
                    "value": display,
                    "by": by_name,
                    "at": at,
                }
            )
    data_rows.sort(key=lambda r: (r["step_sort"], r["field"]))
    context["data_rows"] = data_rows

    return templates.TemplateResponse("executions/detail.html", context)


@router.get("/executions/{instance_id}/report", response_class=HTMLResponse)
async def executions_report(request: Request, db: DbSession, instance_id: int) -> HTMLResponse:
    """Standalone, printable build report for a completed work order."""
    import base64
    import io
    from datetime import UTC, datetime

    import segno

    from opal.db.models.attachment import Attachment
    from opal.db.models.inventory import InventoryProduction
    from opal.db.models.procedure import ProcedureOutput

    instance = db.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).first()
    if not instance:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"Execution {instance_id} not found"},
            status_code=404,
        )

    inst_status = instance.status.value if hasattr(instance.status, "value") else instance.status
    if inst_status != "completed":
        return HTMLResponse(
            f"<h1>Build report unavailable</h1>"
            f"<p>Work order is currently <b>{inst_status.upper()}</b>. "
            f"Reports are only generated for COMPLETED work orders.</p>"
            f'<p><a href="/executions/{instance_id}">Back to execution</a></p>',
            status_code=400,
        )

    version = db.query(ProcedureVersion).filter(ProcedureVersion.id == instance.version_id).first()
    procedure = (
        db.query(MasterProcedure).filter(MasterProcedure.id == instance.procedure_id).first()
    )

    # QR back to the execution detail page.
    url = f"{request.base_url}executions/{instance_id}"
    qr = segno.make(url)
    qr_buf = io.BytesIO()
    qr.save(qr_buf, kind="svg", scale=3, border=1)
    qr_data_uri = "data:image/svg+xml;base64," + base64.b64encode(qr_buf.getvalue()).decode()

    # End items: ProcedureOutput defines what this procedure produces; productions
    # are the actual produced units (serial + OPAL number).
    output_items = (
        db.query(ProcedureOutput)
        .filter(ProcedureOutput.procedure_id == instance.procedure_id)
        .all()
    )
    productions = (
        db.query(InventoryProduction)
        .filter(InventoryProduction.procedure_instance_id == instance_id)
        .all()
    )

    # Map step_number -> version step (for human-readable data labels).
    version_steps = version.content.get("steps", []) if version else []
    version_steps_by_order = {s["order"]: s for s in version_steps}

    # Sorted step executions for the operations table + data collects.
    step_execs = sorted(instance.step_executions, key=lambda se: se.step_number)

    def _se_status(se) -> str:
        return se.status.value if hasattr(se.status, "value") else se.status

    ops_summary = []
    for se in step_execs:
        vs = version_steps_by_order.get(se.step_number)
        title = se.title or (vs.get("title") if vs else None) or "(untitled)"
        ops_summary.append(
            {
                "step_number": se.step_number_str or str(se.step_number),
                "title": title,
                "status": _se_status(se),
                "started_at": se.started_at,
                "completed_at": se.completed_at,
                "operator": se.completed_by_user.name if se.completed_by_user else None,
                "signoff": se.signed_off_by_user.name if se.signed_off_by_user else None,
                "signoff_at": se.signed_off_at,
            }
        )

    # Data collects: per step, resolve field name -> human label from the schema.
    data_collects = []
    for se in step_execs:
        if not se.data_captured:
            continue
        vs = version_steps_by_order.get(se.step_number)
        schema = se.required_data_schema or (vs.get("required_data_schema") if vs else None) or {}
        field_defs = {f["name"]: f for f in schema.get("fields", []) if "name" in f}

        rows = []
        for field_name, value in se.data_captured.items():
            field_def = field_defs.get(field_name, {})
            label = field_def.get("label") or field_name
            unit = field_def.get("unit")
            if isinstance(value, bool):
                display = "YES" if value else "NO"
            elif value is None or value == "":
                display = "-"
            elif isinstance(value, list):
                if value:
                    display = f"{len(value)} image(s) (" + ", ".join(f"#{v}" for v in value) + ")"
                else:
                    display = "-"
            else:
                display = str(value)
            rows.append({"label": label, "value": display, "unit": unit})

        if rows:
            data_collects.append(
                {
                    "step_number": se.step_number_str or str(se.step_number),
                    "step_title": se.title or (vs.get("title") if vs else None) or "(untitled)",
                    "rows": rows,
                }
            )

    # Datasets with chart-enabled fields whose points are tied to this WO.
    step_exec_ids = {se.id for se in step_execs}
    chart_datasets: list[dict] = []
    if step_exec_ids:
        points = (
            db.query(DataPoint)
            .filter(DataPoint.step_execution_id.in_(step_exec_ids))
            .order_by(DataPoint.recorded_at.asc())
            .all()
        )
        points_by_ds: dict[int, list[DataPoint]] = {}
        for p in points:
            points_by_ds.setdefault(p.dataset_id, []).append(p)

        if points_by_ds:
            datasets = (
                db.query(Dataset)
                .filter(Dataset.id.in_(points_by_ds.keys()), Dataset.deleted_at.is_(None))
                .all()
            )
            for ds in datasets:
                fields = (ds.schema or {}).get("fields", []) or []
                chart_fields = [
                    f
                    for f in fields
                    if f.get("chart") is True and f.get("type") == "number" and f.get("name")
                ]
                if not chart_fields:
                    continue
                points_for_ds = points_by_ds.get(ds.id, [])
                points_json = [
                    {"recorded_at": p.recorded_at.isoformat(), "values": p.values}
                    for p in points_for_ds
                ]
                chart_datasets.append(
                    {
                        "dataset": ds,
                        "chart_fields": chart_fields,
                        "all_fields": fields,
                        "points": points_for_ds,
                        "points_json": points_json,
                    }
                )

    # Linked issues on this WO.
    issues = (
        db.query(Issue)
        .filter(Issue.procedure_instance_id == instance.id, Issue.deleted_at.is_(None))
        .order_by(Issue.created_at.asc())
        .all()
    )

    # Closeout photos only.
    closeout_attachments = (
        db.query(Attachment)
        .filter(
            Attachment.procedure_instance_id == instance.id,
            Attachment.kind == "closeout",
        )
        .order_by(Attachment.created_at.asc())
        .all()
    )

    return templates.TemplateResponse(
        "executions/report.html",
        {
            "request": request,
            "instance": instance,
            "version": version,
            "procedure": procedure,
            "qr_data_uri": qr_data_uri,
            "output_items": output_items,
            "productions": productions,
            "ops_summary": ops_summary,
            "data_collects": data_collects,
            "chart_datasets": chart_datasets,
            "issues": issues,
            "closeout_attachments": closeout_attachments,
            "generated_at": datetime.now(UTC),
        },
    )


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
        return val.value if hasattr(val, "value") else val

    issues_data = [
        {
            "id": i.id,
            "issue_number": i.issue_number,
            "title": i.title,
            "issue_type": get_val(i, "issue_type"),
            "status": get_val(i, "status"),
            "priority": get_val(i, "priority"),
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

    # Get parts, procedures, and users for linking
    parts = db.query(Part).filter(Part.deleted_at.is_(None)).order_by(Part.name).all()
    procedures = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.deleted_at.is_(None))
        .order_by(MasterProcedure.name)
        .all()
    )
    from opal.db.models.user import User

    users = db.query(User).filter(User.is_active == True).order_by(User.name).all()  # noqa: E712
    context["parts"] = parts
    context["procedures"] = procedures
    context["users"] = users

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

    from opal.db.models.attachment import Attachment
    from opal.db.models.issue import DispositionType
    from opal.db.models.issue_comment import IssueComment
    from opal.db.models.user import User

    comments = (
        db.query(IssueComment)
        .filter(IssueComment.issue_id == issue.id)
        .order_by(IssueComment.created_at)
        .all()
    )
    attachments = db.query(Attachment).filter(Attachment.issue_id == issue.id).all()
    users = db.query(User).filter(User.is_active == True).order_by(User.name).all()  # noqa: E712

    context["comments"] = comments
    context["attachments"] = attachments
    context["users"] = users
    context["disposition_types"] = [d.value for d in DispositionType]

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
    context["risks_json"] = json.dumps(
        [
            {"id": r.id, "title": r.title, "probability": r.probability, "impact": r.impact}
            for r in risks
        ]
    )

    return templates.TemplateResponse("risks/matrix.html", context)


@router.get("/risks/new", response_class=HTMLResponse)
async def risks_new(request: Request, db: DbSession) -> HTMLResponse:
    """New risk form page."""
    context = get_base_context(request, db, "New Risk - OPAL")

    # Get issues for linking
    issues = (
        db.query(Issue)
        .filter(Issue.deleted_at.is_(None))
        .order_by(Issue.id.desc())
        .limit(100)
        .all()
    )
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
    procedures = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.deleted_at.is_(None))
        .order_by(MasterProcedure.name)
        .all()
    )
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
    procedures = (
        db.query(MasterProcedure)
        .filter(MasterProcedure.deleted_at.is_(None))
        .order_by(MasterProcedure.name)
        .all()
    )
    context["procedures"] = procedures

    return templates.TemplateResponse("datasets/new.html", context)


@router.get("/datasets/{dataset_id}", response_class=HTMLResponse)
async def datasets_detail(request: Request, db: DbSession, dataset_id: int) -> HTMLResponse:
    """Dataset detail page with chart."""
    import json

    dataset = (
        db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None)).first()
    )
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
    context["data_points_json"] = json.dumps(
        [
            {
                "id": p.id,
                "recorded_at": p.recorded_at.isoformat(),
                "values": p.values,
            }
            for p in data_points
        ]
    )

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
        supplier_data.append(
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "email": s.email,
                "phone": s.phone,
                "is_active": s.is_active,
                "purchase_count": len(s.purchases) if s.purchases else 0,
            }
        )

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
    supplier = (
        db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.deleted_at.is_(None)).first()
    )
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
    supplier = (
        db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.deleted_at.is_(None)).first()
    )
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


@router.get("/users")
async def users_list(request: Request, db: DbSession):
    """Redirect to settings page (user management is now on /settings)."""
    return RedirectResponse(url="/settings", status_code=302)


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
    """New user form page. Admin only."""
    redirect = _require_admin_web(request, db)
    if redirect:
        return redirect
    context = get_base_context(request, db, "New User - OPAL")
    return templates.TemplateResponse("users/new.html", context)


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def users_detail(request: Request, db: DbSession, user_id: int) -> HTMLResponse:
    """User detail page. Self-view for all, admin can view anyone."""
    current_user = _get_current_user(request, db)
    is_own_profile = current_user and current_user.id == user_id

    # Non-admins can only view their own profile
    if not is_own_profile and (not current_user or not current_user.is_admin):
        return RedirectResponse(url="/", status_code=302)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request, "message": f"User {user_id} not found"},
            status_code=404,
        )

    context = get_base_context(request, db, f"{user.name} - OPAL")
    context["user"] = user
    context["is_own_profile"] = is_own_profile

    return templates.TemplateResponse("users/detail.html", context)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def users_edit(request: Request, db: DbSession, user_id: int) -> HTMLResponse:
    """User edit page. Self-edit for all, admin can edit anyone."""
    current_user = _get_current_user(request, db)
    is_own_profile = current_user and current_user.id == user_id

    # Non-admins can only edit their own profile
    if not is_own_profile and (not current_user or not current_user.is_admin):
        return RedirectResponse(url="/", status_code=302)

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


# ============ LABEL PRINT ============


@router.get("/label", response_class=HTMLResponse)
async def label_print(
    request: Request,
    db: DbSession,
    type: str = Query(...),
    id: int = Query(...),
) -> HTMLResponse:
    """Print label with QR code for a part or inventory record."""
    if type == "inventory":
        record = (
            db.query(InventoryRecord)
            .join(Part)
            .filter(InventoryRecord.id == id, Part.deleted_at.is_(None))
            .first()
        )
        if not record:
            return HTMLResponse("Not found", status_code=404)
        return templates.TemplateResponse(
            "label_print.html",
            {
                "request": request,
                "entity_type": "inventory",
                "entity_id": record.id,
                "identifier": record.opal_number or f"INV-{record.id}",
                "name": record.part.name,
                "location": record.location,
            },
        )
    elif type == "part":
        part = db.query(Part).filter(Part.id == id, Part.deleted_at.is_(None)).first()
        if not part:
            return HTMLResponse("Not found", status_code=404)
        return templates.TemplateResponse(
            "label_print.html",
            {
                "request": request,
                "entity_type": "parts",
                "entity_id": part.id,
                "identifier": part.internal_pn or f"PART-{part.id}",
                "name": part.name,
                "location": None,
            },
        )
    return HTMLResponse("Invalid type", status_code=400)


# ============ DOCUMENTATION ============


@router.get("/docs", response_class=HTMLResponse)
async def docs(request: Request, db: DbSession) -> HTMLResponse:
    """Documentation page."""
    context = get_base_context(request, db, "Documentation - OPAL")
    return templates.TemplateResponse("docs.html", context)


# ============ PROJECT CONFIGURATION ============


@router.get("/project/new", response_class=HTMLResponse)
async def project_new(request: Request, db: DbSession) -> HTMLResponse:
    """New project wizard page. Admin only."""
    import os

    redirect = _require_admin_web(request, db)
    if redirect:
        return redirect

    context = get_base_context(request, db, "New Project - OPAL")
    context["existing_config"] = None
    context["tiers"] = DEFAULT_TIERS
    context["categories"] = []
    context["requirements"] = []
    context["default_directory"] = os.getcwd()

    return templates.TemplateResponse("project/wizard.html", context)


@router.get("/project/edit", response_class=HTMLResponse)
async def project_edit(request: Request, db: DbSession) -> HTMLResponse:
    """Edit existing project configuration. Admin only."""
    from opal.config import get_active_project

    redirect = _require_admin_web(request, db)
    if redirect:
        return redirect

    project = get_active_project()
    if not project:
        # No existing project, redirect to new
        return RedirectResponse(url="/project/new", status_code=302)

    context = get_base_context(request, db, "Edit Project - OPAL")
    context["existing_config"] = project
    context["tiers"] = project.tiers
    context["categories"] = project.categories
    context["requirements"] = project.requirements

    return templates.TemplateResponse("project/wizard.html", context)


# ============ SETTINGS ============


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: DbSession) -> HTMLResponse:
    """System settings page."""
    import platform

    from opal.config import get_active_project, get_active_settings, get_default_data_dir

    context = get_base_context(request, db, "Settings - OPAL")
    project = get_active_project()
    settings = get_active_settings()

    # Compute database size
    db_path = settings.database_url.replace("sqlite:///", "")
    db_size = "-"
    try:
        size_bytes = Path(db_path).stat().st_size
        if size_bytes < 1024:
            db_size = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            db_size = f"{size_bytes / 1024:.1f} KB"
        else:
            db_size = f"{size_bytes / (1024 * 1024):.1f} MB"
    except OSError:
        pass

    # Max upload size human-readable
    max_bytes = settings.max_upload_size
    if max_bytes < 1024 * 1024:
        max_upload = f"{max_bytes / 1024:.0f} KB"
    else:
        max_upload = f"{max_bytes / (1024 * 1024):.0f} MB"

    context["project"] = project

    # Onshape integration context
    onshape_enabled = settings.onshape_enabled
    context["onshape_enabled"] = onshape_enabled
    context["onshape_connected"] = False
    context["onshape_documents"] = []
    context["onshape_poll_interval"] = settings.onshape_poll_interval_minutes
    if onshape_enabled and project and project.onshape.documents:
        context["onshape_connected"] = True
        context["onshape_documents"] = project.onshape.documents

    context["sys_info"] = {
        "opal_version": context["opal_version"],
        "python_version": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "server": f"{settings.host}:{settings.port}",
        "debug": settings.debug,
        "auth_mode": settings.auth_mode,
        "data_dir": str(get_default_data_dir()),
        "db_path": db_path,
        "db_size": db_size,
        "upload_dir": str(settings.upload_dir),
        "max_upload_size": max_upload,
    }

    return templates.TemplateResponse("settings/index.html", context)


def _onshape_form_context(request: Request, db: DbSession) -> dict[str, Any]:
    """Build the template context for the Onshape configure form."""
    from opal.config import get_active_settings

    s = get_active_settings()
    context = get_base_context(request, db, "Onshape - OPAL")
    context["onshape_enabled"] = s.onshape_enabled
    context["form"] = {
        "access_key": s.onshape_access_key,
        "base_url": s.onshape_base_url,
        "poll_interval_minutes": s.onshape_poll_interval_minutes,
        "has_secret_key": bool(s.onshape_secret_key),
        "has_webhook_secret": bool(s.onshape_webhook_secret),
    }
    return context


@router.get("/settings/onshape/configure", response_class=HTMLResponse, response_model=None)
async def settings_onshape_configure_form(
    request: Request, db: DbSession
) -> HTMLResponse | RedirectResponse:
    """Render the Onshape credentials form (admin only)."""
    if redirect := _require_admin_web(request, db):
        return redirect
    context = _onshape_form_context(request, db)
    context["save_result"] = None
    context["test_result"] = None
    return templates.TemplateResponse("settings/onshape_configure.html", context)


@router.post("/settings/onshape/configure", response_class=HTMLResponse, response_model=None)
async def settings_onshape_configure_save(
    request: Request,
    db: DbSession,
    access_key: str = Form(default=""),
    secret_key: str = Form(default=""),
    base_url: str = Form(default="https://cad.onshape.com"),
    poll_interval_minutes: int = Form(default=15),
    webhook_secret: str = Form(default=""),
    clear_secret_key: bool = Form(default=False),
    clear_webhook_secret: bool = Form(default=False),
) -> HTMLResponse | RedirectResponse:
    """Persist Onshape credentials. Blank secret fields keep existing values
    unless the matching ``clear_*`` checkbox was sent."""
    if redirect := _require_admin_web(request, db):
        return redirect

    from opal.config import apply_db_overlay, get_active_settings, set_app_setting

    current = get_active_settings()

    new_secret: str | None
    if clear_secret_key:
        new_secret = ""
    elif secret_key:
        new_secret = secret_key
    else:
        new_secret = current.onshape_secret_key

    new_webhook: str | None
    if clear_webhook_secret:
        new_webhook = ""
    elif webhook_secret:
        new_webhook = webhook_secret
    else:
        new_webhook = current.onshape_webhook_secret

    set_app_setting(db, "onshape_access_key", access_key.strip())
    set_app_setting(db, "onshape_secret_key", new_secret)
    set_app_setting(db, "onshape_base_url", base_url.strip() or "https://cad.onshape.com")
    set_app_setting(db, "onshape_poll_interval_minutes", str(max(0, poll_interval_minutes)))
    set_app_setting(db, "onshape_webhook_secret", new_webhook)
    db.commit()
    apply_db_overlay(db)

    context = _onshape_form_context(request, db)
    context["save_result"] = {"ok": True, "message": "Onshape settings saved."}
    context["test_result"] = None
    return templates.TemplateResponse("settings/onshape_configure.html", context)


@router.post("/settings/onshape/test", response_class=HTMLResponse)
async def settings_onshape_test(request: Request, db: DbSession) -> HTMLResponse:
    """Run a credential smoke-test against the saved Onshape config.
    Returns an HTMX banner partial."""
    if redirect := _require_admin_web(request, db):
        return redirect

    from opal.config import get_active_settings
    from opal.integrations.onshape.client import OnshapeApiError, OnshapeClient

    s = get_active_settings()
    if not s.onshape_enabled:
        result = {"ok": False, "message": "Access key and secret key are required."}
    else:
        import json as _json

        try:
            client = OnshapeClient(
                access_key=s.onshape_access_key,
                secret_key=s.onshape_secret_key,
                base_url=s.onshape_base_url,
            )
            try:
                info = client.get_session_info()
            finally:
                client.close()
            name = info.get("name") or info.get("email") or "session OK"
            result = {"ok": True, "message": f"Connected as {name}."}
        except OnshapeApiError as err:
            result = {"ok": False, "message": f"Onshape API {err.status_code}: {err.detail}"}
        except _json.JSONDecodeError:
            # Onshape returns an HTML login page (HTTP 200) for bad credentials,
            # which trips the JSON decoder before we ever see a 4xx.
            result = {
                "ok": False,
                "message": "Authentication failed — check that the access and secret keys are correct.",
            }
        except Exception as err:
            result = {"ok": False, "message": f"Connection failed: {err}"}

    return templates.TemplateResponse(
        "settings/_onshape_test_banner.html",
        {"request": request, "test_result": result},
    )


@router.get("/settings/onshape/sync-log", response_class=HTMLResponse)
async def settings_onshape_sync_log(request: Request, db: DbSession) -> HTMLResponse:
    """HTMX partial: recent Onshape sync log entries."""
    from opal.db.models.onshape_link import OnshapeSyncLog

    sync_logs = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc()).limit(10).all()
    return templates.TemplateResponse(
        "settings/onshape_sync_log.html",
        {"request": request, "sync_logs": sync_logs},
    )


@router.get("/settings/onshape/documents", response_class=HTMLResponse)
async def settings_onshape_documents(request: Request, db: DbSession) -> HTMLResponse:
    """HTMX partial: Onshape registered documents table + add form."""
    from opal.config import get_active_project, get_active_settings

    settings = get_active_settings()
    project = get_active_project()
    documents = project.onshape.documents if project else []
    context = get_base_context(request, db, "")
    context["onshape_documents"] = documents
    context["onshape_enabled"] = settings.onshape_enabled
    context["onshape_doc_error"] = None
    context["onshape_doc_success"] = None
    return templates.TemplateResponse("settings/onshape_documents.html", context)


@router.post("/settings/onshape/documents", response_class=HTMLResponse)
async def settings_onshape_add_document(request: Request, db: DbSession) -> HTMLResponse:
    """HTMX: add an Onshape document from a pasted URL."""
    import asyncio

    from opal.config import get_active_project, get_active_settings
    from opal.integrations.onshape.client import (
        OnshapeApiError,
        OnshapeClient,
        parse_onshape_url,
    )
    from opal.project import OnshapeDocumentRef, save_project_config

    settings = get_active_settings()
    project = get_active_project()

    form = await request.form()
    url = str(form.get("url", "")).strip()
    name_override = str(form.get("name", "")).strip()

    documents = project.onshape.documents if project else []
    context = get_base_context(request, db, "")
    context["onshape_documents"] = documents
    context["onshape_enabled"] = settings.onshape_enabled
    context["onshape_doc_error"] = None
    context["onshape_doc_success"] = None

    if not url:
        context["onshape_doc_error"] = "URL is required"
        return templates.TemplateResponse("settings/onshape_documents.html", context)

    if not project:
        context["onshape_doc_error"] = "No project configured"
        return templates.TemplateResponse("settings/onshape_documents.html", context)

    parsed = parse_onshape_url(url)
    if not parsed:
        context["onshape_doc_error"] = (
            "Invalid Onshape URL. Expected: https://cad.onshape.com/documents/..."
        )
        return templates.TemplateResponse("settings/onshape_documents.html", context)

    document_id, wvm_type, wvm_id, element_id = parsed

    if wvm_type != "w":
        context["onshape_doc_error"] = (
            "Only workspace URLs (/w/) are supported. Open the document in a workspace."
        )
        return templates.TemplateResponse("settings/onshape_documents.html", context)
    workspace_id = wvm_id

    # Duplicate check
    for doc in project.onshape.documents:
        if doc.document_id == document_id and doc.element_id == element_id:
            context["onshape_doc_error"] = f"Already registered as '{doc.name}'"
            return templates.TemplateResponse("settings/onshape_documents.html", context)

    # Auto-detect element type
    client = OnshapeClient(
        access_key=settings.onshape_access_key,
        secret_key=settings.onshape_secret_key,
        base_url=settings.onshape_base_url,
    )
    try:
        elements = await asyncio.to_thread(client.get_elements, document_id, workspace_id)
    except OnshapeApiError as e:
        context["onshape_doc_error"] = f"Onshape API error: {e.detail}"
        return templates.TemplateResponse("settings/onshape_documents.html", context)
    finally:
        client.close()

    matched = next((el for el in elements if el.id == element_id), None)
    if not matched:
        context["onshape_doc_error"] = "Element not found in the Onshape document"
        return templates.TemplateResponse("settings/onshape_documents.html", context)

    type_map = {"PARTSTUDIO": "part_studio", "ASSEMBLY": "assembly"}
    element_type = type_map.get(matched.element_type)
    if not element_type:
        context["onshape_doc_error"] = (
            f"Unsupported element type: {matched.element_type}. "
            "Only assemblies and part studios are supported."
        )
        return templates.TemplateResponse("settings/onshape_documents.html", context)

    doc_name = name_override if name_override else matched.name

    doc_ref = OnshapeDocumentRef(
        name=doc_name,
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
        element_type=element_type,
        auto_sync=True,
    )
    project.onshape.documents.append(doc_ref)
    save_project_config(project)

    context["onshape_documents"] = project.onshape.documents
    context["onshape_doc_success"] = f"Added '{doc_name}' ({element_type.replace('_', ' ')})"
    return templates.TemplateResponse("settings/onshape_documents.html", context)


@router.post("/settings/onshape/documents/remove", response_class=HTMLResponse)
async def settings_onshape_remove_document(request: Request, db: DbSession) -> HTMLResponse:
    """HTMX: remove an Onshape document from config."""
    from opal.config import get_active_project, get_active_settings
    from opal.project import save_project_config

    settings = get_active_settings()
    project = get_active_project()

    form = await request.form()
    document_id = str(form.get("document_id", ""))
    element_id = str(form.get("element_id", ""))

    context = get_base_context(request, db, "")
    context["onshape_enabled"] = settings.onshape_enabled
    context["onshape_doc_error"] = None
    context["onshape_doc_success"] = None

    if project:
        removed_name = None
        for doc in project.onshape.documents:
            if doc.document_id == document_id and doc.element_id == element_id:
                removed_name = doc.name
                break

        project.onshape.documents = [
            d
            for d in project.onshape.documents
            if not (d.document_id == document_id and d.element_id == element_id)
        ]
        save_project_config(project)

        if removed_name:
            context["onshape_doc_success"] = f"Removed '{removed_name}'"

    context["onshape_documents"] = project.onshape.documents if project else []
    return templates.TemplateResponse("settings/onshape_documents.html", context)


@router.post("/settings/onshape/sync/pull", response_class=HTMLResponse)
async def settings_onshape_sync_pull(request: Request, db: DbSession) -> HTMLResponse:
    """HTMX: trigger pull sync from Onshape, return HTML result."""
    import asyncio

    from opal.config import get_active_project, get_active_settings
    from opal.db.base import SessionLocal
    from opal.db.models.onshape_link import OnshapeSyncLog
    from opal.integrations.onshape.client import OnshapeClient
    from opal.integrations.onshape.sync import pull_sync

    settings = get_active_settings()
    project = get_active_project()

    # Resolve user from cookie
    user_id: int | None = None
    cookie_user_id = request.cookies.get("opal_user_id")
    if cookie_user_id:
        with contextlib.suppress(ValueError, TypeError):
            user_id = int(cookie_user_id)

    if not settings.onshape_enabled or not project or not project.onshape.documents:
        sync_logs = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc()).limit(10).all()
        return templates.TemplateResponse(
            "settings/onshape_sync_result.html",
            {
                "request": request,
                "status": "error",
                "summary": "Onshape not enabled or no documents configured",
                "error_message": None,
                "sync_logs": sync_logs,
            },
        )

    doc_refs = project.onshape.documents
    client = OnshapeClient(
        access_key=settings.onshape_access_key,
        secret_key=settings.onshape_secret_key,
        base_url=settings.onshape_base_url,
    )

    def _run_sync() -> list[dict[str, str | None]]:
        results: list[dict[str, str | None]] = []
        thread_db = SessionLocal()
        try:
            for doc_ref in doc_refs:
                sync_log = pull_sync(thread_db, client, doc_ref, user_id, "manual")
                results.append({"status": sync_log.status, "summary": sync_log.summary})
        finally:
            thread_db.close()
        return results

    try:
        results = await asyncio.to_thread(_run_sync)
    except Exception as e:
        db.commit()  # Release stale read snapshot so we see thread-committed data
        sync_logs = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc()).limit(10).all()
        return templates.TemplateResponse(
            "settings/onshape_sync_result.html",
            {
                "request": request,
                "status": "error",
                "summary": f"Pull sync failed: {e}",
                "error_message": str(e),
                "sync_logs": sync_logs,
            },
        )
    finally:
        client.close()

    # Combine results: worst status wins, summaries joined
    worst = "success"
    for r in results:
        if r["status"] == "error":
            worst = "error"
            break
        if r["status"] == "partial":
            worst = "partial"
    combined_summary = "\n".join(r["summary"] or "" for r in results)

    # Re-query sync logs — commit first to release stale read snapshot
    db.commit()
    sync_logs = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc()).limit(10).all()
    return templates.TemplateResponse(
        "settings/onshape_sync_result.html",
        {
            "request": request,
            "status": worst,
            "summary": combined_summary,
            "error_message": None,
            "sync_logs": sync_logs,
        },
    )


@router.post("/settings/onshape/sync/push", response_class=HTMLResponse)
async def settings_onshape_sync_push(request: Request, db: DbSession) -> HTMLResponse:
    """HTMX: trigger push sync to Onshape, return HTML result."""
    import asyncio

    from opal.config import get_active_project, get_active_settings
    from opal.db.base import SessionLocal
    from opal.db.models.onshape_link import OnshapeSyncLog
    from opal.integrations.onshape.client import OnshapeClient
    from opal.integrations.onshape.sync import push_sync

    settings = get_active_settings()
    project = get_active_project()

    user_id: int | None = None
    cookie_user_id = request.cookies.get("opal_user_id")
    if cookie_user_id:
        with contextlib.suppress(ValueError, TypeError):
            user_id = int(cookie_user_id)

    if not settings.onshape_enabled or not project or not project.onshape.documents:
        sync_logs = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc()).limit(10).all()
        return templates.TemplateResponse(
            "settings/onshape_sync_result.html",
            {
                "request": request,
                "status": "error",
                "summary": "Onshape not enabled or no documents configured",
                "error_message": None,
                "sync_logs": sync_logs,
            },
        )

    doc_refs = project.onshape.documents
    client = OnshapeClient(
        access_key=settings.onshape_access_key,
        secret_key=settings.onshape_secret_key,
        base_url=settings.onshape_base_url,
    )

    def _run_sync() -> list[dict[str, str | None]]:
        results: list[dict[str, str | None]] = []
        thread_db = SessionLocal()
        try:
            for doc_ref in doc_refs:
                sync_log = push_sync(thread_db, client, doc_ref, user_id, "manual")
                results.append({"status": sync_log.status, "summary": sync_log.summary})
        finally:
            thread_db.close()
        return results

    try:
        results = await asyncio.to_thread(_run_sync)
    except Exception as e:
        db.commit()  # Release stale read snapshot so we see thread-committed data
        sync_logs = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc()).limit(10).all()
        return templates.TemplateResponse(
            "settings/onshape_sync_result.html",
            {
                "request": request,
                "status": "error",
                "summary": f"Push sync failed: {e}",
                "error_message": str(e),
                "sync_logs": sync_logs,
            },
        )
    finally:
        client.close()

    # Combine results: worst status wins, summaries joined
    worst = "success"
    for r in results:
        if r["status"] == "error":
            worst = "error"
            break
        if r["status"] == "partial":
            worst = "partial"
    combined_summary = "\n".join(r["summary"] or "" for r in results)

    db.commit()  # Release stale read snapshot so we see thread-committed data
    sync_logs = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc()).limit(10).all()
    return templates.TemplateResponse(
        "settings/onshape_sync_result.html",
        {
            "request": request,
            "status": worst,
            "summary": combined_summary,
            "error_message": None,
            "sync_logs": sync_logs,
        },
    )


# ============ AUDIT LOG ============


@router.get("/audit", response_class=HTMLResponse)
async def audit_list(request: Request, db: DbSession) -> HTMLResponse:
    """Audit log list page."""
    from opal.db.models.audit import AuditLog

    context = get_base_context(request, db, "Audit Log - OPAL")

    # Get distinct table names for filter
    table_names = [
        row[0]
        for row in db.query(AuditLog.table_name).distinct().order_by(AuditLog.table_name).all()
    ]
    context["table_names"] = table_names

    return templates.TemplateResponse("audit/list.html", context)


@router.get("/audit/table", response_class=HTMLResponse)
async def audit_table(
    request: Request,
    db: DbSession,
    table_name: str | None = Query(None),
    action: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> HTMLResponse:
    """Audit log table rows (HTMX partial)."""
    from opal.db.models.audit import AuditLog

    query = db.query(AuditLog)

    if table_name:
        query = query.filter(AuditLog.table_name == table_name)
    if action:
        query = query.filter(AuditLog.action == action)
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=UTC)
            query = query.filter(AuditLog.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
            query = query.filter(AuditLog.timestamp < dt_to)
        except ValueError:
            pass

    entries = query.order_by(AuditLog.timestamp.desc()).limit(200).all()

    # Build user cache to avoid N+1
    user_ids = {e.user_id for e in entries if e.user_id}
    user_cache: dict[int, str] = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_cache = {u.id: u.name for u in users}

    # Annotate entries with helper data
    for entry in entries:
        entry._user_name = user_cache.get(entry.user_id) if entry.user_id else None
        entry._summary = _build_change_summary(entry)
        url_base = _TABLE_URL_MAP.get(entry.table_name)
        entry._url = f"{url_base}/{entry.record_id}" if url_base else None

    return templates.TemplateResponse(
        "audit/table_rows.html",
        {"request": request, "entries": entries},
    )


# ============ STYLEGUIDE ============


@router.get("/styleguide", response_class=HTMLResponse)
async def styleguide(request: Request, db: DbSession) -> HTMLResponse:
    """OPALkit component styleguide page."""
    context = get_base_context(request, db, "Styleguide - OPAL")
    return templates.TemplateResponse("opalkit/styleguide/index.html", context)

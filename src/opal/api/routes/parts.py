"""Parts management endpoints."""

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
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
    reorder_point: Decimal | None = None
    is_tooling: bool = False
    calibration_interval_days: int | None = None
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
    reorder_point: Decimal | None = None
    is_tooling: bool | None = None
    calibration_interval_days: int | None = None
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
    reorder_point: Decimal | None = None
    is_low_stock: bool = False
    is_tooling: bool = False
    calibration_interval_days: int | None = None
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

    total = total_qty or Decimal(0)
    is_low = bool(part.reorder_point is not None and total < part.reorder_point)

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
        reorder_point=part.reorder_point,
        is_low_stock=is_low,
        is_tooling=part.is_tooling,
        calibration_interval_days=part.calibration_interval_days,
        metadata=part.metadata_,
        total_quantity=total,
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
    low_stock: bool = Query(False, description="Only show parts below reorder point"),
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

    if low_stock:
        # Filter to parts with reorder_point set, where stock < reorder_point
        query = query.filter(Part.reorder_point.isnot(None))
        # We need to compute stock in a subquery
        stock_subq = (
            db.query(
                InventoryRecord.part_id,
                func.coalesce(func.sum(InventoryRecord.quantity), 0).label("total_qty"),
            )
            .group_by(InventoryRecord.part_id)
            .subquery()
        )
        query = (
            query.outerjoin(stock_subq, Part.id == stock_subq.c.part_id)
            .filter(func.coalesce(stock_subq.c.total_qty, 0) < Part.reorder_point)
        )

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
        reorder_point=part_in.reorder_point,
        is_tooling=part_in.is_tooling,
        calibration_interval_days=part_in.calibration_interval_days,
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


@router.get("/{part_id}/qrcode")
async def get_part_qrcode(
    db: DbSession,
    part_id: int,
    request: Request,
) -> Response:
    """Generate a QR code SVG for a part."""
    import io as _io

    import segno

    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")

    from opal.core.mri import encode_part_mri

    mri = encode_part_mri(part)
    qr = segno.make(mri, micro=False)
    buf = _io.BytesIO()
    qr.save(buf, kind="svg", scale=1, border=1, svgclass=None, lineclass=None)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


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


# ============ CSV Import ============

# Column header normalization mapping
_HEADER_ALIASES: dict[str, str] = {
    "name": "name",
    "part_name": "name",
    "external_pn": "external_pn",
    "external pn": "external_pn",
    "external_part_number": "external_pn",
    "external part number": "external_pn",
    "part_number": "external_pn",
    "part number": "external_pn",
    "manufacturer_pn": "external_pn",
    "description": "description",
    "category": "category",
    "tier": "tier",
    "unit_of_measure": "unit_of_measure",
    "unit of measure": "unit_of_measure",
    "unit": "unit_of_measure",
    "uom": "unit_of_measure",
    "tracking_type": "tracking_type",
    "tracking type": "tracking_type",
    "tracking": "tracking_type",
    "reorder_point": "reorder_point",
    "reorder point": "reorder_point",
}

# Columns to silently ignore (from CSV export format)
_IGNORE_COLUMNS = {"id", "internal_pn", "internal pn", "internal_part_number",
                    "total_quantity", "total quantity", "locations", "stock_qty",
                    "stock qty", "created_at", "updated_at"}


class ImportRowPreview(BaseModel):
    """Preview of a single CSV row."""

    row_number: int
    name: str | None = None
    external_pn: str | None = None
    tier: int | None = None
    category: str | None = None
    unit_of_measure: str | None = None
    tracking_type: str | None = None
    description: str | None = None
    reorder_point: float | None = None
    errors: list[str] = []
    warnings: list[str] = []
    valid: bool = True


class ImportPreviewResponse(BaseModel):
    """Response from import preview."""

    total_rows: int
    valid_rows: int
    error_rows: int
    warning_rows: int
    rows: list[ImportRowPreview]
    headers_found: list[str]


class ImportResult(BaseModel):
    """Response from actual import."""

    created: int
    skipped: int
    errors: list[str]


def _normalize_header(header: str) -> str | None:
    """Normalize a CSV column header to a known field name."""
    h = header.strip().lower().replace(" ", "_")
    if h in _IGNORE_COLUMNS or header.strip().lower() in _IGNORE_COLUMNS:
        return None
    return _HEADER_ALIASES.get(h) or _HEADER_ALIASES.get(header.strip().lower())


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(
    db: DbSession,
    file: UploadFile,
) -> ImportPreviewResponse:
    """Parse and validate a CSV file for parts import without creating anything."""
    # Read CSV with BOM handling
    content = await file.read()
    text_stream = io.StringIO(content.decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file has no headers")

    # Normalize headers
    header_map: dict[str, str | None] = {}
    for h in reader.fieldnames:
        header_map[h] = _normalize_header(h)

    headers_found = [v for v in header_map.values() if v]

    if "name" not in headers_found:
        raise HTTPException(status_code=400, detail="CSV must have a 'Name' column")

    # Collect existing parts for duplicate detection
    existing_names = {p.name.lower() for p in db.query(Part.name).filter(Part.deleted_at.is_(None)).all()}
    existing_external_pns = set()
    for row in db.query(Part.external_pn).filter(Part.deleted_at.is_(None), Part.external_pn.isnot(None)).all():
        existing_external_pns.add(row[0].lower())

    valid_tiers = {1, 2, 3, 4, 5}  # Reasonable tier range
    valid_tracking = {"bulk", "serialized"}

    rows: list[ImportRowPreview] = []
    for i, raw_row in enumerate(reader):
        if i >= 5000:
            break

        row_data: dict[str, str] = {}
        for csv_key, normalized_key in header_map.items():
            if normalized_key and csv_key in raw_row:
                row_data[normalized_key] = raw_row[csv_key].strip() if raw_row[csv_key] else ""

        preview = ImportRowPreview(row_number=i + 1)
        preview.name = row_data.get("name") or None
        preview.external_pn = row_data.get("external_pn") or None
        preview.category = row_data.get("category") or None
        preview.unit_of_measure = row_data.get("unit_of_measure") or None
        preview.tracking_type = row_data.get("tracking_type") or None
        preview.description = row_data.get("description") or None

        # Parse tier
        tier_str = row_data.get("tier", "").strip()
        if tier_str:
            try:
                preview.tier = int(tier_str)
            except ValueError:
                preview.errors.append(f"Invalid tier: '{tier_str}'")

        # Parse reorder_point
        rp_str = row_data.get("reorder_point", "").strip()
        if rp_str:
            try:
                preview.reorder_point = float(rp_str)
            except ValueError:
                preview.errors.append(f"Invalid reorder_point: '{rp_str}'")

        # Validate required fields
        if not preview.name:
            preview.errors.append("Name is required")

        if preview.tier is not None and preview.tier not in valid_tiers:
            preview.errors.append(f"Tier must be 1-5, got {preview.tier}")

        if preview.tracking_type and preview.tracking_type.lower() not in valid_tracking:
            preview.errors.append(f"Tracking type must be 'bulk' or 'serialized', got '{preview.tracking_type}'")

        # Check duplicates
        if preview.name and preview.name.lower() in existing_names:
            preview.warnings.append(f"Part with name '{preview.name}' already exists")
        if preview.external_pn and preview.external_pn.lower() in existing_external_pns:
            preview.warnings.append(f"Part with external PN '{preview.external_pn}' already exists")

        preview.valid = len(preview.errors) == 0
        rows.append(preview)

    return ImportPreviewResponse(
        total_rows=len(rows),
        valid_rows=sum(1 for r in rows if r.valid),
        error_rows=sum(1 for r in rows if not r.valid),
        warning_rows=sum(1 for r in rows if r.warnings),
        rows=rows,
        headers_found=headers_found,
    )


class ImportRequest(BaseModel):
    """Request to perform the actual import."""

    rows: list[PartCreate]
    skip_duplicates: bool = True


@router.post("/import", response_model=ImportResult)
async def import_parts(
    db: DbSession,
    import_in: ImportRequest,
    user_id: CurrentUserId,
) -> ImportResult:
    """Import parts from validated data. Call preview first to validate."""
    if len(import_in.rows) > 5000:
        raise HTTPException(status_code=400, detail="Maximum 5000 rows per import")

    existing_names = {p.name.lower() for p in db.query(Part.name).filter(Part.deleted_at.is_(None)).all()}

    created = 0
    skipped = 0
    errors: list[str] = []

    for i, part_in in enumerate(import_in.rows):
        # Skip duplicates if requested
        if import_in.skip_duplicates and part_in.name.lower() in existing_names:
            skipped += 1
            continue

        try:
            internal_pn = generate_internal_pn(db, part_in.tier)
            part = Part(
                name=part_in.name,
                internal_pn=internal_pn,
                external_pn=part_in.external_pn,
                description=part_in.description,
                category=part_in.category,
                unit_of_measure=part_in.unit_of_measure or "EA",
                tracking_type=part_in.tracking_type or "bulk",
                tier=part_in.tier,
                reorder_point=part_in.reorder_point,
                metadata_=part_in.metadata,
            )
            db.add(part)
            db.flush()
            log_create(db, part, user_id)
            existing_names.add(part_in.name.lower())
            created += 1
        except Exception as e:
            errors.append(f"Row {i + 1}: {str(e)}")

    db.commit()

    return ImportResult(created=created, skipped=skipped, errors=errors)

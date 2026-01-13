"""Inventory management endpoints."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func

from opal.api.deps import CurrentUserId, DbSession, PaginationParams
from opal.core.audit import log_create, log_update, get_model_dict
from opal.core.inventory import generate_opal_number
from opal.db.models import InventoryRecord, Part, StockTestResult, StockTransfer, TestTemplate
from opal.db.models.inventory import SourceType, TestResult, TransferStatus

router = APIRouter()


class InventoryCreate(BaseModel):
    """Schema for creating an inventory record."""

    part_id: int
    quantity: Decimal
    location: str
    lot_number: str | None = None


class InventoryUpdate(BaseModel):
    """Schema for updating an inventory record."""

    quantity: Decimal | None = None
    location: str | None = None
    lot_number: str | None = None


class InventoryAdjust(BaseModel):
    """Schema for adjusting inventory quantity."""

    adjustment: Decimal  # Positive to add, negative to subtract
    reason: str | None = None


class InventoryCount(BaseModel):
    """Schema for recording a physical count."""

    counted_quantity: Decimal


class InventoryResponse(BaseModel):
    """Schema for inventory response."""

    id: int
    part_id: int
    part_name: str
    part_external_pn: str | None
    quantity: Decimal
    location: str
    lot_number: str | None
    last_counted_at: str | None
    opal_number: str | None
    source_type: str | None
    source_purchase_line_id: int | None
    source_production_id: int | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class InventoryListResponse(BaseModel):
    """Schema for inventory list response."""

    items: list[InventoryResponse]
    total: int


class LocationSummary(BaseModel):
    """Summary of inventory at a location."""

    location: str
    total_records: int
    total_parts: int


def inventory_to_response(record: InventoryRecord) -> InventoryResponse:
    """Convert inventory record to response."""
    source_type = None
    if record.source_type:
        source_type = record.source_type.value if hasattr(record.source_type, 'value') else record.source_type

    return InventoryResponse(
        id=record.id,
        part_id=record.part_id,
        part_name=record.part.name,
        part_external_pn=record.part.external_pn,
        quantity=record.quantity,
        location=record.location,
        lot_number=record.lot_number,
        last_counted_at=record.last_counted_at.isoformat() if record.last_counted_at else None,
        opal_number=record.opal_number,
        source_type=source_type,
        source_purchase_line_id=record.source_purchase_line_id,
        source_production_id=record.source_production_id,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


@router.get("", response_model=InventoryListResponse)
async def list_inventory(
    db: DbSession,
    pagination: PaginationParams,
    part_id: int | None = Query(None, description="Filter by part ID"),
    location: str | None = Query(None, description="Filter by location"),
    lot_number: str | None = Query(None, description="Filter by lot number"),
) -> InventoryListResponse:
    """List inventory records with optional filtering."""
    query = db.query(InventoryRecord).join(Part).filter(Part.deleted_at.is_(None))

    if part_id:
        query = query.filter(InventoryRecord.part_id == part_id)
    if location:
        query = query.filter(InventoryRecord.location == location)
    if lot_number:
        query = query.filter(InventoryRecord.lot_number == lot_number)

    total = query.count()
    records = (
        query.order_by(InventoryRecord.location, InventoryRecord.part_id)
        .offset(pagination.skip)
        .limit(pagination.limit)
        .all()
    )

    return InventoryListResponse(
        items=[inventory_to_response(r) for r in records],
        total=total,
    )


@router.get("/locations")
async def list_locations(db: DbSession) -> list[LocationSummary]:
    """List all inventory locations with summary."""
    results = (
        db.query(
            InventoryRecord.location,
            func.count(InventoryRecord.id).label("total_records"),
            func.count(func.distinct(InventoryRecord.part_id)).label("total_parts"),
        )
        .join(Part)
        .filter(Part.deleted_at.is_(None))
        .group_by(InventoryRecord.location)
        .order_by(InventoryRecord.location)
        .all()
    )

    return [
        LocationSummary(
            location=r.location,
            total_records=r.total_records,
            total_parts=r.total_parts,
        )
        for r in results
    ]


# ============ OPAL Number Lookup ============


class OpalHistoryEntry(BaseModel):
    """Entry in OPAL number history."""

    event_type: str  # "created", "consumed", "transferred", "counted", "adjusted"
    timestamp: str
    details: dict


class OpalHistoryResponse(BaseModel):
    """Response for OPAL number history."""

    opal_number: str
    inventory: InventoryResponse
    history: list[OpalHistoryEntry]


@router.get("/opal/{opal_number}", response_model=InventoryResponse)
async def get_inventory_by_opal(
    opal_number: str,
    db: DbSession,
) -> InventoryResponse:
    """Look up an inventory record by its OPAL number."""
    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(
            InventoryRecord.opal_number == opal_number,
            Part.deleted_at.is_(None)
        )
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory record with OPAL number {opal_number} not found",
        )

    return inventory_to_response(record)


@router.get("/opal/{opal_number}/history", response_model=OpalHistoryResponse)
async def get_opal_history(
    opal_number: str,
    db: DbSession,
) -> OpalHistoryResponse:
    """Get the full lifecycle history of an item by OPAL number.

    Returns creation source, consumptions, transfers, counts, etc.
    """
    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(
            InventoryRecord.opal_number == opal_number,
            Part.deleted_at.is_(None)
        )
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory record with OPAL number {opal_number} not found",
        )

    history: list[OpalHistoryEntry] = []

    # Creation event
    source_details: dict = {"source_type": record.source_type.value if record.source_type else "unknown"}
    if record.source_purchase_line_id:
        source_details["purchase_line_id"] = record.source_purchase_line_id
        if record.source_purchase_line:
            source_details["purchase_id"] = record.source_purchase_line.purchase_id
    if record.source_production_id:
        source_details["production_id"] = record.source_production_id

    history.append(OpalHistoryEntry(
        event_type="created",
        timestamp=record.created_at.isoformat(),
        details=source_details,
    ))

    # Consumptions
    for consumption in record.consumptions:
        history.append(OpalHistoryEntry(
            event_type="consumed",
            timestamp=consumption.created_at.isoformat(),
            details={
                "quantity": float(consumption.quantity),
                "consumption_type": consumption.consumption_type.value if hasattr(consumption.consumption_type, 'value') else consumption.consumption_type,
                "usage_type": consumption.usage_type.value if hasattr(consumption.usage_type, 'value') else consumption.usage_type,
                "procedure_instance_id": consumption.procedure_instance_id,
                "step_execution_id": consumption.step_execution_id,
            },
        ))

    # Outgoing transfers (from this record)
    for transfer in record.outgoing_transfers:
        history.append(OpalHistoryEntry(
            event_type="transferred_out",
            timestamp=transfer.transferred_at.isoformat() if transfer.transferred_at else transfer.created_at.isoformat(),
            details={
                "quantity": float(transfer.quantity),
                "to_location": transfer.target_location,
            },
        ))

    # Incoming transfers (to this record) - this record was created from a transfer
    for transfer in record.incoming_transfers:
        history.append(OpalHistoryEntry(
            event_type="transferred_in",
            timestamp=transfer.transferred_at.isoformat() if transfer.transferred_at else transfer.created_at.isoformat(),
            details={
                "quantity": float(transfer.quantity),
                "from_location": transfer.source_location,
            },
        ))

    # Physical counts
    if record.last_counted_at:
        history.append(OpalHistoryEntry(
            event_type="counted",
            timestamp=record.last_counted_at.isoformat(),
            details={"quantity": float(record.quantity)},
        ))

    # Sort history by timestamp
    history.sort(key=lambda h: h.timestamp)

    return OpalHistoryResponse(
        opal_number=opal_number,
        inventory=inventory_to_response(record),
        history=history,
    )


@router.post("", response_model=InventoryResponse, status_code=status.HTTP_201_CREATED)
async def create_inventory(
    db: DbSession,
    inv_in: InventoryCreate,
    user_id: CurrentUserId,
) -> InventoryResponse:
    """Create a new inventory record with OPAL number for traceability."""
    # Verify part exists
    part = db.query(Part).filter(Part.id == inv_in.part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {inv_in.part_id} not found",
        )

    # Each inventory record gets a unique OPAL number for traceability
    opal_number = generate_opal_number(db)

    record = InventoryRecord(
        part_id=inv_in.part_id,
        quantity=inv_in.quantity,
        location=inv_in.location,
        lot_number=inv_in.lot_number,
        opal_number=opal_number,
        source_type=SourceType.MANUAL,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    log_create(db, record, user_id)
    db.commit()

    return inventory_to_response(record)


@router.get("/{inventory_id}", response_model=InventoryResponse)
async def get_inventory(
    db: DbSession,
    inventory_id: int,
) -> InventoryResponse:
    """Get a specific inventory record."""
    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(InventoryRecord.id == inventory_id, Part.deleted_at.is_(None))
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory record {inventory_id} not found",
        )

    return inventory_to_response(record)


@router.patch("/{inventory_id}", response_model=InventoryResponse)
async def update_inventory(
    db: DbSession,
    inventory_id: int,
    inv_in: InventoryUpdate,
    user_id: CurrentUserId,
) -> InventoryResponse:
    """Update an inventory record."""
    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(InventoryRecord.id == inventory_id, Part.deleted_at.is_(None))
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory record {inventory_id} not found",
        )

    old_values = get_model_dict(record)

    update_data = inv_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    db.commit()
    db.refresh(record)

    log_update(db, record, old_values, user_id)
    db.commit()

    return inventory_to_response(record)


@router.post("/{inventory_id}/adjust", response_model=InventoryResponse)
async def adjust_inventory(
    db: DbSession,
    inventory_id: int,
    adjust_in: InventoryAdjust,
    user_id: CurrentUserId,
) -> InventoryResponse:
    """Adjust inventory quantity (add or subtract)."""
    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(InventoryRecord.id == inventory_id, Part.deleted_at.is_(None))
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory record {inventory_id} not found",
        )

    old_values = get_model_dict(record)

    new_quantity = record.quantity + adjust_in.adjustment
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Adjustment would result in negative quantity ({new_quantity})",
        )

    record.quantity = new_quantity
    db.commit()
    db.refresh(record)

    log_update(db, record, old_values, user_id)
    db.commit()

    return inventory_to_response(record)


@router.post("/{inventory_id}/count", response_model=InventoryResponse)
async def record_count(
    db: DbSession,
    inventory_id: int,
    count_in: InventoryCount,
    user_id: CurrentUserId,
) -> InventoryResponse:
    """Record a physical count, updating quantity and timestamp."""
    record = (
        db.query(InventoryRecord)
        .join(Part)
        .filter(InventoryRecord.id == inventory_id, Part.deleted_at.is_(None))
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory record {inventory_id} not found",
        )

    old_values = get_model_dict(record)

    record.quantity = count_in.counted_quantity
    record.last_counted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)

    log_update(db, record, old_values, user_id)
    db.commit()

    return inventory_to_response(record)


@router.delete("/{inventory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory(
    db: DbSession,
    inventory_id: int,
    user_id: CurrentUserId,
) -> None:
    """Delete an inventory record."""
    record = db.query(InventoryRecord).filter(InventoryRecord.id == inventory_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory record {inventory_id} not found",
        )

    db.delete(record)
    db.commit()


# ============ Test Results ============


class TestTemplateCreate(BaseModel):
    """Schema for creating a test template."""

    name: str
    description: str | None = None
    required: bool = False
    test_type: str = "boolean"  # boolean, numeric, text
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    unit: str | None = None
    sort_order: int = 0


class TestTemplateResponse(BaseModel):
    """Schema for test template response."""

    id: int
    part_id: int
    name: str
    description: str | None
    required: bool
    test_type: str
    min_value: Decimal | None
    max_value: Decimal | None
    unit: str | None
    sort_order: int
    created_at: str

    model_config = {"from_attributes": True}


class TestResultCreate(BaseModel):
    """Schema for creating a test result."""

    test_name: str
    template_id: int | None = None
    result: str = "pending"  # pass, fail, pending
    value: str | None = None
    notes: str | None = None


class TestResultResponse(BaseModel):
    """Schema for test result response."""

    id: int
    inventory_record_id: int
    template_id: int | None
    test_name: str
    result: str
    value: str | None
    notes: str | None
    tested_at: str | None
    tested_by_id: int | None
    created_at: str

    model_config = {"from_attributes": True}


# Test Templates (Part-level)


@router.get("/parts/{part_id}/test-templates", response_model=list[TestTemplateResponse])
async def list_test_templates(
    part_id: int,
    db: DbSession,
) -> list[TestTemplateResponse]:
    """List all test templates for a part."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")

    templates = (
        db.query(TestTemplate)
        .filter(TestTemplate.part_id == part_id)
        .order_by(TestTemplate.sort_order)
        .all()
    )

    return [
        TestTemplateResponse(
            id=t.id,
            part_id=t.part_id,
            name=t.name,
            description=t.description,
            required=t.required,
            test_type=t.test_type,
            min_value=t.min_value,
            max_value=t.max_value,
            unit=t.unit,
            sort_order=t.sort_order,
            created_at=t.created_at.isoformat(),
        )
        for t in templates
    ]


@router.post("/parts/{part_id}/test-templates", response_model=TestTemplateResponse, status_code=201)
async def create_test_template(
    part_id: int,
    data: TestTemplateCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> TestTemplateResponse:
    """Create a test template for a part."""
    part = db.query(Part).filter(Part.id == part_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")

    template = TestTemplate(
        part_id=part_id,
        name=data.name,
        description=data.description,
        required=data.required,
        test_type=data.test_type,
        min_value=data.min_value,
        max_value=data.max_value,
        unit=data.unit,
        sort_order=data.sort_order,
    )
    db.add(template)
    log_create(db, template, user_id)
    db.commit()
    db.refresh(template)

    return TestTemplateResponse(
        id=template.id,
        part_id=template.part_id,
        name=template.name,
        description=template.description,
        required=template.required,
        test_type=template.test_type,
        min_value=template.min_value,
        max_value=template.max_value,
        unit=template.unit,
        sort_order=template.sort_order,
        created_at=template.created_at.isoformat(),
    )


@router.delete("/parts/{part_id}/test-templates/{template_id}", status_code=204)
async def delete_test_template(
    part_id: int,
    template_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Delete a test template."""
    template = (
        db.query(TestTemplate)
        .filter(TestTemplate.id == template_id, TestTemplate.part_id == part_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Test template not found")

    db.delete(template)
    db.commit()


# Stock Test Results (Inventory-level)


@router.get("/{inventory_id}/tests", response_model=list[TestResultResponse])
async def list_test_results(
    inventory_id: int,
    db: DbSession,
) -> list[TestResultResponse]:
    """List all test results for an inventory record."""
    record = db.query(InventoryRecord).filter(InventoryRecord.id == inventory_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Inventory record {inventory_id} not found")

    results = (
        db.query(StockTestResult)
        .filter(StockTestResult.inventory_record_id == inventory_id)
        .order_by(StockTestResult.created_at.desc())
        .all()
    )

    return [
        TestResultResponse(
            id=r.id,
            inventory_record_id=r.inventory_record_id,
            template_id=r.template_id,
            test_name=r.test_name,
            result=r.result.value if hasattr(r.result, 'value') else r.result,
            value=r.value,
            notes=r.notes,
            tested_at=r.tested_at.isoformat() if r.tested_at else None,
            tested_by_id=r.tested_by_id,
            created_at=r.created_at.isoformat(),
        )
        for r in results
    ]


@router.post("/{inventory_id}/tests", response_model=TestResultResponse, status_code=201)
async def create_test_result(
    inventory_id: int,
    data: TestResultCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> TestResultResponse:
    """Add a test result to an inventory record."""
    record = db.query(InventoryRecord).filter(InventoryRecord.id == inventory_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Inventory record {inventory_id} not found")

    # Validate result value
    try:
        result_enum = TestResult(data.result)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid result: {data.result}")

    # If template_id provided, validate it
    if data.template_id:
        template = db.query(TestTemplate).filter(TestTemplate.id == data.template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail=f"Test template {data.template_id} not found")

    test_result = StockTestResult(
        inventory_record_id=inventory_id,
        template_id=data.template_id,
        test_name=data.test_name,
        result=result_enum,
        value=data.value,
        notes=data.notes,
        tested_at=datetime.now(timezone.utc) if result_enum != TestResult.PENDING else None,
        tested_by_id=user_id,
    )
    db.add(test_result)
    log_create(db, test_result, user_id)
    db.commit()
    db.refresh(test_result)

    return TestResultResponse(
        id=test_result.id,
        inventory_record_id=test_result.inventory_record_id,
        template_id=test_result.template_id,
        test_name=test_result.test_name,
        result=test_result.result.value if hasattr(test_result.result, 'value') else test_result.result,
        value=test_result.value,
        notes=test_result.notes,
        tested_at=test_result.tested_at.isoformat() if test_result.tested_at else None,
        tested_by_id=test_result.tested_by_id,
        created_at=test_result.created_at.isoformat(),
    )


@router.patch("/{inventory_id}/tests/{test_id}", response_model=TestResultResponse)
async def update_test_result(
    inventory_id: int,
    test_id: int,
    data: TestResultCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> TestResultResponse:
    """Update a test result."""
    test_result = (
        db.query(StockTestResult)
        .filter(
            StockTestResult.id == test_id,
            StockTestResult.inventory_record_id == inventory_id
        )
        .first()
    )
    if not test_result:
        raise HTTPException(status_code=404, detail="Test result not found")

    old_values = get_model_dict(test_result)

    # Validate result value
    try:
        result_enum = TestResult(data.result)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid result: {data.result}")

    test_result.test_name = data.test_name
    test_result.result = result_enum
    test_result.value = data.value
    test_result.notes = data.notes

    # Set tested_at when result changes from pending
    if result_enum != TestResult.PENDING and not test_result.tested_at:
        test_result.tested_at = datetime.now(timezone.utc)
        test_result.tested_by_id = user_id

    log_update(db, test_result, old_values, user_id)
    db.commit()
    db.refresh(test_result)

    return TestResultResponse(
        id=test_result.id,
        inventory_record_id=test_result.inventory_record_id,
        template_id=test_result.template_id,
        test_name=test_result.test_name,
        result=test_result.result.value if hasattr(test_result.result, 'value') else test_result.result,
        value=test_result.value,
        notes=test_result.notes,
        tested_at=test_result.tested_at.isoformat() if test_result.tested_at else None,
        tested_by_id=test_result.tested_by_id,
        created_at=test_result.created_at.isoformat(),
    )


@router.delete("/{inventory_id}/tests/{test_id}", status_code=204)
async def delete_test_result(
    inventory_id: int,
    test_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Delete a test result."""
    test_result = (
        db.query(StockTestResult)
        .filter(
            StockTestResult.id == test_id,
            StockTestResult.inventory_record_id == inventory_id
        )
        .first()
    )
    if not test_result:
        raise HTTPException(status_code=404, detail="Test result not found")

    db.delete(test_result)
    db.commit()


@router.get("/{inventory_id}/test-status")
async def get_test_status(
    inventory_id: int,
    db: DbSession,
) -> dict:
    """Get overall test status for an inventory record.

    Returns counts of passed, failed, and pending tests,
    plus whether all required tests have passed.
    """
    record = db.query(InventoryRecord).filter(InventoryRecord.id == inventory_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Inventory record {inventory_id} not found")

    # Get all test results
    results = (
        db.query(StockTestResult)
        .filter(StockTestResult.inventory_record_id == inventory_id)
        .all()
    )

    # Count by status
    passed = sum(1 for r in results if (r.result.value if hasattr(r.result, 'value') else r.result) == 'pass')
    failed = sum(1 for r in results if (r.result.value if hasattr(r.result, 'value') else r.result) == 'fail')
    pending = sum(1 for r in results if (r.result.value if hasattr(r.result, 'value') else r.result) == 'pending')

    # Check required tests from templates
    required_templates = (
        db.query(TestTemplate)
        .filter(TestTemplate.part_id == record.part_id, TestTemplate.required == True)  # noqa: E712
        .all()
    )

    required_passed = True
    missing_required = []
    for template in required_templates:
        template_results = [r for r in results if r.template_id == template.id]
        if not template_results:
            required_passed = False
            missing_required.append(template.name)
        elif not any((r.result.value if hasattr(r.result, 'value') else r.result) == 'pass' for r in template_results):
            required_passed = False
            missing_required.append(template.name)

    return {
        "inventory_record_id": inventory_id,
        "total_tests": len(results),
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "required_tests_passed": required_passed,
        "missing_required_tests": missing_required,
        "overall_status": "pass" if failed == 0 and pending == 0 and required_passed and len(results) > 0 else (
            "fail" if failed > 0 else "pending"
        ),
    }


# ============ Stock Transfers ============


class TransferCreate(BaseModel):
    """Schema for creating a stock transfer."""

    source_inventory_id: int
    target_location: str
    quantity: Decimal
    target_lot_number: str | None = None
    notes: str | None = None


class TransferResponse(BaseModel):
    """Schema for transfer response."""

    id: int
    part_id: int
    part_name: str
    quantity: Decimal
    source_location: str
    target_location: str
    source_lot_number: str | None
    target_lot_number: str | None
    status: str
    notes: str | None
    transferred_by_id: int | None
    transferred_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/transfer", response_model=TransferResponse, status_code=201)
async def transfer_stock(
    data: TransferCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> TransferResponse:
    """Transfer stock from one location to another.

    This deducts from the source inventory and adds to the target location.
    If the target location doesn't exist for this part/lot combo, it's created.
    """
    # Get source inventory
    source = db.query(InventoryRecord).filter(InventoryRecord.id == data.source_inventory_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source inventory record not found")

    # Validate quantity
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Transfer quantity must be positive")

    if float(source.quantity) < float(data.quantity):
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient quantity at source (have {source.quantity}, need {data.quantity})"
        )

    # Check if transferring to same location
    target_lot = data.target_lot_number or source.lot_number
    if source.location == data.target_location and source.lot_number == target_lot:
        raise HTTPException(status_code=400, detail="Cannot transfer to same location with same lot number")

    # Find or create target inventory record
    target = (
        db.query(InventoryRecord)
        .filter(
            InventoryRecord.part_id == source.part_id,
            InventoryRecord.location == data.target_location,
            InventoryRecord.lot_number == target_lot,
        )
        .first()
    )

    if target:
        target.quantity = Decimal(str(target.quantity)) + data.quantity
    else:
        target = InventoryRecord(
            part_id=source.part_id,
            quantity=data.quantity,
            location=data.target_location,
            lot_number=target_lot,
        )
        db.add(target)
        db.flush()

    # Deduct from source
    source.quantity = Decimal(str(source.quantity)) - data.quantity

    # Create transfer record
    transfer = StockTransfer(
        source_inventory_id=source.id,
        target_inventory_id=target.id,
        part_id=source.part_id,
        quantity=data.quantity,
        source_location=source.location,
        target_location=data.target_location,
        source_lot_number=source.lot_number,
        target_lot_number=target_lot,
        status=TransferStatus.COMPLETED,
        notes=data.notes,
        transferred_by_id=user_id,
        transferred_at=datetime.now(timezone.utc),
    )
    db.add(transfer)
    log_create(db, transfer, user_id)
    db.commit()
    db.refresh(transfer)

    return TransferResponse(
        id=transfer.id,
        part_id=transfer.part_id,
        part_name=source.part.name,
        quantity=transfer.quantity,
        source_location=transfer.source_location,
        target_location=transfer.target_location,
        source_lot_number=transfer.source_lot_number,
        target_lot_number=transfer.target_lot_number,
        status=transfer.status.value if hasattr(transfer.status, 'value') else transfer.status,
        notes=transfer.notes,
        transferred_by_id=transfer.transferred_by_id,
        transferred_at=transfer.transferred_at.isoformat() if transfer.transferred_at else None,
        created_at=transfer.created_at.isoformat(),
    )


@router.get("/transfers", response_model=list[TransferResponse])
async def list_transfers(
    db: DbSession,
    part_id: int | None = Query(None),
    location: str | None = Query(None, description="Filter by source or target location"),
    limit: int = Query(50, ge=1, le=200),
) -> list[TransferResponse]:
    """List stock transfers with optional filters."""
    query = db.query(StockTransfer).join(Part, StockTransfer.part_id == Part.id)

    if part_id:
        query = query.filter(StockTransfer.part_id == part_id)
    if location:
        query = query.filter(
            (StockTransfer.source_location == location) |
            (StockTransfer.target_location == location)
        )

    transfers = query.order_by(StockTransfer.created_at.desc()).limit(limit).all()

    return [
        TransferResponse(
            id=t.id,
            part_id=t.part_id,
            part_name=t.part.name,
            quantity=t.quantity,
            source_location=t.source_location,
            target_location=t.target_location,
            source_lot_number=t.source_lot_number,
            target_lot_number=t.target_lot_number,
            status=t.status.value if hasattr(t.status, 'value') else t.status,
            notes=t.notes,
            transferred_by_id=t.transferred_by_id,
            transferred_at=t.transferred_at.isoformat() if t.transferred_at else None,
            created_at=t.created_at.isoformat(),
        )
        for t in transfers
    ]


@router.get("/transfers/{transfer_id}", response_model=TransferResponse)
async def get_transfer(
    transfer_id: int,
    db: DbSession,
) -> TransferResponse:
    """Get a specific stock transfer."""
    transfer = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    return TransferResponse(
        id=transfer.id,
        part_id=transfer.part_id,
        part_name=transfer.part.name,
        quantity=transfer.quantity,
        source_location=transfer.source_location,
        target_location=transfer.target_location,
        source_lot_number=transfer.source_lot_number,
        target_lot_number=transfer.target_lot_number,
        status=transfer.status.value if hasattr(transfer.status, 'value') else transfer.status,
        notes=transfer.notes,
        transferred_by_id=transfer.transferred_by_id,
        transferred_at=transfer.transferred_at.isoformat() if transfer.transferred_at else None,
        created_at=transfer.created_at.isoformat(),
    )

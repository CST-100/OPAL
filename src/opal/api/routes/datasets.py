"""Datasets API routes."""

import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_delete, log_update, get_model_dict
from opal.db.models.dataset import Dataset, DataPoint

router = APIRouter(prefix="/datasets", tags=["datasets"])


# ============ Schemas ============


class DataPointResponse(BaseModel):
    """Data point response."""

    id: int
    dataset_id: int
    recorded_at: datetime
    values: dict[str, Any]
    step_execution_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetResponse(BaseModel):
    """Dataset response."""

    id: int
    name: str
    description: str | None = None
    data_schema: dict[str, Any] = Field(serialization_alias="schema")
    procedure_id: int | None = None
    point_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class DatasetDetailResponse(DatasetResponse):
    """Dataset with data points."""

    data_points: list[DataPointResponse] = []


class DatasetListResponse(BaseModel):
    """Paginated dataset list."""

    items: list[DatasetResponse]
    total: int
    page: int
    page_size: int


class DatasetCreate(BaseModel):
    """Create dataset request."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    data_schema: dict[str, Any] = Field(..., alias="schema", description="Schema defining fields and types")
    procedure_id: int | None = None

    model_config = {"populate_by_name": True}


class DatasetUpdate(BaseModel):
    """Update dataset request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    data_schema: dict[str, Any] | None = Field(None, alias="schema")
    procedure_id: int | None = None

    model_config = {"populate_by_name": True}


class DataPointCreate(BaseModel):
    """Create data point request."""

    recorded_at: datetime | None = None
    values: dict[str, Any]
    step_execution_id: int | None = None


class ChartDataResponse(BaseModel):
    """Chart.js compatible data response."""

    labels: list[str]
    datasets: list[dict[str, Any]]


# ============ Dataset CRUD ============


def _dataset_to_response(dataset: Dataset) -> DatasetResponse:
    """Convert Dataset model to response."""
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        data_schema=dataset.schema,
        procedure_id=dataset.procedure_id,
        point_count=len(dataset.data_points),
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


@router.get("", response_model=DatasetListResponse)
async def list_datasets(
    db: DbSession,
    search: str | None = Query(None),
    procedure_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> DatasetListResponse:
    """List datasets with optional filters."""
    query = db.query(Dataset).filter(Dataset.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(Dataset.name.ilike(search_term))

    if procedure_id:
        query = query.filter(Dataset.procedure_id == procedure_id)

    total = query.count()

    datasets = (
        query.order_by(Dataset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return DatasetListResponse(
        items=[_dataset_to_response(d) for d in datasets],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    data: DatasetCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> DatasetResponse:
    """Create a new dataset."""
    dataset = Dataset(
        name=data.name,
        description=data.description,
        schema=data.data_schema,
        procedure_id=data.procedure_id,
    )
    db.add(dataset)
    db.flush()

    log_create(db, dataset, user_id)
    db.commit()
    db.refresh(dataset)

    return _dataset_to_response(dataset)


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
async def get_dataset(
    dataset_id: int,
    db: DbSession,
    include_points: bool = Query(True),
    limit_points: int = Query(100, ge=1, le=1000),
) -> DatasetDetailResponse:
    """Get dataset by ID with optional data points."""
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    points = []
    if include_points:
        points = (
            db.query(DataPoint)
            .filter(DataPoint.dataset_id == dataset_id)
            .order_by(DataPoint.recorded_at.desc())
            .limit(limit_points)
            .all()
        )

    return DatasetDetailResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        data_schema=dataset.schema,
        procedure_id=dataset.procedure_id,
        point_count=len(dataset.data_points),
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        data_points=[
            DataPointResponse(
                id=p.id,
                dataset_id=p.dataset_id,
                recorded_at=p.recorded_at,
                values=p.values,
                step_execution_id=p.step_execution_id,
                created_at=p.created_at,
            )
            for p in points
        ],
    )


@router.patch("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: int,
    data: DatasetUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> DatasetResponse:
    """Update a dataset."""
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    old_values = get_model_dict(dataset)

    if data.name is not None:
        dataset.name = data.name
    if data.description is not None:
        dataset.description = data.description
    if data.data_schema is not None:
        dataset.schema = data.data_schema
    if data.procedure_id is not None:
        dataset.procedure_id = data.procedure_id

    log_update(db, dataset, old_values, user_id)
    db.commit()
    db.refresh(dataset)

    return _dataset_to_response(dataset)


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Soft delete a dataset."""
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    dataset.deleted_at = datetime.now(timezone.utc)
    log_delete(db, dataset, user_id)
    db.commit()


# ============ Data Points ============


@router.post("/{dataset_id}/points", response_model=DataPointResponse, status_code=201)
async def add_data_point(
    dataset_id: int,
    data: DataPointCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> DataPointResponse:
    """Add a data point to a dataset."""
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    recorded_at = data.recorded_at or datetime.now(timezone.utc)

    point = DataPoint(
        dataset_id=dataset_id,
        recorded_at=recorded_at,
        values=data.values,
        step_execution_id=data.step_execution_id,
    )
    db.add(point)
    db.commit()
    db.refresh(point)

    return DataPointResponse(
        id=point.id,
        dataset_id=point.dataset_id,
        recorded_at=point.recorded_at,
        values=point.values,
        step_execution_id=point.step_execution_id,
        created_at=point.created_at,
    )


@router.get("/{dataset_id}/points", response_model=list[DataPointResponse])
async def list_data_points(
    dataset_id: int,
    db: DbSession,
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[DataPointResponse]:
    """List data points for a dataset."""
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    query = db.query(DataPoint).filter(DataPoint.dataset_id == dataset_id)

    if start_date:
        query = query.filter(DataPoint.recorded_at >= start_date)
    if end_date:
        query = query.filter(DataPoint.recorded_at <= end_date)

    points = (
        query.order_by(DataPoint.recorded_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        DataPointResponse(
            id=p.id,
            dataset_id=p.dataset_id,
            recorded_at=p.recorded_at,
            values=p.values,
            step_execution_id=p.step_execution_id,
            created_at=p.created_at,
        )
        for p in points
    ]


@router.delete("/{dataset_id}/points/{point_id}", status_code=204)
async def delete_data_point(
    dataset_id: int,
    point_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Delete a data point."""
    point = (
        db.query(DataPoint)
        .filter(DataPoint.id == point_id, DataPoint.dataset_id == dataset_id)
        .first()
    )
    if not point:
        raise HTTPException(status_code=404, detail="Data point not found")

    db.delete(point)
    db.commit()


# ============ Chart Data ============


@router.get("/{dataset_id}/chart", response_model=ChartDataResponse)
async def get_chart_data(
    dataset_id: int,
    db: DbSession,
    field: str = Query(..., description="Field name from schema to chart"),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> ChartDataResponse:
    """Get chart-ready data for a specific field.

    Returns data in Chart.js compatible format.
    """
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    query = db.query(DataPoint).filter(DataPoint.dataset_id == dataset_id)

    if start_date:
        query = query.filter(DataPoint.recorded_at >= start_date)
    if end_date:
        query = query.filter(DataPoint.recorded_at <= end_date)

    points = (
        query.order_by(DataPoint.recorded_at.asc())
        .limit(limit)
        .all()
    )

    labels = []
    data_values = []

    for point in points:
        labels.append(point.recorded_at.strftime("%Y-%m-%d %H:%M"))
        value = point.values.get(field)
        if value is not None:
            try:
                data_values.append(float(value))
            except (TypeError, ValueError):
                data_values.append(None)
        else:
            data_values.append(None)

    return ChartDataResponse(
        labels=labels,
        datasets=[
            {
                "label": field,
                "data": data_values,
                "borderColor": "rgb(75, 192, 192)",
                "backgroundColor": "rgba(75, 192, 192, 0.2)",
                "tension": 0.1,
            }
        ],
    )


# ============ CSV Export ============


@router.get("/{dataset_id}/export")
async def export_dataset_csv(
    dataset_id: int,
    db: DbSession,
) -> StreamingResponse:
    """Export dataset data points as CSV."""
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    points = (
        db.query(DataPoint)
        .filter(DataPoint.dataset_id == dataset_id)
        .order_by(DataPoint.recorded_at.asc())
        .all()
    )

    field_names = [f["name"] for f in dataset.data_schema.get("fields", [])]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["recorded_at"] + field_names)

    for point in points:
        row = [point.recorded_at.strftime("%Y-%m-%dT%H:%M:%S")]
        for fname in field_names:
            row.append(point.values.get(fname, ""))
        writer.writerow(row)

    output.seek(0)
    filename = f"dataset_{dataset_id}_{dataset.name.replace(' ', '_')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

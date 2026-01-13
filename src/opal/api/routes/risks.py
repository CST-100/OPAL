"""Risks API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_delete, log_update, get_model_dict
from opal.core.designators import generate_risk_number
from opal.db.models.risk import Risk, RiskStatus

router = APIRouter(prefix="/risks", tags=["risks"])


# ============ Schemas ============


class RiskResponse(BaseModel):
    """Risk response."""

    id: int
    risk_number: str | None = None
    title: str
    description: str | None = None
    status: str
    probability: int
    impact: int
    score: int
    severity: str
    mitigation_plan: str | None = None
    linked_issue_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RiskListResponse(BaseModel):
    """Paginated risk list."""

    items: list[RiskResponse]
    total: int
    page: int
    page_size: int


class RiskCreate(BaseModel):
    """Create risk request."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    probability: int = Field(3, ge=1, le=5)
    impact: int = Field(3, ge=1, le=5)
    mitigation_plan: str | None = None
    linked_issue_id: int | None = None


class RiskUpdate(BaseModel):
    """Update risk request."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = None
    probability: int | None = Field(None, ge=1, le=5)
    impact: int | None = Field(None, ge=1, le=5)
    mitigation_plan: str | None = None
    linked_issue_id: int | None = None


# ============ Utility Endpoints ============


@router.get("/statuses", response_model=list[str])
async def get_risk_statuses() -> list[str]:
    """Get all risk statuses."""
    return [s.value for s in RiskStatus]


@router.get("/matrix")
async def get_risk_matrix(db: DbSession) -> dict:
    """Get risk matrix data for visualization.

    Returns counts of active risks by probability/impact.
    """
    risks = (
        db.query(Risk)
        .filter(Risk.deleted_at.is_(None))
        .filter(Risk.status != RiskStatus.CLOSED)
        .all()
    )

    # Initialize 5x5 matrix
    matrix = [[0 for _ in range(5)] for _ in range(5)]

    for risk in risks:
        prob_idx = risk.probability - 1  # 0-indexed
        impact_idx = risk.impact - 1
        matrix[prob_idx][impact_idx] += 1

    return {
        "matrix": matrix,
        "labels": {
            "probability": ["1 - Rare", "2 - Unlikely", "3 - Possible", "4 - Likely", "5 - Almost Certain"],
            "impact": ["1 - Negligible", "2 - Minor", "3 - Moderate", "4 - Major", "5 - Severe"],
        },
        "total_risks": len(risks),
    }


# ============ Risk CRUD ============


def _risk_to_response(risk: Risk) -> RiskResponse:
    """Convert Risk model to response."""
    status_val = risk.status.value if hasattr(risk.status, 'value') else risk.status
    return RiskResponse(
        id=risk.id,
        risk_number=risk.risk_number,
        title=risk.title,
        description=risk.description,
        status=status_val,
        probability=risk.probability,
        impact=risk.impact,
        score=risk.probability * risk.impact,
        severity=risk.severity,
        mitigation_plan=risk.mitigation_plan,
        linked_issue_id=risk.linked_issue_id,
        created_at=risk.created_at,
        updated_at=risk.updated_at,
    )


@router.get("", response_model=RiskListResponse)
async def list_risks(
    db: DbSession,
    search: str | None = Query(None),
    status: str | None = Query(None),
    severity: str | None = Query(None),
    min_score: int | None = Query(None, ge=1, le=25),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> RiskListResponse:
    """List risks with optional filters."""
    query = db.query(Risk).filter(Risk.deleted_at.is_(None))

    if search:
        search_term = f"%{search}%"
        query = query.filter(Risk.title.ilike(search_term))

    if status:
        query = query.filter(Risk.status == status)

    total = query.count()

    risks = (
        query.order_by(Risk.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Filter by severity/min_score in Python (computed properties)
    items = [_risk_to_response(r) for r in risks]

    if severity:
        items = [i for i in items if i.severity == severity]
    if min_score:
        items = [i for i in items if i.score >= min_score]

    return RiskListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=RiskResponse, status_code=201)
async def create_risk(
    data: RiskCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> RiskResponse:
    """Create a new risk."""
    risk = Risk(
        risk_number=generate_risk_number(db),
        title=data.title,
        description=data.description,
        status=RiskStatus.IDENTIFIED,
        probability=data.probability,
        impact=data.impact,
        mitigation_plan=data.mitigation_plan,
        linked_issue_id=data.linked_issue_id,
    )
    db.add(risk)
    db.flush()

    log_create(db, risk, user_id)
    db.commit()
    db.refresh(risk)

    return _risk_to_response(risk)


@router.get("/{risk_id}", response_model=RiskResponse)
async def get_risk(
    risk_id: int,
    db: DbSession,
) -> RiskResponse:
    """Get risk by ID."""
    risk = (
        db.query(Risk)
        .filter(Risk.id == risk_id, Risk.deleted_at.is_(None))
        .first()
    )
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")

    return _risk_to_response(risk)


@router.patch("/{risk_id}", response_model=RiskResponse)
async def update_risk(
    risk_id: int,
    data: RiskUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> RiskResponse:
    """Update a risk."""
    risk = (
        db.query(Risk)
        .filter(Risk.id == risk_id, Risk.deleted_at.is_(None))
        .first()
    )
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")

    old_values = get_model_dict(risk)

    if data.title is not None:
        risk.title = data.title
    if data.description is not None:
        risk.description = data.description
    if data.status is not None:
        try:
            risk.status = RiskStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")
    if data.probability is not None:
        risk.probability = data.probability
    if data.impact is not None:
        risk.impact = data.impact
    if data.mitigation_plan is not None:
        risk.mitigation_plan = data.mitigation_plan
    if data.linked_issue_id is not None:
        risk.linked_issue_id = data.linked_issue_id

    log_update(db, risk, old_values, user_id)
    db.commit()
    db.refresh(risk)

    return _risk_to_response(risk)


@router.delete("/{risk_id}", status_code=204)
async def delete_risk(
    risk_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Soft delete a risk."""
    risk = (
        db.query(Risk)
        .filter(Risk.id == risk_id, Risk.deleted_at.is_(None))
        .first()
    )
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")

    risk.deleted_at = datetime.now(timezone.utc)
    log_delete(db, risk, user_id)
    db.commit()

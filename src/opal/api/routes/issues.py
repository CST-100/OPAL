"""Issues API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import log_create, log_delete, log_update, get_model_dict
from opal.core.designators import generate_issue_number
from opal.db.models.issue import Issue, IssuePriority, IssueStatus, IssueType

router = APIRouter(prefix="/issues", tags=["issues"])


# ============ Schemas ============


class IssueResponse(BaseModel):
    """Issue response."""

    id: int
    issue_number: str | None = None
    title: str
    description: str | None = None
    issue_type: str
    status: str
    priority: str
    part_id: int | None = None
    procedure_id: int | None = None
    procedure_instance_id: int | None = None
    step_execution_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IssueListResponse(BaseModel):
    """Paginated issue list."""

    items: list[IssueResponse]
    total: int
    page: int
    page_size: int


class IssueCreate(BaseModel):
    """Create issue request."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    issue_type: str = "task"
    priority: str = "medium"
    part_id: int | None = None
    procedure_id: int | None = None
    procedure_instance_id: int | None = None


class IssueUpdate(BaseModel):
    """Update issue request."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    part_id: int | None = None
    procedure_id: int | None = None


# ============ Utility Endpoints ============


@router.get("/types", response_model=list[str])
async def get_issue_types() -> list[str]:
    """Get all issue types."""
    return [t.value for t in IssueType]


@router.get("/statuses", response_model=list[str])
async def get_issue_statuses() -> list[str]:
    """Get all issue statuses."""
    return [s.value for s in IssueStatus]


@router.get("/priorities", response_model=list[str])
async def get_issue_priorities() -> list[str]:
    """Get all issue priorities."""
    return [p.value for p in IssuePriority]


# ============ Issue CRUD ============


@router.get("", response_model=IssueListResponse)
async def list_issues(
    db: DbSession,
    search: str | None = Query(None),
    issue_type: str | None = Query(None),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    part_id: int | None = Query(None),
    procedure_id: int | None = Query(None),
    procedure_instance_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> IssueListResponse:
    """List issues with optional filters."""
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
    if part_id:
        query = query.filter(Issue.part_id == part_id)
    if procedure_id:
        query = query.filter(Issue.procedure_id == procedure_id)
    if procedure_instance_id:
        query = query.filter(Issue.procedure_instance_id == procedure_instance_id)

    total = query.count()

    issues = (
        query.order_by(Issue.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    def get_val(obj, attr):
        val = getattr(obj, attr)
        return val.value if hasattr(val, 'value') else val

    return IssueListResponse(
        items=[
            IssueResponse(
                id=i.id,
                issue_number=i.issue_number,
                title=i.title,
                description=i.description,
                issue_type=get_val(i, 'issue_type'),
                status=get_val(i, 'status'),
                priority=get_val(i, 'priority'),
                part_id=i.part_id,
                procedure_id=i.procedure_id,
                procedure_instance_id=i.procedure_instance_id,
                step_execution_id=i.step_execution_id,
                created_at=i.created_at,
                updated_at=i.updated_at,
            )
            for i in issues
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=IssueResponse, status_code=201)
async def create_issue(
    data: IssueCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> IssueResponse:
    """Create a new issue."""
    # Validate enums
    try:
        issue_type = IssueType(data.issue_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid issue type: {data.issue_type}")

    try:
        priority = IssuePriority(data.priority)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {data.priority}")

    issue = Issue(
        issue_number=generate_issue_number(db),
        title=data.title,
        description=data.description,
        issue_type=issue_type,
        status=IssueStatus.OPEN,
        priority=priority,
        part_id=data.part_id,
        procedure_id=data.procedure_id,
        procedure_instance_id=data.procedure_instance_id,
    )
    db.add(issue)
    db.flush()

    log_create(db, issue, user_id)
    db.commit()
    db.refresh(issue)

    def get_val(obj, attr):
        val = getattr(obj, attr)
        return val.value if hasattr(val, 'value') else val

    return IssueResponse(
        id=issue.id,
        issue_number=issue.issue_number,
        title=issue.title,
        description=issue.description,
        issue_type=get_val(issue, 'issue_type'),
        status=get_val(issue, 'status'),
        priority=get_val(issue, 'priority'),
        part_id=issue.part_id,
        procedure_id=issue.procedure_id,
        procedure_instance_id=issue.procedure_instance_id,
        step_execution_id=issue.step_execution_id,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: int,
    db: DbSession,
) -> IssueResponse:
    """Get issue by ID."""
    issue = (
        db.query(Issue)
        .filter(Issue.id == issue_id, Issue.deleted_at.is_(None))
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    def get_val(obj, attr):
        val = getattr(obj, attr)
        return val.value if hasattr(val, 'value') else val

    return IssueResponse(
        id=issue.id,
        issue_number=issue.issue_number,
        title=issue.title,
        description=issue.description,
        issue_type=get_val(issue, 'issue_type'),
        status=get_val(issue, 'status'),
        priority=get_val(issue, 'priority'),
        part_id=issue.part_id,
        procedure_id=issue.procedure_id,
        procedure_instance_id=issue.procedure_instance_id,
        step_execution_id=issue.step_execution_id,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: int,
    data: IssueUpdate,
    db: DbSession,
    user_id: CurrentUserId,
) -> IssueResponse:
    """Update an issue."""
    issue = (
        db.query(Issue)
        .filter(Issue.id == issue_id, Issue.deleted_at.is_(None))
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    old_values = get_model_dict(issue)

    if data.title is not None:
        issue.title = data.title
    if data.description is not None:
        issue.description = data.description
    if data.issue_type is not None:
        try:
            issue.issue_type = IssueType(data.issue_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid issue type: {data.issue_type}")
    if data.status is not None:
        try:
            issue.status = IssueStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")
    if data.priority is not None:
        try:
            issue.priority = IssuePriority(data.priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {data.priority}")
    if data.part_id is not None:
        issue.part_id = data.part_id
    if data.procedure_id is not None:
        issue.procedure_id = data.procedure_id

    log_update(db, issue, old_values, user_id)
    db.commit()
    db.refresh(issue)

    def get_val(obj, attr):
        val = getattr(obj, attr)
        return val.value if hasattr(val, 'value') else val

    return IssueResponse(
        id=issue.id,
        issue_number=issue.issue_number,
        title=issue.title,
        description=issue.description,
        issue_type=get_val(issue, 'issue_type'),
        status=get_val(issue, 'status'),
        priority=get_val(issue, 'priority'),
        part_id=issue.part_id,
        procedure_id=issue.procedure_id,
        procedure_instance_id=issue.procedure_instance_id,
        step_execution_id=issue.step_execution_id,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


@router.delete("/{issue_id}", status_code=204)
async def delete_issue(
    issue_id: int,
    db: DbSession,
    user_id: CurrentUserId,
) -> None:
    """Soft delete an issue."""
    issue = (
        db.query(Issue)
        .filter(Issue.id == issue_id, Issue.deleted_at.is_(None))
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.deleted_at = datetime.now(timezone.utc)
    log_delete(db, issue, user_id)
    db.commit()

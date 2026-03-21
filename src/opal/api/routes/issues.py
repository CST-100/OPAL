"""Issues API routes."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import get_model_dict, log_create, log_delete, log_update
from opal.core.designators import generate_issue_number
from opal.db.models.issue import (
    DispositionType,
    Issue,
    IssuePriority,
    IssueStatus,
    IssueType,
)
from opal.db.models.issue_comment import IssueComment

router = APIRouter(prefix="/issues", tags=["issues"])


def _get_enum_val(obj: object, attr: str) -> str:
    """Extract the string value from a potentially-enum attribute."""
    val = getattr(obj, attr)
    return val.value if hasattr(val, "value") else val


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
    root_cause: str | None = None
    corrective_action: str | None = None
    disposition_type: str | None = None
    disposition_notes: str | None = None
    assigned_to_id: int | None = None
    disposition_approved_by_id: int | None = None
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
    assigned_to_id: int | None = None


class IssueUpdate(BaseModel):
    """Update issue request."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    part_id: int | None = None
    procedure_id: int | None = None
    procedure_instance_id: int | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    disposition_type: str | None = None
    disposition_notes: str | None = None
    assigned_to_id: int | None = None
    disposition_approved_by_id: int | None = None


class IssueCommentResponse(BaseModel):
    """Issue comment response."""

    id: int
    issue_id: int
    user_id: int | None = None
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class IssueCommentCreate(BaseModel):
    """Create issue comment request."""

    body: str = Field(..., min_length=1)


def _issue_to_response(issue: Issue) -> IssueResponse:
    """Convert an Issue ORM object to an IssueResponse."""
    return IssueResponse(
        id=issue.id,
        issue_number=issue.issue_number,
        title=issue.title,
        description=issue.description,
        issue_type=_get_enum_val(issue, "issue_type"),
        status=_get_enum_val(issue, "status"),
        priority=_get_enum_val(issue, "priority"),
        part_id=issue.part_id,
        procedure_id=issue.procedure_id,
        procedure_instance_id=issue.procedure_instance_id,
        step_execution_id=issue.step_execution_id,
        root_cause=issue.root_cause,
        corrective_action=issue.corrective_action,
        disposition_type=_get_enum_val(issue, "disposition_type") if issue.disposition_type else None,
        disposition_notes=issue.disposition_notes,
        assigned_to_id=issue.assigned_to_id,
        disposition_approved_by_id=issue.disposition_approved_by_id,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


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


@router.get("/disposition-types", response_model=list[str])
async def get_disposition_types() -> list[str]:
    """Get all disposition types."""
    return [d.value for d in DispositionType]


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

    return IssueListResponse(
        items=[_issue_to_response(i) for i in issues],
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
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid issue type: {data.issue_type}") from err

    try:
        priority = IssuePriority(data.priority)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {data.priority}") from err

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
        assigned_to_id=data.assigned_to_id,
    )
    db.add(issue)
    db.flush()

    log_create(db, issue, user_id)
    db.commit()
    db.refresh(issue)

    return _issue_to_response(issue)


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

    return _issue_to_response(issue)


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
        except ValueError as err:
            raise HTTPException(status_code=400, detail=f"Invalid issue type: {data.issue_type}") from err
    if data.status is not None:
        try:
            new_status = IssueStatus(data.status)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}") from err
        # Disposition approval requires disposition_type to be set
        if new_status == IssueStatus.DISPOSITION_APPROVED:
            effective_disposition_type = data.disposition_type or (
                _get_enum_val(issue, "disposition_type") if issue.disposition_type else None
            )
            if not effective_disposition_type:
                raise HTTPException(
                    status_code=400,
                    detail="disposition_type is required when approving disposition",
                )
        issue.status = new_status
    if data.priority is not None:
        try:
            issue.priority = IssuePriority(data.priority)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {data.priority}") from err
    if data.part_id is not None:
        issue.part_id = data.part_id
    if data.procedure_id is not None:
        issue.procedure_id = data.procedure_id
    if data.procedure_instance_id is not None:
        issue.procedure_instance_id = data.procedure_instance_id
    if data.root_cause is not None:
        issue.root_cause = data.root_cause
    if data.corrective_action is not None:
        issue.corrective_action = data.corrective_action
    if data.disposition_type is not None:
        if data.disposition_type == "":
            # Clearing disposition_type — block if status is disposition_approved
            current_status = _get_enum_val(issue, "status") if issue.status else None
            if current_status == "disposition_approved":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot clear disposition_type while status is disposition_approved",
                )
            issue.disposition_type = None
        else:
            try:
                issue.disposition_type = DispositionType(data.disposition_type)
            except ValueError as err:
                raise HTTPException(
                    status_code=400, detail=f"Invalid disposition type: {data.disposition_type}"
                ) from err
    if data.disposition_notes is not None:
        issue.disposition_notes = data.disposition_notes
    if data.assigned_to_id is not None:
        issue.assigned_to_id = data.assigned_to_id
    if data.disposition_approved_by_id is not None:
        issue.disposition_approved_by_id = data.disposition_approved_by_id

    log_update(db, issue, old_values, user_id)
    db.commit()
    db.refresh(issue)

    return _issue_to_response(issue)


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

    issue.deleted_at = datetime.now(UTC)
    log_delete(db, issue, user_id)
    db.commit()


# ============ Issue Comments ============


@router.post("/{issue_id}/comments", response_model=IssueCommentResponse, status_code=201)
async def create_issue_comment(
    issue_id: int,
    data: IssueCommentCreate,
    db: DbSession,
    user_id: CurrentUserId,
) -> IssueCommentResponse:
    """Add a comment to an issue."""
    issue = (
        db.query(Issue)
        .filter(Issue.id == issue_id, Issue.deleted_at.is_(None))
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    comment = IssueComment(
        issue_id=issue_id,
        user_id=user_id,
        body=data.body,
    )
    db.add(comment)
    db.flush()
    log_create(db, comment, user_id)
    db.commit()
    db.refresh(comment)

    return IssueCommentResponse.model_validate(comment)


@router.get("/{issue_id}/comments", response_model=list[IssueCommentResponse])
async def list_issue_comments(
    issue_id: int,
    db: DbSession,
) -> list[IssueCommentResponse]:
    """List comments for an issue."""
    issue = (
        db.query(Issue)
        .filter(Issue.id == issue_id, Issue.deleted_at.is_(None))
        .first()
    )
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    comments = (
        db.query(IssueComment)
        .filter(IssueComment.issue_id == issue_id)
        .order_by(IssueComment.created_at)
        .all()
    )

    return [IssueCommentResponse.model_validate(c) for c in comments]

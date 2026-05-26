"""File attachment endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from opal.api.deps import CurrentUserId, DbSession
from opal.config import get_active_settings
from opal.core.audit import get_model_dict, log_create, log_delete, log_update
from opal.db.models.attachment import Attachment
from opal.db.models.execution import ProcedureInstance, StepExecution
from opal.db.models.issue import Issue

router = APIRouter(prefix="/attachments", tags=["attachments"])


ALLOWED_KINDS: set[str | None] = {None, "inline", "reference", "closeout"}


class AttachmentResponse(BaseModel):
    """Schema for attachment response."""

    id: int
    original_filename: str
    stored_filename: str
    mime_type: str
    size_bytes: int
    procedure_instance_id: int | None
    step_execution_id: int | None
    issue_id: int | None = None
    procedure_id: int | None = None
    kind: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


class AttachmentPatchRequest(BaseModel):
    """Partial update payload for an attachment."""

    kind: str | None = None


def _attachment_to_response(att: Attachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=att.id,
        original_filename=att.original_filename,
        stored_filename=att.stored_filename,
        mime_type=att.mime_type,
        size_bytes=att.size_bytes,
        procedure_instance_id=att.procedure_instance_id,
        step_execution_id=att.step_execution_id,
        issue_id=att.issue_id,
        procedure_id=att.procedure_id,
        kind=att.kind,
        created_at=att.created_at.isoformat(),
    )


@router.post("/upload", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    db: DbSession,
    user_id: CurrentUserId,
    file: UploadFile,
    procedure_instance_id: int | None = Form(default=None),
    step_execution_id: int | None = Form(default=None),
    issue_id: int | None = Form(default=None),
    procedure_id: int | None = Form(default=None),
    kind: str | None = Form(default=None),
) -> AttachmentResponse:
    """Upload a file attachment.

    Can be linked to a procedure instance, step execution, issue, and/or
    procedure template. `procedure_id` scopes inline images used in step
    instructions so they're cleaned up when the procedure is deleted.
    """
    if kind is not None and kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid kind '{kind}'. Allowed: {sorted(k for k in ALLOWED_KINDS if k)}",
        )

    settings = get_active_settings()

    # Validate MIME type
    if file.content_type not in settings.mime_types_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file.content_type}' is not allowed. Allowed: {', '.join(settings.mime_types_list)}",
        )

    # Read file and check size
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({len(content)} bytes). Max: {settings.max_upload_size} bytes",
        )

    # Validate linked entities exist
    if procedure_instance_id:
        instance = (
            db.query(ProcedureInstance)
            .filter(ProcedureInstance.id == procedure_instance_id)
            .first()
        )
        if not instance:
            raise HTTPException(
                status_code=404, detail=f"Procedure instance {procedure_instance_id} not found"
            )

    if step_execution_id:
        step_exec = db.query(StepExecution).filter(StepExecution.id == step_execution_id).first()
        if not step_exec:
            raise HTTPException(
                status_code=404, detail=f"Step execution {step_execution_id} not found"
            )

    if issue_id:
        issue = db.query(Issue).filter(Issue.id == issue_id, Issue.deleted_at.is_(None)).first()
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

    if procedure_id:
        from opal.db.models import MasterProcedure

        procedure = (
            db.query(MasterProcedure)
            .filter(
                MasterProcedure.id == procedure_id,
                MasterProcedure.deleted_at.is_(None),
            )
            .first()
        )
        if not procedure:
            raise HTTPException(status_code=404, detail=f"Procedure {procedure_id} not found")

    # Sanitize filename and generate stored name
    original_name = file.filename or "unnamed"
    # Strip path separators and limit length
    original_name = original_name.replace("/", "_").replace("\\", "_")[:200]
    ext = Path(original_name).suffix
    stored_name = f"{uuid.uuid4()}{ext}"

    # Ensure upload directory exists and write file
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = settings.upload_dir / stored_name
    file_path.write_bytes(content)

    # Create DB record
    attachment = Attachment(
        original_filename=original_name,
        stored_filename=stored_name,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        procedure_instance_id=procedure_instance_id,
        step_execution_id=step_execution_id,
        issue_id=issue_id,
        procedure_id=procedure_id,
        kind=kind,
    )
    db.add(attachment)
    db.flush()
    log_create(db, attachment, user_id)
    db.commit()
    db.refresh(attachment)

    return _attachment_to_response(attachment)


@router.get("/{attachment_id}/download")
async def download_attachment(
    db: DbSession,
    attachment_id: int,
) -> FileResponse:
    """Download an attachment file."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    settings = get_active_settings()
    file_path = settings.upload_dir / attachment.stored_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=attachment.original_filename,
        media_type=attachment.mime_type,
    )


@router.get("", response_model=list[AttachmentResponse])
async def list_attachments(
    db: DbSession,
    procedure_instance_id: int | None = Query(None),
    step_execution_id: int | None = Query(None),
    issue_id: int | None = Query(None),
    procedure_id: int | None = Query(None),
    kind: str | None = Query(None),
) -> list[AttachmentResponse]:
    """List attachments, optionally filtered by instance, step, issue,
    procedure, or kind."""
    query = db.query(Attachment)

    if procedure_instance_id is not None:
        query = query.filter(Attachment.procedure_instance_id == procedure_instance_id)
    if step_execution_id is not None:
        query = query.filter(Attachment.step_execution_id == step_execution_id)
    if issue_id is not None:
        query = query.filter(Attachment.issue_id == issue_id)
    if procedure_id is not None:
        query = query.filter(Attachment.procedure_id == procedure_id)
    if kind is not None:
        query = query.filter(Attachment.kind == kind)

    attachments = query.order_by(Attachment.created_at.desc()).limit(200).all()
    return [_attachment_to_response(a) for a in attachments]


@router.patch("/{attachment_id}", response_model=AttachmentResponse)
async def patch_attachment(
    db: DbSession,
    attachment_id: int,
    payload: AttachmentPatchRequest,
    user_id: CurrentUserId,
) -> AttachmentResponse:
    """Update mutable fields on an attachment (currently just `kind`)."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    new_kind = payload.kind
    if new_kind is not None and new_kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid kind '{new_kind}'. Allowed: {sorted(k for k in ALLOWED_KINDS if k)}",
        )

    old_values = get_model_dict(attachment)
    attachment.kind = new_kind
    log_update(db, attachment, old_values, user_id)
    db.commit()
    db.refresh(attachment)
    return _attachment_to_response(attachment)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    db: DbSession,
    attachment_id: int,
    user_id: CurrentUserId,
) -> None:
    """Delete an attachment (file + DB record)."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Remove file from disk
    settings = get_active_settings()
    file_path = settings.upload_dir / attachment.stored_filename
    file_path.unlink(missing_ok=True)

    log_delete(db, attachment, user_id)
    db.delete(attachment)
    db.commit()

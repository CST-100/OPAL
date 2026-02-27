"""Onshape integration API endpoints."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from pydantic import BaseModel

from opal.api.deps import CurrentUserId, DbSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onshape", tags=["onshape"])


# ── Response schemas ─────────────────────────────────────────────


class OnshapeStatusResponse(BaseModel):
    """Onshape integration status."""

    enabled: bool
    connected: bool
    documents: list[dict[str, Any]]
    poll_interval_minutes: int


class SyncLogResponse(BaseModel):
    """Sync log entry."""

    id: int
    started_at: str
    completed_at: str | None
    direction: str
    trigger: str
    status: str
    document_id: str | None
    parts_created: int
    parts_updated: int
    bom_lines_created: int
    bom_lines_updated: int
    bom_lines_removed: int
    errors: dict[str, Any] | None
    summary: str | None


class OnshapeLinkResponse(BaseModel):
    """An Onshape link to an OPAL part."""

    id: int
    part_id: int
    part_internal_pn: str | None
    part_name: str
    document_id: str
    element_id: str
    part_id_onshape: str
    onshape_name: str | None
    onshape_part_number: str | None
    last_synced_at: str | None
    stale: bool


class SyncResultResponse(BaseModel):
    """Result of a sync operation."""

    sync_log_id: int
    status: str
    summary: str | None
    parts_created: int
    parts_updated: int
    bom_lines_created: int
    bom_lines_updated: int
    bom_lines_removed: int


class AddDocumentRequest(BaseModel):
    """Request to add an Onshape document from a URL."""

    url: str
    name: str = ""


class DocumentRefResponse(BaseModel):
    """Response for an added/listed document reference."""

    name: str
    document_id: str
    workspace_id: str
    element_id: str
    element_type: str
    auto_sync: bool


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/status", response_model=OnshapeStatusResponse)
async def onshape_status() -> OnshapeStatusResponse:
    """Get Onshape integration status."""
    from opal.config import get_active_project, get_active_settings

    settings = get_active_settings()
    project = get_active_project()

    documents = []
    if project and project.onshape.documents:
        for doc in project.onshape.documents:
            documents.append({
                "name": doc.name,
                "document_id": doc.document_id,
                "element_id": doc.element_id,
                "auto_sync": doc.auto_sync,
            })

    return OnshapeStatusResponse(
        enabled=settings.onshape_enabled,
        connected=settings.onshape_enabled and bool(documents),
        documents=documents,
        poll_interval_minutes=settings.onshape_poll_interval_minutes,
    )


@router.post("/documents", response_model=DocumentRefResponse)
async def add_document(body: AddDocumentRequest) -> DocumentRefResponse:
    """Add an Onshape document from a pasted URL.

    Parses the URL, auto-detects element type via API, and saves to project config.
    """
    from opal.config import get_active_project, get_active_settings
    from opal.integrations.onshape.client import OnshapeClient, parse_onshape_url
    from opal.project import OnshapeDocumentRef, save_project_config

    settings = get_active_settings()
    if not settings.onshape_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onshape integration is not enabled",
        )

    project = get_active_project()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No project configured",
        )

    # Parse URL
    parsed = parse_onshape_url(body.url)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Onshape URL. Expected format: "
            "https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}",
        )

    document_id, wvm_type, wvm_id, element_id = parsed

    if wvm_type != "w":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only workspace URLs (/w/) are supported. "
            "Open the document in a workspace and copy the URL.",
        )
    workspace_id = wvm_id

    # Check for duplicates
    for doc in project.onshape.documents:
        if doc.document_id == document_id and doc.element_id == element_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document element already registered as '{doc.name}'",
            )

    # Auto-detect element type via API
    client = OnshapeClient(
        access_key=settings.onshape_access_key,
        secret_key=settings.onshape_secret_key,
        base_url=settings.onshape_base_url,
    )
    try:
        elements = await asyncio.to_thread(
            client.get_elements, document_id, workspace_id
        )
    finally:
        client.close()

    # Find the matching element
    matched = next((el for el in elements if el.id == element_id), None)
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Element not found in the Onshape document",
        )

    # Map Onshape element type to OPAL config value
    type_map = {"PARTSTUDIO": "part_studio", "ASSEMBLY": "assembly"}
    element_type = type_map.get(matched.element_type)
    if not element_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported element type: {matched.element_type}. "
            "Only assemblies and part studios are supported.",
        )

    name = body.name.strip() if body.name.strip() else matched.name

    doc_ref = OnshapeDocumentRef(
        name=name,
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
        element_type=element_type,
        auto_sync=True,
    )
    project.onshape.documents.append(doc_ref)
    save_project_config(project)

    return DocumentRefResponse(
        name=doc_ref.name,
        document_id=doc_ref.document_id,
        workspace_id=doc_ref.workspace_id,
        element_id=doc_ref.element_id,
        element_type=doc_ref.element_type,
        auto_sync=doc_ref.auto_sync,
    )


@router.delete(
    "/documents/{document_id}/{element_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_document(
    document_id: str = Path(...),
    element_id: str = Path(...),
) -> None:
    """Remove an Onshape document from the project config."""
    from opal.config import get_active_project
    from opal.project import save_project_config

    project = get_active_project()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No project configured",
        )

    original_len = len(project.onshape.documents)
    project.onshape.documents = [
        d
        for d in project.onshape.documents
        if not (d.document_id == document_id and d.element_id == element_id)
    ]

    if len(project.onshape.documents) == original_len:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in project config",
        )

    save_project_config(project)


@router.post("/sync/pull", response_model=SyncResultResponse)
async def trigger_pull_sync(
    user_id: CurrentUserId,
    document_id: str | None = Query(None, description="Specific document to sync (all if omitted)"),
) -> SyncResultResponse:
    """Trigger a manual pull sync from Onshape."""
    from opal.config import get_active_project, get_active_settings
    from opal.db.base import SessionLocal
    from opal.integrations.onshape.client import OnshapeClient
    from opal.integrations.onshape.sync import pull_sync

    settings = get_active_settings()
    if not settings.onshape_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onshape integration is not enabled",
        )

    project = get_active_project()
    if not project or not project.onshape.documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Onshape documents configured in project",
        )

    # Find the document(s) to sync
    docs = project.onshape.documents
    if document_id:
        docs = [d for d in docs if d.document_id == document_id]
        if not docs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found in project config",
            )

    client = OnshapeClient(
        access_key=settings.onshape_access_key,
        secret_key=settings.onshape_secret_key,
        base_url=settings.onshape_base_url,
    )

    # Run sync in thread pool with its own session (avoids cross-thread session use)
    def _run_sync() -> list:
        db = SessionLocal()
        try:
            return [pull_sync(db, client, doc_ref, user_id, "manual") for doc_ref in docs]
        finally:
            db.close()

    sync_logs = await asyncio.to_thread(_run_sync)
    client.close()

    # Combine results across all synced documents
    worst = "success"
    for sl in sync_logs:
        if sl.status == "error":
            worst = "error"
            break
        if sl.status == "partial":
            worst = "partial"

    return SyncResultResponse(
        sync_log_id=sync_logs[-1].id,
        status=worst,
        summary="\n".join(sl.summary or "" for sl in sync_logs),
        parts_created=sum(sl.parts_created for sl in sync_logs),
        parts_updated=sum(sl.parts_updated for sl in sync_logs),
        bom_lines_created=sum(sl.bom_lines_created for sl in sync_logs),
        bom_lines_updated=sum(sl.bom_lines_updated for sl in sync_logs),
        bom_lines_removed=sum(sl.bom_lines_removed for sl in sync_logs),
    )


@router.post("/sync/push", response_model=SyncResultResponse)
async def trigger_push_sync(
    user_id: CurrentUserId,
    document_id: str | None = Query(None, description="Specific document to push (all if omitted)"),
) -> SyncResultResponse:
    """Trigger a manual push sync to Onshape."""
    from opal.config import get_active_project, get_active_settings
    from opal.db.base import SessionLocal
    from opal.integrations.onshape.client import OnshapeClient
    from opal.integrations.onshape.sync import push_sync

    settings = get_active_settings()
    if not settings.onshape_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onshape integration is not enabled",
        )

    project = get_active_project()
    if not project or not project.onshape.documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Onshape documents configured in project",
        )

    docs = project.onshape.documents
    if document_id:
        docs = [d for d in docs if d.document_id == document_id]
        if not docs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found in project config",
            )

    client = OnshapeClient(
        access_key=settings.onshape_access_key,
        secret_key=settings.onshape_secret_key,
        base_url=settings.onshape_base_url,
    )

    def _run_sync() -> list:
        db = SessionLocal()
        try:
            return [push_sync(db, client, doc_ref, user_id, "manual") for doc_ref in docs]
        finally:
            db.close()

    sync_logs = await asyncio.to_thread(_run_sync)
    client.close()

    # Combine results across all synced documents
    worst = "success"
    for sl in sync_logs:
        if sl.status == "error":
            worst = "error"
            break
        if sl.status == "partial":
            worst = "partial"

    return SyncResultResponse(
        sync_log_id=sync_logs[-1].id,
        status=worst,
        summary="\n".join(sl.summary or "" for sl in sync_logs),
        parts_created=sum(sl.parts_created for sl in sync_logs),
        parts_updated=sum(sl.parts_updated for sl in sync_logs),
        bom_lines_created=sum(sl.bom_lines_created for sl in sync_logs),
        bom_lines_updated=sum(sl.bom_lines_updated for sl in sync_logs),
        bom_lines_removed=sum(sl.bom_lines_removed for sl in sync_logs),
    )


@router.get("/sync/logs", response_model=list[SyncLogResponse])
async def get_sync_logs(
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
    direction: str | None = Query(None, description="Filter by 'pull' or 'push'"),
) -> list[SyncLogResponse]:
    """Get recent sync logs."""
    from opal.db.models.onshape_link import OnshapeSyncLog

    query = db.query(OnshapeSyncLog).order_by(OnshapeSyncLog.id.desc())
    if direction:
        query = query.filter(OnshapeSyncLog.direction == direction)
    logs = query.limit(limit).all()

    return [
        SyncLogResponse(
            id=log.id,
            started_at=log.started_at.isoformat(),
            completed_at=log.completed_at.isoformat() if log.completed_at else None,
            direction=log.direction,
            trigger=log.trigger,
            status=log.status,
            document_id=log.document_id,
            parts_created=log.parts_created,
            parts_updated=log.parts_updated,
            bom_lines_created=log.bom_lines_created,
            bom_lines_updated=log.bom_lines_updated,
            bom_lines_removed=log.bom_lines_removed,
            errors=log.errors,
            summary=log.summary,
        )
        for log in logs
    ]


@router.get("/links", response_model=list[OnshapeLinkResponse])
async def get_links(
    db: DbSession,
    document_id: str | None = Query(None),
    stale: bool | None = Query(None),
) -> list[OnshapeLinkResponse]:
    """Get all Onshape links."""
    from opal.db.models.onshape_link import OnshapeLink

    query = db.query(OnshapeLink).order_by(OnshapeLink.id.desc())
    if document_id:
        query = query.filter(OnshapeLink.document_id == document_id)
    if stale is not None:
        query = query.filter(OnshapeLink.stale == stale)

    links = query.all()
    return [
        OnshapeLinkResponse(
            id=link.id,
            part_id=link.part_id,
            part_internal_pn=link.part.internal_pn if link.part else None,
            part_name=link.part.name if link.part else "",
            document_id=link.document_id,
            element_id=link.element_id,
            part_id_onshape=link.part_id_onshape,
            onshape_name=link.onshape_name,
            onshape_part_number=link.onshape_part_number,
            last_synced_at=link.last_synced_at.isoformat() if link.last_synced_at else None,
            stale=link.stale,
        )
        for link in links
    ]


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    db: DbSession,
    link_id: int,
    user_id: CurrentUserId,
) -> None:
    """Unlink an Onshape part from its OPAL part (does not delete the OPAL part)."""
    from opal.core.audit import log_delete
    from opal.db.models.onshape_link import OnshapeLink

    link = db.query(OnshapeLink).filter(OnshapeLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    log_delete(db, link, user_id)
    db.delete(link)
    db.commit()


@router.post("/webhook")
async def onshape_webhook(
    request: Request,
) -> dict[str, str]:
    """Receive Onshape webhook notifications and trigger pull sync.

    Verifies HMAC signature if webhook_secret is configured.
    """
    import hashlib
    import hmac as hmac_mod

    from opal.config import get_active_project, get_active_settings
    from opal.db.base import SessionLocal
    from opal.integrations.onshape.client import OnshapeClient
    from opal.integrations.onshape.sync import pull_sync

    settings = get_active_settings()
    if not settings.onshape_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Onshape not enabled")

    body = await request.body()

    # Verify HMAC signature if secret is configured
    if settings.onshape_webhook_secret:
        signature = request.headers.get("X-Onshape-Signature", "")
        expected = hmac_mod.new(
            settings.onshape_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac_mod.compare_digest(signature, expected):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    # Parse payload to find the document ID
    import json

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from e

    document_id = payload.get("documentId", "")
    if not document_id:
        return {"status": "ignored", "reason": "no document ID"}

    project = get_active_project()
    if not project:
        return {"status": "ignored", "reason": "no project configured"}

    # Find all matching document refs (multiple elements may share one document)
    matching_refs = [d for d in project.onshape.documents if d.document_id == document_id]
    if not matching_refs:
        return {"status": "ignored", "reason": "document not registered"}

    client = OnshapeClient(
        access_key=settings.onshape_access_key,
        secret_key=settings.onshape_secret_key,
        base_url=settings.onshape_base_url,
    )

    def _run_sync() -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        db = SessionLocal()
        try:
            for doc_ref in matching_refs:
                sync_log = pull_sync(db, client, doc_ref, None, "webhook")
                results.append({"status": sync_log.status, "summary": sync_log.summary or ""})
        finally:
            db.close()
        return results

    results = await asyncio.to_thread(_run_sync)
    client.close()

    # Combine: worst status wins
    worst = "success"
    for r in results:
        if r["status"] == "error":
            worst = "error"
            break
        if r["status"] == "partial":
            worst = "partial"

    return {"status": worst, "summary": "\n".join(r["summary"] for r in results)}

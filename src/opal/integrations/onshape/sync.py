"""Onshape sync engine — pull and push sync operations."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from opal.core.audit import get_model_dict, log_create, log_update
from opal.integrations.onshape.client import OnshapeClient
from opal.integrations.onshape.models import OnshapeBOMItem
from opal.project import OnshapeDocumentRef

if TYPE_CHECKING:
    from opal.db.models.onshape_link import OnshapeSyncLog

logger = logging.getLogger(__name__)


def _compute_pull_hash(name: str, description: str | None, part_number: str | None) -> str:
    """SHA-256 hash of Onshape-owned fields for change detection."""
    data = json.dumps({"name": name, "description": description, "part_number": part_number},
                      sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def _compute_push_hash(
    internal_pn: str | None,
    category: str | None,
    tier: int,
) -> str:
    """SHA-256 hash of OPAL-owned fields for push change detection."""
    data = json.dumps(
        {"internal_pn": internal_pn, "category": category, "tier": tier},
        sort_keys=True,
    )
    return hashlib.sha256(data.encode()).hexdigest()


def _generate_internal_pn(db: Session, tier: int) -> str:
    """Generate the next internal part number for a given tier.

    Re-uses the same logic as the parts API route.
    """
    from opal.config import get_active_project
    from opal.db.models.part import Part

    project = get_active_project()
    if not project:
        count = db.query(Part).filter(Part.tier == tier, Part.deleted_at.is_(None)).count()
        return f"PN-{tier}-{str(count + 1).zfill(4)}"

    count = db.query(Part).filter(Part.tier == tier, Part.deleted_at.is_(None)).count()
    return project.generate_part_number(tier, count + 1)


def pull_sync(
    db: Session,
    client: OnshapeClient,
    doc_ref: OnshapeDocumentRef,
    user_id: int | None = None,
    trigger: str = "manual",
) -> "OnshapeSyncLog":
    """Pull BOM and part data from Onshape into OPAL.

    Creates new OPAL Parts for undiscovered Onshape parts, updates
    CAD-owned fields (name, description) on existing parts, and
    syncs BOM structure.

    Args:
        db: Database session.
        client: Authenticated Onshape API client.
        doc_ref: Document reference from project config.
        user_id: User who triggered the sync (None for automated).
        trigger: What triggered the sync ('manual', 'poll', 'webhook').

    Returns:
        OnshapeSyncLog with results.
    """
    from opal.config import get_active_project
    from opal.db.models.onshape_link import OnshapeLink, OnshapeSyncLog
    from opal.db.models.part import BOMLine, Part

    now = datetime.now(UTC)
    sync_log = OnshapeSyncLog(
        started_at=now,
        direction="pull",
        trigger=trigger,
        status="running",
        document_id=doc_ref.document_id,
        user_id=user_id,
    )
    db.add(sync_log)
    db.flush()

    project = get_active_project()
    default_tier = project.onshape.default_tier if project else 1
    default_category = (project.onshape.default_category if project else "") or None

    errors: list[str] = []
    parts_created = 0
    parts_updated = 0
    bom_lines_created = 0
    bom_lines_updated = 0
    bom_lines_removed = 0
    new_part_ids: list[int] = []

    try:
        # Resolve workspace_id if not provided
        workspace_id = doc_ref.workspace_id
        if not workspace_id:
            doc = client.get_document(doc_ref.document_id)
            workspace_id = doc.default_workspace_id or ""

        # Fetch BOM from Onshape
        bom = client.get_bom(
            document_id=doc_ref.document_id,
            workspace_id=workspace_id,
            element_id=doc_ref.element_id,
        )

        # Collect all Onshape part IDs seen in the BOM (flat)
        seen_onshape_part_ids: set[str] = set()

        def _flatten_bom(items: list[OnshapeBOMItem]) -> list[OnshapeBOMItem]:
            """Flatten nested BOM into a list of all items."""
            result = []
            for item in items:
                result.append(item)
                if item.children:
                    result.extend(_flatten_bom(item.children))
            return result

        flat_items = _flatten_bom(bom.items)

        # ── Sync parts ──────────────────────────────────────────

        for item in flat_items:
            if not item.part_id:
                continue
            seen_onshape_part_ids.add(item.part_id)

            pull_hash = _compute_pull_hash(item.part_name, None, item.part_number)

            # Look up existing link
            link = (
                db.query(OnshapeLink)
                .filter(
                    OnshapeLink.document_id == doc_ref.document_id,
                    OnshapeLink.part_id_onshape == item.part_id,
                )
                .first()
            )

            if link:
                # Existing link — check if Onshape data changed
                if link.pull_hash == pull_hash:
                    # No changes from Onshape side
                    link.last_synced_at = now
                    link.stale = False
                    continue

                # Update OPAL Part's CAD-owned fields
                part = link.part
                old_values = get_model_dict(part)
                part.name = item.part_name
                # description stays — Onshape BOM doesn't always carry it
                log_update(db, part, old_values, user_id)

                link.onshape_name = item.part_name
                link.onshape_part_number = item.part_number
                link.pull_hash = pull_hash
                link.last_synced_at = now
                link.stale = False
                parts_updated += 1

            else:
                # New part — create OPAL Part + OnshapeLink
                internal_pn = _generate_internal_pn(db, default_tier)
                part = Part(
                    name=item.part_name,
                    internal_pn=internal_pn,
                    tier=default_tier,
                    category=default_category,
                )
                db.add(part)
                db.flush()  # Get part.id
                log_create(db, part, user_id)

                link = OnshapeLink(
                    part_id=part.id,
                    document_id=doc_ref.document_id,
                    element_id=doc_ref.element_id,
                    part_id_onshape=item.part_id,
                    onshape_name=item.part_name,
                    onshape_part_number=item.part_number,
                    pull_hash=pull_hash,
                    last_synced_at=now,
                )
                db.add(link)
                db.flush()
                log_create(db, link, user_id)

                parts_created += 1
                new_part_ids.append(part.id)

        # ── Sync BOM structure ──────────────────────────────────

        def _sync_bom_children(
            parent_items: list[OnshapeBOMItem],
            assembly_part_id: int | None,
        ) -> None:
            nonlocal bom_lines_created, bom_lines_updated, bom_lines_removed

            if assembly_part_id is None:
                return

            # Build map of current BOM lines for this assembly
            existing_lines = {
                bl.component_id: bl
                for bl in db.query(BOMLine)
                .filter(BOMLine.assembly_id == assembly_part_id)
                .all()
            }

            seen_component_ids: set[int] = set()

            for item in parent_items:
                if not item.part_id:
                    continue

                # Find the OPAL part for this Onshape part
                child_link = (
                    db.query(OnshapeLink)
                    .filter(
                        OnshapeLink.document_id == doc_ref.document_id,
                        OnshapeLink.part_id_onshape == item.part_id,
                    )
                    .first()
                )
                if not child_link:
                    continue

                component_id = child_link.part_id
                seen_component_ids.add(component_id)

                if component_id in existing_lines:
                    # Update quantity if changed
                    bl = existing_lines[component_id]
                    if bl.quantity != item.quantity:
                        old_values = get_model_dict(bl)
                        bl.quantity = item.quantity
                        log_update(db, bl, old_values, user_id)
                        bom_lines_updated += 1
                else:
                    # Create new BOM line
                    bl = BOMLine(
                        assembly_id=assembly_part_id,
                        component_id=component_id,
                        quantity=item.quantity,
                    )
                    db.add(bl)
                    db.flush()
                    log_create(db, bl, user_id)
                    bom_lines_created += 1

                # Recurse into children
                if item.children:
                    _sync_bom_children(item.children, child_link.part_id)

            # Remove BOM lines for components no longer in Onshape BOM
            for comp_id, bl in existing_lines.items():
                if comp_id not in seen_component_ids:
                    db.delete(bl)
                    bom_lines_removed += 1

        # The top-level BOM items are children of the root assembly.
        # Find or create the root assembly part from the document.
        # For now, sync BOM for each top-level item that has children.
        for item in bom.items:
            if not item.part_id or not item.children:
                continue
            parent_link = (
                db.query(OnshapeLink)
                .filter(
                    OnshapeLink.document_id == doc_ref.document_id,
                    OnshapeLink.part_id_onshape == item.part_id,
                )
                .first()
            )
            if parent_link:
                _sync_bom_children(item.children, parent_link.part_id)

        # ── Mark stale links ───────────────────────────────────

        stale_links = (
            db.query(OnshapeLink)
            .filter(
                OnshapeLink.document_id == doc_ref.document_id,
                OnshapeLink.part_id_onshape.notin_(seen_onshape_part_ids) if seen_onshape_part_ids else True,
                OnshapeLink.stale.is_(False),
            )
            .all()
        )
        for link in stale_links:
            link.stale = True

        # ── Finalize ───────────────────────────────────────────

        sync_log.completed_at = datetime.now(UTC)
        sync_log.status = "success"
        sync_log.parts_created = parts_created
        sync_log.parts_updated = parts_updated
        sync_log.bom_lines_created = bom_lines_created
        sync_log.bom_lines_updated = bom_lines_updated
        sync_log.bom_lines_removed = bom_lines_removed
        sync_log.summary = (
            f"Pull sync complete: {parts_created} parts created, "
            f"{parts_updated} updated, {bom_lines_created} BOM lines created, "
            f"{bom_lines_updated} updated, {bom_lines_removed} removed"
        )

        if errors:
            sync_log.status = "partial"
            sync_log.errors = {"messages": errors}

        db.commit()
        logger.info("Pull sync complete: %s", sync_log.summary)

    except Exception as e:
        sync_log.completed_at = datetime.now(UTC)
        sync_log.status = "error"
        sync_log.errors = {"messages": [str(e)]}
        sync_log.summary = f"Pull sync failed: {e}"
        db.commit()
        logger.exception("Pull sync failed for document %s", doc_ref.document_id)

    return sync_log


def push_sync(
    db: Session,
    client: OnshapeClient,
    doc_ref: OnshapeDocumentRef,
    user_id: int | None = None,
    trigger: str = "manual",
    part_ids: list[int] | None = None,
) -> "OnshapeSyncLog":
    """Push OPAL ERP data back to Onshape custom properties.

    Writes internal_pn and configured field mappings to Onshape metadata.

    Args:
        db: Database session.
        client: Authenticated Onshape API client.
        doc_ref: Document reference from project config.
        user_id: User who triggered the sync.
        trigger: What triggered the sync.
        part_ids: If provided, only push these specific parts.

    Returns:
        OnshapeSyncLog with results.
    """
    from opal.config import get_active_project
    from opal.db.models.onshape_link import OnshapeLink, OnshapeSyncLog

    now = datetime.now(UTC)
    sync_log = OnshapeSyncLog(
        started_at=now,
        direction="push",
        trigger=trigger,
        status="running",
        document_id=doc_ref.document_id,
        user_id=user_id,
    )
    db.add(sync_log)
    db.flush()

    project = get_active_project()
    field_mapping = project.onshape.field_mapping if project else {"internal_pn": "Part Number"}

    parts_updated = 0
    errors: list[str] = []

    try:
        # Resolve workspace_id
        workspace_id = doc_ref.workspace_id
        if not workspace_id:
            doc = client.get_document(doc_ref.document_id)
            workspace_id = doc.default_workspace_id or ""

        # Query links for this document
        query = db.query(OnshapeLink).filter(
            OnshapeLink.document_id == doc_ref.document_id,
            OnshapeLink.stale.is_(False),
        )
        if part_ids:
            query = query.filter(OnshapeLink.part_id.in_(part_ids))

        links = query.all()

        for link in links:
            part = link.part
            push_hash = _compute_push_hash(part.internal_pn, part.category, part.tier)

            # Skip if nothing changed since last push
            if link.push_hash == push_hash and not part_ids:
                continue

            # Build properties to push
            properties = []
            for opal_field, onshape_prop_name in field_mapping.items():
                value = getattr(part, opal_field, None)
                if value is not None:
                    properties.append({
                        "propertyId": onshape_prop_name,
                        "value": str(value),
                    })

            if not properties:
                continue

            try:
                # First get existing metadata to find property IDs
                existing = client.get_metadata(
                    document_id=doc_ref.document_id,
                    workspace_id=workspace_id,
                    element_id=link.element_id,
                    part_id=link.part_id_onshape,
                )

                # Map property names to actual property IDs
                name_to_id = {p.name: p.property_id for p in existing if p.property_id}
                resolved_properties = []
                for prop in properties:
                    prop_id = name_to_id.get(prop["propertyId"])
                    if prop_id:
                        resolved_properties.append({
                            "propertyId": prop_id,
                            "value": prop["value"],
                        })

                if resolved_properties:
                    client.set_metadata(
                        document_id=doc_ref.document_id,
                        workspace_id=workspace_id,
                        element_id=link.element_id,
                        part_id=link.part_id_onshape,
                        properties=resolved_properties,
                    )

                link.push_hash = push_hash
                link.last_synced_at = datetime.now(UTC)
                parts_updated += 1

            except Exception as e:
                errors.append(f"Failed to push part {part.internal_pn}: {e}")
                logger.warning("Push failed for link %s: %s", link.id, e)

        sync_log.completed_at = datetime.now(UTC)
        sync_log.parts_updated = parts_updated
        sync_log.status = "success" if not errors else "partial"
        sync_log.summary = f"Push sync complete: {parts_updated} parts updated"
        if errors:
            sync_log.errors = {"messages": errors}

        db.commit()
        logger.info("Push sync complete: %s", sync_log.summary)

    except Exception as e:
        sync_log.completed_at = datetime.now(UTC)
        sync_log.status = "error"
        sync_log.errors = {"messages": [str(e)]}
        sync_log.summary = f"Push sync failed: {e}"
        db.commit()
        logger.exception("Push sync failed for document %s", doc_ref.document_id)

    return sync_log

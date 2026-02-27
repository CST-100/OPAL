"""Onshape sync engine — pull and push sync operations."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from opal.core.audit import get_model_dict, log_create, log_delete, log_update
from opal.integrations.onshape.client import OnshapeClient
from opal.integrations.onshape.models import OnshapeBOMItem
from opal.project import OnshapeDocumentRef

if TYPE_CHECKING:
    from opal.db.models.onshape_link import OnshapeSyncLog

logger = logging.getLogger(__name__)

ROOT_ASSEMBLY_MARKER = "__asm_root__"


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


def _fetch_part_studio_items(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
) -> list[OnshapeBOMItem]:
    """Fetch parts from a part studio and wrap them as BOM items.

    Part studios contain a flat list of parts (no hierarchy), so each
    part is returned with quantity=1 and no children.
    """
    parts = client.get_parts(
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
    )
    logger.info("Part studio returned %d parts for element %s", len(parts), element_id)
    for p in parts:
        logger.debug("  part: id=%r name=%r pn=%r", p.part_id, p.name, p.part_number)
    return [
        OnshapeBOMItem(
            item_source={"partId": p.part_id, "material": p.material},
            source_element_id=element_id,
            part_id=p.part_id,
            part_name=p.name,
            part_number=p.part_number,
            description=p.description,
            quantity=1,
            children=[],
        )
        for p in parts
    ]


def _flatten_bom(items: list[OnshapeBOMItem]) -> list[OnshapeBOMItem]:
    """Flatten nested BOM into a deduplicated list of all items.

    Deduplicates by composite key (source_element_id:part_id) since
    Onshape part_ids are only unique within a Part Studio element.
    Parts from different Part Studios with the same part_id are kept
    as separate entries.
    """
    seen: set[str] = set()  # composite key: "source_element_id:part_id"
    result: list[OnshapeBOMItem] = []

    def _walk(items: list[OnshapeBOMItem]) -> None:
        for item in items:
            dedup_key = f"{item.source_element_id}:{item.part_id}"
            if item.part_id and dedup_key not in seen:
                seen.add(dedup_key)
                result.append(item)
            elif not item.part_id:
                result.append(item)
            if item.children:
                _walk(item.children)

    _walk(items)
    return result


def _sync_bom_structure(
    db: Session,
    bom_items: list[OnshapeBOMItem],
    assembly_part_id: int,
    onshape_to_opal: dict[str, int],
    user_id: int | None,
    visited: set[int] | None = None,
    default_element_id: str = "",
) -> tuple[int, int, int]:
    """Sync BOM lines from hierarchical Onshape BOM items.

    Returns (created, updated, removed) counts.

    Args:
        db: Database session.
        bom_items: Children of the current assembly level.
        assembly_part_id: OPAL Part.id of the parent assembly.
        onshape_to_opal: Mapping from composite key "source_eid:part_id" to OPAL Part.id.
        user_id: User who triggered the sync.
        visited: Set of OPAL Part.ids already visited (cycle detection).
        default_element_id: Fallback element_id when item has no source_element_id.
    """
    from opal.db.models.part import BOMLine

    if visited is None:
        visited = set()

    if assembly_part_id in visited:
        logger.warning(
            "Cycle detected: OPAL Part %d already visited, skipping BOM sync",
            assembly_part_id,
        )
        return (0, 0, 0)

    visited = visited | {assembly_part_id}  # Copy to allow DAG structures

    created = 0
    updated = 0
    removed = 0

    # Build map of current BOM lines for this assembly
    existing_lines = {
        bl.component_id: bl
        for bl in db.query(BOMLine)
        .filter(BOMLine.assembly_id == assembly_part_id)
        .all()
    }

    # Pass 1: resolve all items to component_id, accumulate quantities,
    # and track the first item ("representative") for children recursion.
    component_agg: dict[int, tuple[int, OnshapeBOMItem]] = {}  # comp_id → (total_qty, first_item)

    for item in bom_items:
        if not item.part_id:
            continue

        source_eid = item.source_element_id or default_element_id
        composite_key = f"{source_eid}:{item.part_id}"
        component_id = onshape_to_opal.get(composite_key)
        if component_id is None:
            logger.warning(
                "Child link not found in mapping for Onshape key=%r, skipping",
                composite_key,
            )
            continue

        if component_id in component_agg:
            existing_qty, representative = component_agg[component_id]
            component_agg[component_id] = (existing_qty + item.quantity, representative)
        else:
            component_agg[component_id] = (item.quantity, item)

    # Pass 2: create/update BOM lines with accumulated quantities
    seen_component_ids: set[int] = set()

    for component_id, (total_qty, representative) in component_agg.items():
        seen_component_ids.add(component_id)

        if component_id in existing_lines:
            # Update quantity if changed
            bl = existing_lines[component_id]
            if bl.quantity != total_qty:
                old_values = get_model_dict(bl)
                bl.quantity = total_qty
                log_update(db, bl, old_values, user_id)
                updated += 1
        else:
            # Create new BOM line
            bl = BOMLine(
                assembly_id=assembly_part_id,
                component_id=component_id,
                quantity=total_qty,
            )
            db.add(bl)
            db.flush()
            log_create(db, bl, user_id)
            created += 1

        # Recurse into representative's children
        if representative.children:
            c, u, r = _sync_bom_structure(
                db, representative.children, component_id, onshape_to_opal, user_id,
                visited, default_element_id,
            )
            created += c
            updated += u
            removed += r

    # Remove BOM lines for components no longer in Onshape BOM
    for comp_id, bl in existing_lines.items():
        if comp_id not in seen_component_ids:
            log_delete(db, bl, user_id)
            db.delete(bl)
            removed += 1

    return (created, updated, removed)


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
    from opal.db.models.part import Part

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
    parts_restored = 0
    bom_lines_created = 0
    bom_lines_updated = 0
    bom_lines_removed = 0
    new_part_ids: list[int] = []

    try:
        # ── Phase 0: Fetch + validate ─────────────────────────

        workspace_id = doc_ref.workspace_id
        if not workspace_id:
            doc = client.get_document(doc_ref.document_id)
            workspace_id = doc.default_workspace_id or ""

        is_part_studio = doc_ref.element_type == "part_studio"

        if is_part_studio:
            flat_items = _fetch_part_studio_items(
                client,
                document_id=doc_ref.document_id,
                workspace_id=workspace_id,
                element_id=doc_ref.element_id,
            )
            bom_items: list[OnshapeBOMItem] = []
        else:
            bom = client.get_bom(
                document_id=doc_ref.document_id,
                workspace_id=workspace_id,
                element_id=doc_ref.element_id,
            )
            bom_items = bom.items
            flat_items = _flatten_bom(bom.items)

            # Surface BOM parse warnings as sync errors for visibility
            for w in bom.warnings:
                errors.append(f"BOM parse [{w.field}]: {w.message}")

        logger.info(
            "Fetched %d items from Onshape (element_type=%s)",
            len(flat_items), doc_ref.element_type,
        )

        # Validate: warn on empty names
        for item in flat_items:
            if not item.part_id or item.is_standard_content:
                continue
            if not item.part_name:
                msg = f"Empty name for Onshape part_id={item.part_id!r}"
                errors.append(msg)
                logger.warning(msg)

        # ── Phase 0b: Root assembly (assemblies only) ─────────

        onshape_to_opal: dict[str, int] = {}  # composite key "source_eid:part_id" → OPAL Part.id
        root_assembly_part_id: int | None = None
        seen_link_ids: set[int] = set()
        seen_source_eids: set[str] = set()

        if not is_part_studio:
            root_link = (
                db.query(OnshapeLink)
                .filter(
                    OnshapeLink.document_id == doc_ref.document_id,
                    OnshapeLink.element_id == doc_ref.element_id,
                    OnshapeLink.part_id_onshape == ROOT_ASSEMBLY_MARKER,
                )
                .first()
            )
            if root_link:
                root_assembly_part_id = root_link.part_id
                root_link.last_synced_at = now
                root_link.stale = False
                root_part = root_link.part
                if root_part.name != doc_ref.name:
                    old_values = get_model_dict(root_part)
                    root_part.name = doc_ref.name
                    log_update(db, root_part, old_values, user_id)
            else:
                internal_pn = _generate_internal_pn(db, default_tier)
                root_part = Part(
                    name=doc_ref.name,
                    internal_pn=internal_pn,
                    tier=default_tier,
                    category=default_category,
                )
                db.add(root_part)
                db.flush()
                log_create(db, root_part, user_id)

                root_link = OnshapeLink(
                    part_id=root_part.id,
                    document_id=doc_ref.document_id,
                    element_id=doc_ref.element_id,
                    part_id_onshape=ROOT_ASSEMBLY_MARKER,
                    onshape_name=doc_ref.name,
                    last_synced_at=now,
                )
                db.add(root_link)
                db.flush()
                log_create(db, root_link, user_id)

                root_assembly_part_id = root_part.id
                parts_created += 1
            seen_link_ids.add(root_link.id)

        # ── Phase 1: Part resolution ──────────────────────────

        # Name-based dedup: track part_name → OPAL Part.id so that the same
        # physical part from different Onshape coordinates (different Part Studios
        # with different partId values) maps to a single OPAL Part.
        name_to_part_id: dict[str, int] = {}

        # Pre-populate from existing links for this document (handles re-sync
        # when BOM order changes between syncs)
        existing_doc_links = (
            db.query(OnshapeLink)
            .join(Part, OnshapeLink.part_id == Part.id)
            .filter(
                OnshapeLink.document_id == doc_ref.document_id,
                OnshapeLink.stale.is_(False),
                Part.deleted_at.is_(None),
            )
            .all()
        )
        for el in existing_doc_links:
            if el.onshape_name:
                name_to_part_id[el.onshape_name] = el.part_id

        items_with_empty_id = 0
        items_unchanged = 0

        for item in flat_items:
            if not item.part_id:
                items_with_empty_id += 1
                logger.warning("Skipping item with empty part_id: name=%r", item.part_name)
                continue
            if item.is_standard_content:
                logger.debug("Skipping standard content: name=%r", item.part_name)
                continue

            # Use the part's source Part Studio element_id for link scoping,
            # falling back to the doc_ref element_id for part studios or items
            # without an itemSource.elementId.
            source_eid = item.source_element_id or doc_ref.element_id
            composite_key = f"{source_eid}:{item.part_id}"

            pull_hash = _compute_pull_hash(item.part_name, item.description, item.part_number)

            link = (
                db.query(OnshapeLink)
                .filter(
                    OnshapeLink.document_id == doc_ref.document_id,
                    OnshapeLink.element_id == source_eid,
                    OnshapeLink.part_id_onshape == item.part_id,
                )
                .first()
            )

            if link:
                part = link.part
                if part.deleted_at is not None:
                    old_values = get_model_dict(part)
                    part.deleted_at = None
                    log_update(db, part, old_values, user_id)
                    parts_restored += 1
                    logger.info(
                        "Restored soft-deleted part %s (Onshape %s)",
                        part.internal_pn, item.part_id,
                    )

                if link.pull_hash == pull_hash:
                    link.last_synced_at = now
                    link.stale = False
                    items_unchanged += 1
                    onshape_to_opal[composite_key] = part.id
                    seen_link_ids.add(link.id)
                    seen_source_eids.add(source_eid)
                    if item.part_name:
                        name_to_part_id[item.part_name] = part.id
                    continue

                old_values = get_model_dict(part)
                part.name = item.part_name
                part.external_pn = item.part_number or part.external_pn
                if item.description:
                    part.description = item.description
                material = (item.item_source or {}).get("material")
                if material:
                    part.metadata_ = {**(part.metadata_ or {}), "material": material}
                log_update(db, part, old_values, user_id)

                link.onshape_name = item.part_name
                link.onshape_part_number = item.part_number
                link.pull_hash = pull_hash
                link.last_synced_at = now
                link.stale = False
                parts_updated += 1
                onshape_to_opal[composite_key] = part.id
                seen_link_ids.add(link.id)
                seen_source_eids.add(source_eid)
                if item.part_name:
                    name_to_part_id[item.part_name] = part.id

            else:
                # Name-based dedup: if another Onshape coordinate already
                # resolved to an OPAL Part with the same name, reuse it
                # instead of creating a duplicate.
                if item.part_name and item.part_name in name_to_part_id:
                    onshape_to_opal[composite_key] = name_to_part_id[item.part_name]
                    seen_source_eids.add(source_eid)
                    continue

                internal_pn = _generate_internal_pn(db, default_tier)
                part = Part(
                    name=item.part_name,
                    description=item.description or None,
                    internal_pn=internal_pn,
                    external_pn=item.part_number or None,
                    tier=default_tier,
                    category=default_category,
                )
                material = (item.item_source or {}).get("material")
                if material:
                    part.metadata_ = {"material": material}
                db.add(part)
                db.flush()
                log_create(db, part, user_id)

                link = OnshapeLink(
                    part_id=part.id,
                    document_id=doc_ref.document_id,
                    element_id=source_eid,
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
                onshape_to_opal[composite_key] = part.id
                seen_link_ids.add(link.id)
                seen_source_eids.add(source_eid)
                if item.part_name:
                    name_to_part_id[item.part_name] = part.id

        # ── Phase 2: BOM structure (assemblies only) ──────────

        if not is_part_studio and root_assembly_part_id is not None:
            bom_lines_created, bom_lines_updated, bom_lines_removed = (
                _sync_bom_structure(
                    db, bom_items, root_assembly_part_id,
                    onshape_to_opal, user_id,
                    default_element_id=doc_ref.element_id,
                )
            )

        # ── Mark stale links ──────────────────────────────────

        if seen_link_ids:
            # Include the assembly element itself so the root link isn't orphaned
            seen_source_eids.add(doc_ref.element_id)
            stale_links = (
                db.query(OnshapeLink)
                .filter(
                    OnshapeLink.document_id == doc_ref.document_id,
                    OnshapeLink.element_id.in_(seen_source_eids),
                    OnshapeLink.id.notin_(seen_link_ids),
                    OnshapeLink.stale.is_(False),
                )
                .all()
            )
            for link in stale_links:
                link.stale = True

        # ── Finalize ──────────────────────────────────────────

        sync_log.completed_at = datetime.now(UTC)
        sync_log.status = "success"
        sync_log.parts_created = parts_created
        sync_log.parts_updated = parts_updated
        sync_log.bom_lines_created = bom_lines_created
        sync_log.bom_lines_updated = bom_lines_updated
        sync_log.bom_lines_removed = bom_lines_removed

        summary_parts = [
            f"{parts_created} parts created",
            f"{parts_updated} updated",
        ]
        if parts_restored > 0:
            summary_parts.append(f"{parts_restored} restored")
        if not is_part_studio:
            summary_parts.append(f"{bom_lines_created} BOM lines added")

        summary = "Pull sync complete: " + ", ".join(summary_parts)

        all_eids = seen_source_eids | {doc_ref.element_id}
        total_linked = (
            db.query(OnshapeLink)
            .filter(
                OnshapeLink.document_id == doc_ref.document_id,
                OnshapeLink.element_id.in_(all_eids),
                OnshapeLink.stale.is_(False),
            )
            .count()
        )

        if total_linked > 0 and parts_created == 0 and parts_updated == 0 and parts_restored == 0:
            suffix = "part" if total_linked == 1 else "parts"
            summary += f" — {total_linked} {suffix} already linked"
        elif total_linked > 0:
            suffix = "part" if total_linked == 1 else "parts"
            summary += f" ({total_linked} {suffix} linked total)"

        if len(flat_items) == 0:
            summary += (
                f"\n(API returned 0 items: "
                f"{items_with_empty_id} skipped [no ID], "
                f"{items_unchanged} unchanged)"
            )

        sync_log.summary = summary

        if errors:
            sync_log.status = "partial"
            sync_log.errors = {"messages": errors}

        db.commit()
        logger.info("Pull sync complete: %s", sync_log.summary)

        # ── Auto-push PNs for newly created parts ─────────────
        if new_part_ids:
            logger.info(
                "Auto-pushing PNs for %d newly created parts", len(new_part_ids)
            )
            push_log = push_sync(
                db, client, doc_ref, user_id,
                trigger="auto",
                part_ids=new_part_ids,
            )
            if push_log.parts_updated:
                logger.info(
                    "Auto-push complete: %d PNs written to Onshape",
                    push_log.parts_updated,
                )

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

        # Query links for this document (links store source element_id which
        # may differ from doc_ref.element_id for assembly BOM items)
        query = db.query(OnshapeLink).filter(
            OnshapeLink.document_id == doc_ref.document_id,
            OnshapeLink.stale.is_(False),
        )
        if part_ids:
            query = query.filter(OnshapeLink.part_id.in_(part_ids))

        links = query.all()

        for link in links:
            if link.part_id_onshape == ROOT_ASSEMBLY_MARKER:
                continue
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

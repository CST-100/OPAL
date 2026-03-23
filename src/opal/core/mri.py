"""OPALcode MRI (Machine-Readable Identifier) system.

Encodes and decodes host-independent identifiers for all OPAL entities.
These are the strings that go into QR codes / labels.

Format: OPAL:{type}:{identifier}

Types:
    P  = Part (by internal PN)
    I  = Inventory record (PN/serial, PN/lot, or OPAL number)
    L  = Location
    C  = Container (WIP/kit)
    W  = Work order
    T  = Issue ticket
    R  = Risk
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

# Type prefix constants
PART = "P"
INVENTORY = "I"
LOCATION = "L"
CONTAINER = "C"
WORK_ORDER = "W"
ISSUE = "T"
RISK = "R"

PREFIX = "OPAL"


@dataclass
class MRIResult:
    """Result of decoding an OPALcode."""

    type: str  # "part", "inventory", "location", "container", "work_order", "issue", "risk"
    id: int | None
    label: str
    sublabel: str = ""
    entity: Any = None


def encode_part_mri(part: Any) -> str:
    """Encode a Part into an OPALcode."""
    pn = part.internal_pn or str(part.id)
    return f"{PREFIX}:{PART}:{pn}"


def encode_inventory_mri(record: Any) -> str:
    """Encode an InventoryRecord into an OPALcode.

    Prefers PN/lot or PN/serial for human readability.
    Falls back to OPAL number.
    """
    part = record.part
    pn = part.internal_pn or str(part.id) if part else None

    if pn and record.lot_number:
        return f"{PREFIX}:{INVENTORY}:{pn}/{record.lot_number}"
    if pn and record.opal_number:
        # For serialized parts, use the OPAL number as the serial identifier
        return f"{PREFIX}:{INVENTORY}:{pn}/{record.opal_number}"
    if record.opal_number:
        return f"{PREFIX}:{INVENTORY}:{record.opal_number}"
    return f"{PREFIX}:{INVENTORY}:{record.id}"


def encode_location_mri(code: str) -> str:
    """Encode a location code into an OPALcode."""
    return f"{PREFIX}:{LOCATION}:{code}"


def encode_container_mri(code: str) -> str:
    """Encode a container code into an OPALcode."""
    return f"{PREFIX}:{CONTAINER}:{code}"


def encode_work_order_mri(wo_number: str) -> str:
    """Encode a work order number into an OPALcode."""
    return f"{PREFIX}:{WORK_ORDER}:{wo_number}"


def encode_issue_mri(issue_number: str) -> str:
    """Encode an issue number into an OPALcode."""
    return f"{PREFIX}:{ISSUE}:{issue_number}"


def encode_risk_mri(risk_number: str) -> str:
    """Encode a risk number into an OPALcode."""
    return f"{PREFIX}:{RISK}:{risk_number}"


def decode_mri(db: Session, code: str) -> MRIResult | None:
    """Decode an OPALcode string and resolve the entity from the database.

    Returns None if the code format is invalid.
    Returns MRIResult with entity=None if the format is valid but entity not found.
    """
    if not code.startswith(f"{PREFIX}:"):
        return None

    remainder = code[len(f"{PREFIX}:"):]
    if ":" not in remainder:
        return None

    type_char = remainder[0]
    if remainder[1] != ":":
        return None
    identifier = remainder[2:]

    if not identifier:
        return None

    if type_char == PART:
        return _resolve_part(db, identifier)
    elif type_char == INVENTORY:
        return _resolve_inventory(db, identifier)
    elif type_char == LOCATION:
        return _resolve_location(db, identifier)
    elif type_char == CONTAINER:
        return _resolve_container(db, identifier)
    elif type_char == WORK_ORDER:
        return _resolve_work_order(db, identifier)
    elif type_char == ISSUE:
        return _resolve_issue(db, identifier)
    elif type_char == RISK:
        return _resolve_risk(db, identifier)
    else:
        return None


def _resolve_part(db: Session, identifier: str) -> MRIResult:
    from opal.db.models import Part

    part = db.query(Part).filter(
        Part.internal_pn == identifier, Part.deleted_at.is_(None),
    ).first()
    if not part:
        # Try by ID
        try:
            part = db.query(Part).filter(
                Part.id == int(identifier), Part.deleted_at.is_(None),
            ).first()
        except ValueError:
            pass

    if part:
        return MRIResult(
            type="part", id=part.id,
            label=part.name, sublabel=part.internal_pn or "",
            entity=part,
        )
    return MRIResult(type="part", id=None, label=identifier, sublabel="Not found")


def _resolve_inventory(db: Session, identifier: str) -> MRIResult:
    from opal.db.models import InventoryRecord, Part

    # Try PN/qualifier format (e.g., KST-F-0002/001 or KST-D-0039/LOT-2026-001)
    if "/" in identifier:
        pn, qualifier = identifier.rsplit("/", 1)

        # Find part by PN
        part = db.query(Part).filter(
            Part.internal_pn == pn, Part.deleted_at.is_(None),
        ).first()

        if part:
            # Try lot number match first
            record = db.query(InventoryRecord).filter(
                InventoryRecord.part_id == part.id,
                InventoryRecord.lot_number == qualifier,
            ).first()
            if record:
                return _inventory_result(record)

            # Try OPAL number match
            record = db.query(InventoryRecord).filter(
                InventoryRecord.part_id == part.id,
                InventoryRecord.opal_number == qualifier,
            ).first()
            if record:
                return _inventory_result(record)

    # Try direct OPAL number (e.g., OPAL-00042)
    record = db.query(InventoryRecord).filter(
        InventoryRecord.opal_number == identifier,
    ).first()
    if record:
        return _inventory_result(record)

    return MRIResult(type="inventory", id=None, label=identifier, sublabel="Not found")


def _inventory_result(record: Any) -> MRIResult:
    part_name = record.part.name if record.part else "Unknown"
    sublabel_parts = []
    if record.opal_number:
        sublabel_parts.append(record.opal_number)
    if record.location:
        sublabel_parts.append(record.location)
    return MRIResult(
        type="inventory", id=record.id,
        label=part_name,
        sublabel=" | ".join(sublabel_parts),
        entity=record,
    )


def _resolve_location(db: Session, identifier: str) -> MRIResult:
    # Location model may not exist yet — graceful fallback
    try:
        from opal.db.models.location import Location
        loc = db.query(Location).filter(Location.code == identifier).first()
        if loc:
            return MRIResult(
                type="location", id=loc.id,
                label=loc.name or loc.code, sublabel=loc.code,
                entity=loc,
            )
    except Exception:
        pass

    # Fallback: check if any inventory records use this as a location string
    from opal.db.models import InventoryRecord
    count = db.query(InventoryRecord).filter(
        InventoryRecord.location == identifier,
    ).count()
    if count > 0:
        return MRIResult(
            type="location", id=None,
            label=identifier, sublabel=f"{count} items",
        )
    return MRIResult(type="location", id=None, label=identifier, sublabel="Not found")


def _resolve_container(db: Session, identifier: str) -> MRIResult:
    try:
        from opal.db.models.container import Container
        container = db.query(Container).filter(Container.code == identifier).first()
        if container:
            return MRIResult(
                type="container", id=container.id,
                label=container.name or container.code,
                sublabel=container.code,
                entity=container,
            )
    except Exception:
        pass
    return MRIResult(type="container", id=None, label=identifier, sublabel="Not found")


def _resolve_work_order(db: Session, identifier: str) -> MRIResult:
    from opal.db.models import ProcedureInstance

    instance = db.query(ProcedureInstance).filter(
        ProcedureInstance.work_order_number == identifier,
    ).first()
    if instance:
        proc_name = instance.procedure.name if instance.procedure else ""
        status = instance.status.value if hasattr(instance.status, "value") else str(instance.status)
        return MRIResult(
            type="work_order", id=instance.id,
            label=f"{identifier} — {proc_name}",
            sublabel=status.upper(),
            entity=instance,
        )
    return MRIResult(type="work_order", id=None, label=identifier, sublabel="Not found")


def _resolve_issue(db: Session, identifier: str) -> MRIResult:
    from opal.db.models import Issue

    issue = db.query(Issue).filter(
        Issue.issue_number == identifier, Issue.deleted_at.is_(None),
    ).first()
    if issue:
        status = issue.status.value if hasattr(issue.status, "value") else str(issue.status)
        return MRIResult(
            type="issue", id=issue.id,
            label=issue.title,
            sublabel=f"{identifier} | {status.upper()}",
            entity=issue,
        )
    return MRIResult(type="issue", id=None, label=identifier, sublabel="Not found")


def _resolve_risk(db: Session, identifier: str) -> MRIResult:
    from opal.db.models import Risk

    risk = db.query(Risk).filter(
        Risk.risk_number == identifier, Risk.deleted_at.is_(None),
    ).first()
    if risk:
        return MRIResult(
            type="risk", id=risk.id,
            label=risk.title,
            sublabel=f"{identifier} | Score: {risk.score}",
            entity=risk,
        )
    return MRIResult(type="risk", id=None, label=identifier, sublabel="Not found")

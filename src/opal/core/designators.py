"""Designator generation utilities.

Provides atomic generation of sequential designators for various entity types:
- OPAL-XXXXX: Physical items (inventory, sensors, assemblies)
- WO-XXXXX: Work orders (procedure instances)
- IT-XXXXX: Issues
- RISK-XXXXX: Risks
- SN-{PN}-XXXX: Serial numbers per part number
"""

from sqlalchemy.orm import Session

from opal.db.models.designator import DesignatorSequence


# Designator type constants
OPAL = "OPAL"
WORK_ORDER = "WO"
ISSUE = "IT"
RISK = "RISK"
SERIAL = "SN"

# Known simple prefixes (serial numbers use compound prefix SN-{PN})
_SIMPLE_PREFIXES = (OPAL, WORK_ORDER, ISSUE, RISK)


def generate_designator(db: Session, designator_type: str, digits: int = 5) -> str:
    """Generate the next sequential designator of the given type.

    Uses atomic increment on the DesignatorSequence table to ensure
    unique sequential numbers even under concurrent access.

    Args:
        db: Database session
        designator_type: Type of designator (OPAL, WO, IT, RISK, or SN-{PN})
        digits: Number of digits for zero-padding (default 5)

    Returns:
        The next designator string (e.g., "OPAL-00001", "WO-00042")
    """
    # Get or create the sequence record
    seq = db.query(DesignatorSequence).filter(
        DesignatorSequence.designator_type == designator_type
    ).with_for_update().first()

    if seq is None:
        # First time using this designator type - create sequence
        seq = DesignatorSequence(designator_type=designator_type, last_value=0)
        db.add(seq)

    # Increment and return
    seq.last_value += 1
    next_num = seq.last_value

    # Flush to ensure the increment is persisted before we return
    db.flush()

    return f"{designator_type}-{next_num:0{digits}d}"


def generate_opal_number(db: Session) -> str:
    """Generate the next OPAL number for physical items.

    Format: OPAL-XXXXX (5 digits, zero-padded)
    Example: OPAL-00001, OPAL-00042, OPAL-12345

    Args:
        db: Database session

    Returns:
        The next available OPAL number.
    """
    return generate_designator(db, OPAL)


def generate_work_order_number(db: Session) -> str:
    """Generate the next work order number.

    Format: WO-XXXXX (5 digits, zero-padded)
    Example: WO-00001, WO-00042

    Args:
        db: Database session

    Returns:
        The next available work order number.
    """
    return generate_designator(db, WORK_ORDER)


def generate_issue_number(db: Session) -> str:
    """Generate the next issue number.

    Format: IT-XXXXX (5 digits, zero-padded)
    Example: IT-00001, IT-00042

    Args:
        db: Database session

    Returns:
        The next available issue number.
    """
    return generate_designator(db, ISSUE)


def generate_risk_number(db: Session) -> str:
    """Generate the next risk number.

    Format: RISK-XXXXX (5 digits, zero-padded)
    Example: RISK-00001, RISK-00042

    Args:
        db: Database session

    Returns:
        The next available risk number.
    """
    return generate_designator(db, RISK)


def generate_serial_number(db: Session, part) -> str:
    """Generate the next serial number for a specific part.

    Uses the part's internal_pn (or ID as fallback) to create a per-part
    sequence. Each part gets its own independent counter.

    Format: SN-{PN}-XXXX (4 digits, zero-padded)
    Example: SN-PO/1-001-0001, SN-42-0001

    Args:
        db: Database session
        part: Part model instance

    Returns:
        The next serial number for this part.
    """
    part_key = part.internal_pn or str(part.id)
    seq_key = f"SN-{part_key}"
    return generate_designator(db, seq_key, digits=4)


def get_designator_type(designator: str) -> str | None:
    """Extract the type from a designator string.

    Args:
        designator: A designator string like "OPAL-00042" or "SN-PO/1-001-0003"

    Returns:
        The type prefix (OPAL, WO, IT, RISK, SN) or None if invalid format.
    """
    if not designator or "-" not in designator:
        return None

    prefix = designator.split("-")[0].upper()
    if prefix in _SIMPLE_PREFIXES:
        return prefix
    if prefix == SERIAL:
        return SERIAL
    return None


def parse_designator(designator: str) -> tuple[str, int] | None:
    """Parse a designator into its type and sequence number.

    For simple designators (OPAL, WO, IT, RISK): returns (type, number).
    For serial numbers (SN-{PN}-XXXX): returns ("SN", number) where number
    is the trailing sequence.

    Args:
        designator: A designator string like "OPAL-00042" or "SN-PO/1-001-0003"

    Returns:
        Tuple of (type, number) or None if invalid format.
        Example: ("OPAL", 42) or ("SN", 3)
    """
    if not designator or "-" not in designator:
        return None

    try:
        prefix = designator.split("-")[0].upper()

        if prefix in _SIMPLE_PREFIXES:
            _, num_str = designator.split("-", 1)
            return (prefix, int(num_str))

        if prefix == SERIAL:
            # Serial numbers have format SN-{PN}-XXXX; sequence is the last segment
            last_segment = designator.rsplit("-", 1)[-1]
            return (SERIAL, int(last_segment))

        return None
    except (ValueError, AttributeError):
        return None

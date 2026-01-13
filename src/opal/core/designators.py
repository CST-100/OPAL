"""Designator generation utilities.

Provides atomic generation of sequential designators for various entity types:
- OPAL-XXXXX: Physical items (inventory, sensors, assemblies)
- WO-XXXXX: Work orders (procedure instances)
- IT-XXXXX: Issues
- RISK-XXXXX: Risks
"""

from sqlalchemy.orm import Session

from opal.db.models.designator import DesignatorSequence


# Designator type constants
OPAL = "OPAL"
WORK_ORDER = "WO"
ISSUE = "IT"
RISK = "RISK"


def generate_designator(db: Session, designator_type: str, digits: int = 5) -> str:
    """Generate the next sequential designator of the given type.

    Uses atomic increment on the DesignatorSequence table to ensure
    unique sequential numbers even under concurrent access.

    Args:
        db: Database session
        designator_type: Type of designator (OPAL, WO, IT, RISK)
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


def get_designator_type(designator: str) -> str | None:
    """Extract the type from a designator string.

    Args:
        designator: A designator string like "OPAL-00042" or "WO-00015"

    Returns:
        The type prefix (OPAL, WO, IT, RISK) or None if invalid format.
    """
    if not designator or "-" not in designator:
        return None

    prefix = designator.split("-")[0].upper()
    if prefix in (OPAL, WORK_ORDER, ISSUE, RISK):
        return prefix
    return None


def parse_designator(designator: str) -> tuple[str, int] | None:
    """Parse a designator into its type and sequence number.

    Args:
        designator: A designator string like "OPAL-00042"

    Returns:
        Tuple of (type, number) or None if invalid format.
        Example: ("OPAL", 42)
    """
    if not designator or "-" not in designator:
        return None

    try:
        prefix, num_str = designator.split("-", 1)
        prefix = prefix.upper()
        if prefix not in (OPAL, WORK_ORDER, ISSUE, RISK):
            return None
        return (prefix, int(num_str))
    except (ValueError, AttributeError):
        return None

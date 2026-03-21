"""Core business logic tests — designators, audit, and diff."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from opal.core.audit import get_changes, get_model_dict, log_create, log_delete, log_update
from opal.core.designators import (
    generate_issue_number,
    generate_opal_number,
    generate_risk_number,
    generate_serial_number,
    generate_work_order_number,
    get_designator_type,
    parse_designator,
)
from opal.core.diff import diff_procedure_versions
from opal.db.models import AuditLog, Part
from opal.db.models.audit import AuditAction


# ---- Local fixtures ----


@pytest.fixture
def sample_part(db_session: Session) -> Part:
    """Part with internal_pn set."""
    part = Part(name="Widget", internal_pn="PO/1-001")
    db_session.add(part)
    db_session.flush()
    return part


@pytest.fixture
def sample_part_no_pn(db_session: Session) -> Part:
    """Part without internal_pn (falls back to ID)."""
    part = Part(name="Gizmo")
    db_session.add(part)
    db_session.flush()
    return part


# ============ Designators ============


def test_generate_opal_number(db_session: Session) -> None:
    result = generate_opal_number(db_session)
    assert result == "OPAL-00001"


def test_generate_work_order_number(db_session: Session) -> None:
    result = generate_work_order_number(db_session)
    assert result == "WO-00001"


def test_generate_issue_number(db_session: Session) -> None:
    result = generate_issue_number(db_session)
    assert result == "IT-00001"


def test_generate_risk_number(db_session: Session) -> None:
    result = generate_risk_number(db_session)
    assert result == "RISK-00001"


def test_generate_designator_sequential(db_session: Session) -> None:
    first = generate_opal_number(db_session)
    second = generate_opal_number(db_session)
    assert first == "OPAL-00001"
    assert second == "OPAL-00002"


def test_generate_designator_types_isolated(db_session: Session) -> None:
    opal = generate_opal_number(db_session)
    wo = generate_work_order_number(db_session)
    assert opal == "OPAL-00001"
    assert wo == "WO-00001"


def test_generate_serial_number(db_session: Session, sample_part: Part) -> None:
    result = generate_serial_number(db_session, sample_part)
    assert result == "001"


def test_generate_serial_number_uses_internal_pn(
    db_session: Session, sample_part: Part
) -> None:
    generate_serial_number(db_session, sample_part)
    from opal.db.models.designator import DesignatorSequence

    seq = (
        db_session.query(DesignatorSequence)
        .filter(DesignatorSequence.designator_type == "SN-PO/1-001")
        .first()
    )
    assert seq is not None
    assert seq.last_value == 1


def test_generate_serial_number_falls_back_to_id(
    db_session: Session, sample_part_no_pn: Part
) -> None:
    generate_serial_number(db_session, sample_part_no_pn)
    from opal.db.models.designator import DesignatorSequence

    seq = (
        db_session.query(DesignatorSequence)
        .filter(DesignatorSequence.designator_type == f"SN-{sample_part_no_pn.id}")
        .first()
    )
    assert seq is not None


def test_generate_serial_number_per_part_isolation(
    db_session: Session, sample_part: Part, sample_part_no_pn: Part
) -> None:
    s1 = generate_serial_number(db_session, sample_part)
    s2 = generate_serial_number(db_session, sample_part_no_pn)
    assert s1 == "001"
    assert s2 == "001"


def test_get_designator_type() -> None:
    assert get_designator_type("OPAL-00042") == "OPAL"
    assert get_designator_type("WO-00001") == "WO"
    assert get_designator_type("IT-00005") == "IT"
    assert get_designator_type("RISK-00010") == "RISK"


def test_get_designator_type_serial() -> None:
    assert get_designator_type("SN-PO/1-001-003") == "SN"


def test_get_designator_type_invalid() -> None:
    assert get_designator_type("") is None
    assert get_designator_type("NOPE") is None
    assert get_designator_type("UNKNOWN-123") is None


def test_parse_designator_simple() -> None:
    assert parse_designator("OPAL-00042") == ("OPAL", 42)
    assert parse_designator("WO-00001") == ("WO", 1)
    assert parse_designator("IT-00005") == ("IT", 5)
    assert parse_designator("RISK-00010") == ("RISK", 10)


def test_parse_designator_plain_serial() -> None:
    assert parse_designator("001") == ("SN", 1)
    assert parse_designator("042") == ("SN", 42)


def test_parse_designator_legacy_serial() -> None:
    assert parse_designator("SN-PO/1-001-0003") == ("SN", 3)


def test_parse_designator_invalid() -> None:
    assert parse_designator("") is None
    assert parse_designator("NOPE") is None
    assert parse_designator("OPAL-abc") is None


# ============ Audit ============


def test_get_model_dict(db_session: Session, sample_part: Part) -> None:
    d = get_model_dict(sample_part)
    assert d["name"] == "Widget"
    assert d["internal_pn"] == "PO/1-001"
    assert isinstance(d["id"], int)
    # datetime should be serialized to ISO string
    assert isinstance(d["created_at"], str)


def test_get_model_dict_enum_serialization(db_session: Session) -> None:
    part = Part(name="Bulk Stuff", tracking_type="bulk")
    db_session.add(part)
    db_session.flush()
    d = get_model_dict(part)
    assert d["tracking_type"] == "bulk"


def test_get_changes() -> None:
    old = {"name": "A", "qty": 1, "loc": "X"}
    new = {"name": "B", "qty": 1, "loc": "Y"}
    changes = get_changes(old, new)
    assert changes == {"name": "B", "loc": "Y"}


def test_get_changes_no_diff() -> None:
    d = {"name": "A", "qty": 1}
    assert get_changes(d, d) == {}


def test_log_create(db_session: Session, sample_part: Part) -> None:
    entry = log_create(db_session, sample_part, user_id=None)
    db_session.flush()
    assert entry.action == AuditAction.CREATE
    assert entry.table_name == "part"
    assert entry.record_id == sample_part.id
    assert entry.new_values is not None
    assert entry.old_values is None


def test_log_update(db_session: Session, sample_part: Part) -> None:
    old_values = get_model_dict(sample_part)
    sample_part.name = "Updated Widget"
    db_session.flush()
    entry = log_update(db_session, sample_part, old_values, user_id=None)
    assert entry is not None
    assert entry.action == AuditAction.UPDATE
    assert "name" in entry.new_values


def test_log_update_no_changes(db_session: Session, sample_part: Part) -> None:
    old_values = get_model_dict(sample_part)
    result = log_update(db_session, sample_part, old_values, user_id=None)
    assert result is None


def test_log_delete(db_session: Session, sample_part: Part) -> None:
    entry = log_delete(db_session, sample_part, user_id=None)
    db_session.flush()
    assert entry.action == AuditAction.DELETE
    assert entry.old_values is not None
    assert entry.new_values is None


# ============ Diff ============


def test_diff_procedure_versions_name_change() -> None:
    a = {"procedure_name": "Old Name", "steps": []}
    b = {"procedure_name": "New Name", "steps": []}
    proc_changes, step_diffs = diff_procedure_versions(a, b)
    assert "procedure_name" in proc_changes
    assert len(step_diffs) == 0


def test_diff_procedure_versions_step_added() -> None:
    a = {"steps": []}
    b = {"steps": [{"step_number": "1", "title": "New Step"}]}
    _, diffs = diff_procedure_versions(a, b)
    assert len(diffs) == 1
    assert diffs[0].status == "added"
    assert diffs[0].step_b["title"] == "New Step"


def test_diff_procedure_versions_step_removed() -> None:
    a = {"steps": [{"step_number": "1", "title": "Old Step"}]}
    b = {"steps": []}
    _, diffs = diff_procedure_versions(a, b)
    assert len(diffs) == 1
    assert diffs[0].status == "removed"
    assert diffs[0].step_a["title"] == "Old Step"


def test_diff_procedure_versions_step_modified() -> None:
    a = {"steps": [{"step_number": "1", "title": "Before"}]}
    b = {"steps": [{"step_number": "1", "title": "After"}]}
    _, diffs = diff_procedure_versions(a, b)
    assert len(diffs) == 1
    assert diffs[0].status == "modified"
    assert "title" in diffs[0].changed_fields

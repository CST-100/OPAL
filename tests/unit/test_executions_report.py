"""Smoke tests for the BUILD REPORT route at /executions/{id}/report."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from opal.db.models import User
from opal.db.models.attachment import Attachment
from opal.db.models.dataset import DataPoint, Dataset
from opal.db.models.execution import InstanceStatus, ProcedureInstance


@pytest.fixture
def web_client(client: TestClient, test_user: User) -> TestClient:
    """TestClient pre-authenticated with the cookie the auth middleware expects."""
    client.cookies.set("opal_user_id", str(test_user.id))
    return client


def _create_completed_instance(client: TestClient, db_session: Session) -> ProcedureInstance:
    """Create a published procedure + an instance, force status to COMPLETED."""
    proc_resp = client.post("/api/procedures", json={"name": "Build Report Proc"})
    assert proc_resp.status_code in (200, 201), proc_resp.text
    proc_id = proc_resp.json()["id"]

    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Solder"})
    client.post(f"/api/procedures/{proc_id}/publish")

    inst_resp = client.post("/api/procedure-instances", json={"procedure_id": proc_id})
    assert inst_resp.status_code == 201, inst_resp.text
    instance_id = inst_resp.json()["id"]

    instance = db_session.query(ProcedureInstance).filter(ProcedureInstance.id == instance_id).one()
    instance.status = InstanceStatus.COMPLETED
    instance.started_at = datetime.now(UTC)
    instance.completed_at = datetime.now(UTC)
    db_session.commit()
    db_session.refresh(instance)
    return instance


def test_report_renders_when_completed(web_client: TestClient, db_session: Session):
    instance = _create_completed_instance(web_client, db_session)
    resp = web_client.get(f"/executions/{instance.id}/report")
    assert resp.status_code == 200
    body = resp.text
    assert "BUILD REPORT" in body
    assert "OPERATIONS SUMMARY" in body
    assert "CLOSEOUT PHOTOS" in body


def test_report_rejects_when_not_completed(web_client: TestClient, db_session: Session):
    proc_resp = web_client.post("/api/procedures", json={"name": "Pending Proc"})
    proc_id = proc_resp.json()["id"]
    web_client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 1"})
    web_client.post(f"/api/procedures/{proc_id}/publish")
    inst_resp = web_client.post("/api/procedure-instances", json={"procedure_id": proc_id})
    instance_id = inst_resp.json()["id"]
    # Status stays PENDING - route should refuse.
    resp = web_client.get(f"/executions/{instance_id}/report")
    assert resp.status_code == 400
    assert "PENDING" in resp.text or "COMPLETED" in resp.text


def test_report_includes_only_closeout_photos(web_client: TestClient, db_session: Session):
    instance = _create_completed_instance(web_client, db_session)

    closeout = Attachment(
        original_filename="closeout_shot.jpg",
        stored_filename="closeout-uuid.jpg",
        mime_type="image/jpeg",
        size_bytes=1234,
        kind="closeout",
        procedure_instance_id=instance.id,
    )
    plain = Attachment(
        original_filename="random_note.txt",
        stored_filename="plain-uuid.txt",
        mime_type="text/plain",
        size_bytes=10,
        kind=None,
        procedure_instance_id=instance.id,
    )
    db_session.add_all([closeout, plain])
    db_session.commit()
    db_session.refresh(closeout)
    db_session.refresh(plain)

    resp = web_client.get(f"/executions/{instance.id}/report")
    assert resp.status_code == 200
    body = resp.text
    assert f"/api/attachments/{closeout.id}/download" in body
    assert f"/api/attachments/{plain.id}/download" not in body


def test_report_charts_only_fields_marked_chart_true(web_client: TestClient, db_session: Session):
    instance = _create_completed_instance(web_client, db_session)

    # Grab a real step execution to anchor data points to this WO.
    db_session.refresh(instance)
    step_exec = instance.step_executions[0]

    dataset = Dataset(
        name="Build Readings",
        schema={
            "fields": [
                {"name": "pressure", "type": "number", "unit": "PSI", "chart": True},
                {"name": "temperature", "type": "number", "unit": "C"},
                {"name": "notes", "type": "text", "chart": True},
            ]
        },
    )
    db_session.add(dataset)
    db_session.flush()

    point = DataPoint(
        dataset_id=dataset.id,
        recorded_at=datetime.now(UTC),
        values={"pressure": 120, "temperature": 22, "notes": "ok"},
        step_execution_id=step_exec.id,
    )
    db_session.add(point)
    db_session.commit()

    resp = web_client.get(f"/executions/{instance.id}/report")
    assert resp.status_code == 200
    body = resp.text

    # The pressure field is numeric + chart:true → a canvas is rendered.
    assert f'id="chart-{dataset.id}-0"' in body
    # Only one chart canvas for this dataset: temperature lacks chart:true,
    # and notes is non-numeric so it must be excluded even though chart:true.
    assert f'id="chart-{dataset.id}-1"' not in body
    # And the field name "pressure" should appear in the data-field attribute.
    assert 'data-field="pressure"' in body or "data-field='pressure'" in body

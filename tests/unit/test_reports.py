"""Tests for reports API routes."""

import pytest
from fastapi.testclient import TestClient


def test_export_parts_csv(client: TestClient):
    """Test parts CSV export."""
    # Create a part first
    part = client.post(
        "/api/parts",
        json={"name": "Test Part", "external_pn": "TP-001"},
        headers={"X-User-ID": "1"},
    )
    assert part.status_code == 201

    # Export as CSV
    response = client.get("/api/reports/parts/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "Content-Disposition" in response.headers
    assert "parts_export" in response.headers["Content-Disposition"]

    # Check CSV content
    content = response.text
    assert "ID" in content
    assert "External PN" in content
    assert "TP-001" in content


def test_export_parts_csv_with_category_filter(client: TestClient):
    """Test parts CSV export with category filter."""
    # Create parts with different categories
    client.post(
        "/api/parts",
        json={"name": "Electronic Part", "external_pn": "EP-001", "category": "electronics"},
        headers={"X-User-ID": "1"},
    )
    client.post(
        "/api/parts",
        json={"name": "Mechanical Part", "external_pn": "MP-001", "category": "mechanical"},
        headers={"X-User-ID": "1"},
    )

    # Export with filter
    response = client.get("/api/reports/parts/csv?category=electronics")
    assert response.status_code == 200

    content = response.text
    assert "EP-001" in content
    # Should only have electronics parts


def test_export_inventory_csv(client: TestClient):
    """Test inventory CSV export."""
    # Create a part and add inventory
    part = client.post(
        "/api/parts",
        json={"name": "Inv Test Part", "external_pn": "ITP-001"},
        headers={"X-User-ID": "1"},
    ).json()

    client.post(
        "/api/inventory",
        json={"part_id": part["id"], "quantity": 50, "location": "Warehouse A"},
        headers={"X-User-ID": "1"},
    )

    # Export as CSV
    response = client.get("/api/reports/inventory/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    content = response.text
    assert "Warehouse A" in content


def test_export_executions_csv(client: TestClient):
    """Test executions CSV export."""
    # Create a procedure and execute it
    procedure = client.post(
        "/api/procedures",
        json={"name": "Test Proc", "code": "TP-001"},
        headers={"X-User-ID": "1"},
    ).json()

    # Add a step
    client.post(
        f"/api/procedures/{procedure['id']}/steps",
        json={"title": "Step 1", "order": 1, "instruction": "Do something"},
        headers={"X-User-ID": "1"},
    )

    # Publish
    client.post(
        f"/api/procedures/{procedure['id']}/publish",
        headers={"X-User-ID": "1"},
    )

    # Create instance
    instance = client.post(
        "/api/procedure-instances",
        json={"procedure_id": procedure["id"]},
        headers={"X-User-ID": "1"},
    ).json()

    # Export as CSV
    response = client.get("/api/reports/executions/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    content = response.text
    assert "Test Proc" in content or str(instance["id"]) in content


def test_export_executions_csv_with_status_filter(client: TestClient):
    """Test executions CSV export with status filter."""
    response = client.get("/api/reports/executions/csv?status=completed")
    assert response.status_code == 200


def test_export_issues_csv(client: TestClient):
    """Test issues CSV export."""
    # Create an issue
    client.post(
        "/api/issues",
        json={"title": "Test Issue", "issue_type": "bug", "priority": "high"},
        headers={"X-User-ID": "1"},
    )

    # Export as CSV
    response = client.get("/api/reports/issues/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    content = response.text
    assert "Test Issue" in content


def test_export_issues_csv_with_filters(client: TestClient):
    """Test issues CSV export with filters."""
    response = client.get("/api/reports/issues/csv?status=open&issue_type=bug")
    assert response.status_code == 200


def test_export_risks_csv(client: TestClient):
    """Test risks CSV export."""
    # Create a risk
    client.post(
        "/api/risks",
        json={"title": "Test Risk", "probability": 3, "impact": 4},
        headers={"X-User-ID": "1"},
    )

    # Export as CSV
    response = client.get("/api/reports/risks/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    content = response.text
    assert "Test Risk" in content


def test_export_risks_csv_with_min_score(client: TestClient):
    """Test risks CSV export with minimum score filter."""
    response = client.get("/api/reports/risks/csv?min_score=10")
    assert response.status_code == 200


def test_execution_metrics(client: TestClient):
    """Test execution analytics metrics."""
    response = client.get("/api/reports/analytics/executions")
    assert response.status_code == 200

    data = response.json()
    assert "total_executions" in data
    assert "completed" in data
    assert "in_progress" in data
    assert "pending" in data
    assert "completion_rate" in data


def test_execution_metrics_with_filters(client: TestClient):
    """Test execution metrics with date filters."""
    response = client.get(
        "/api/reports/analytics/executions?from_date=2024-01-01T00:00:00Z"
    )
    assert response.status_code == 200


def test_issue_metrics(client: TestClient):
    """Test issue analytics metrics."""
    # Create some issues
    client.post(
        "/api/issues",
        json={"title": "Bug 1", "issue_type": "bug", "priority": "high"},
        headers={"X-User-ID": "1"},
    )
    client.post(
        "/api/issues",
        json={"title": "Task 1", "issue_type": "task", "priority": "low"},
        headers={"X-User-ID": "1"},
    )

    response = client.get("/api/reports/analytics/issues")
    assert response.status_code == 200

    data = response.json()
    assert "total_issues" in data
    assert "open" in data
    assert "by_type" in data
    assert "by_priority" in data


def test_issue_metrics_with_date_filters(client: TestClient):
    """Test issue metrics with date filters."""
    response = client.get(
        "/api/reports/analytics/issues?from_date=2024-01-01T00:00:00Z&to_date=2025-12-31T23:59:59Z"
    )
    assert response.status_code == 200

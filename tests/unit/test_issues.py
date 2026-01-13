"""Issues API tests."""


def test_create_issue(client):
    """Test creating a new issue."""
    response = client.post(
        "/api/issues",
        json={
            "title": "Test Bug",
            "description": "Something is broken",
            "issue_type": "bug",
            "priority": "high",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Test Bug"
    assert data["description"] == "Something is broken"
    assert data["issue_type"] == "bug"
    assert data["priority"] == "high"
    assert data["status"] == "open"


def test_list_issues(client):
    """Test listing issues."""
    client.post("/api/issues", json={"title": "Issue A"})
    client.post("/api/issues", json={"title": "Issue B"})

    response = client.get("/api/issues")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2


def test_filter_issues_by_type(client):
    """Test filtering issues by type."""
    client.post("/api/issues", json={"title": "Bug 1", "issue_type": "bug"})
    client.post("/api/issues", json={"title": "Task 1", "issue_type": "task"})

    response = client.get("/api/issues?issue_type=bug")
    assert response.status_code == 200

    data = response.json()
    assert all(i["issue_type"] == "bug" for i in data["items"])


def test_filter_issues_by_status(client):
    """Test filtering issues by status."""
    # Create and update one to resolved
    issue1 = client.post("/api/issues", json={"title": "Open Issue"}).json()
    issue2 = client.post("/api/issues", json={"title": "Resolved Issue"}).json()
    client.patch(f"/api/issues/{issue2['id']}", json={"status": "resolved"})

    response = client.get("/api/issues?status=open")
    assert response.status_code == 200

    data = response.json()
    assert all(i["status"] == "open" for i in data["items"])


def test_get_issue(client):
    """Test getting a specific issue."""
    create_response = client.post(
        "/api/issues",
        json={"title": "Specific Issue"},
    )
    issue_id = create_response.json()["id"]

    response = client.get(f"/api/issues/{issue_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Specific Issue"


def test_update_issue(client):
    """Test updating an issue."""
    create_response = client.post(
        "/api/issues",
        json={"title": "Original Title"},
    )
    issue_id = create_response.json()["id"]

    response = client.patch(
        f"/api/issues/{issue_id}",
        json={
            "title": "Updated Title",
            "status": "in_progress",
            "priority": "critical",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["status"] == "in_progress"
    assert data["priority"] == "critical"


def test_delete_issue(client):
    """Test soft deleting an issue."""
    create_response = client.post(
        "/api/issues",
        json={"title": "To Be Deleted"},
    )
    issue_id = create_response.json()["id"]

    response = client.delete(f"/api/issues/{issue_id}")
    assert response.status_code == 204

    # Should not be found
    get_response = client.get(f"/api/issues/{issue_id}")
    assert get_response.status_code == 404


def test_issue_with_part_link(client):
    """Test creating an issue linked to a part."""
    # Create part
    part_response = client.post("/api/parts", json={"name": "Widget"})
    part_id = part_response.json()["id"]

    # Create issue linked to part
    response = client.post(
        "/api/issues",
        json={"title": "Part Issue", "part_id": part_id},
    )
    assert response.status_code == 201
    assert response.json()["part_id"] == part_id


def test_issue_with_procedure_link(client):
    """Test creating an issue linked to a procedure."""
    # Create procedure
    proc_response = client.post("/api/procedures", json={"name": "Test Proc"})
    proc_id = proc_response.json()["id"]

    # Create issue linked to procedure
    response = client.post(
        "/api/issues",
        json={"title": "Procedure Issue", "procedure_id": proc_id},
    )
    assert response.status_code == 201
    assert response.json()["procedure_id"] == proc_id


def test_get_issue_types(client):
    """Test getting issue types."""
    response = client.get("/api/issues/types")
    assert response.status_code == 200

    types = response.json()
    assert "non_conformance" in types
    assert "bug" in types
    assert "task" in types
    assert "improvement" in types


def test_get_issue_statuses(client):
    """Test getting issue statuses."""
    response = client.get("/api/issues/statuses")
    assert response.status_code == 200

    statuses = response.json()
    assert "open" in statuses
    assert "in_progress" in statuses
    assert "resolved" in statuses
    assert "closed" in statuses


def test_get_issue_priorities(client):
    """Test getting issue priorities."""
    response = client.get("/api/issues/priorities")
    assert response.status_code == 200

    priorities = response.json()
    assert "low" in priorities
    assert "medium" in priorities
    assert "high" in priorities
    assert "critical" in priorities

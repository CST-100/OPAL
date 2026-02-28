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
    # Create and update one to disposition_approved (with required disposition_type)
    client.post("/api/issues", json={"title": "Open Issue"})
    issue2 = client.post("/api/issues", json={"title": "Approved Issue"}).json()
    client.patch(
        f"/api/issues/{issue2['id']}",
        json={"status": "disposition_approved", "disposition_type": "use_as_is"},
    )

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
            "status": "investigating",
            "priority": "critical",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["status"] == "investigating"
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
    assert "investigating" in statuses
    assert "disposition_pending" in statuses
    assert "disposition_approved" in statuses
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


def test_create_issue_comment(client):
    """Test adding a comment to an issue."""
    issue = client.post("/api/issues", json={"title": "Comment Test"}).json()

    response = client.post(
        f"/api/issues/{issue['id']}/comments",
        json={"body": "This is a test comment"},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["body"] == "This is a test comment"
    assert data["issue_id"] == issue["id"]


def test_list_issue_comments(client):
    """Test listing comments on an issue in chronological order."""
    issue = client.post("/api/issues", json={"title": "Comments List Test"}).json()

    client.post(f"/api/issues/{issue['id']}/comments", json={"body": "First comment"})
    client.post(f"/api/issues/{issue['id']}/comments", json={"body": "Second comment"})

    response = client.get(f"/api/issues/{issue['id']}/comments")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["body"] == "First comment"
    assert data[1]["body"] == "Second comment"


def test_update_issue_disposition(client):
    """Test setting disposition fields on an issue."""
    issue = client.post("/api/issues", json={"title": "Disposition Test"}).json()

    response = client.patch(
        f"/api/issues/{issue['id']}",
        json={
            "root_cause": "Material defect",
            "corrective_action": "Replace batch",
            "disposition_type": "rework",
            "disposition_notes": "Rework per procedure",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["root_cause"] == "Material defect"
    assert data["corrective_action"] == "Replace batch"
    assert data["disposition_type"] == "rework"
    assert data["disposition_notes"] == "Rework per procedure"


def test_disposition_approval_requires_type(client):
    """Test that approving disposition requires disposition_type to be set."""
    issue = client.post("/api/issues", json={"title": "Approval Test"}).json()

    # Try to approve without disposition_type — should fail
    response = client.patch(
        f"/api/issues/{issue['id']}",
        json={"status": "disposition_approved"},
    )
    assert response.status_code == 400
    assert "disposition_type" in response.json()["detail"]

    # Set disposition_type first, then approve — should succeed
    client.patch(
        f"/api/issues/{issue['id']}",
        json={"disposition_type": "scrap"},
    )
    response = client.patch(
        f"/api/issues/{issue['id']}",
        json={"status": "disposition_approved"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "disposition_approved"

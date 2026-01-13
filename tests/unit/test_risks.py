"""Risks API tests."""


def test_create_risk(client):
    """Test creating a new risk."""
    response = client.post(
        "/api/risks",
        json={
            "title": "Equipment Failure",
            "description": "Critical equipment may fail during operation",
            "probability": 3,
            "impact": 4,
            "mitigation_plan": "Schedule regular maintenance",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Equipment Failure"
    assert data["probability"] == 3
    assert data["impact"] == 4
    assert data["score"] == 12
    assert data["severity"] == "medium"
    assert data["status"] == "identified"


def test_list_risks(client):
    """Test listing risks."""
    client.post("/api/risks", json={"title": "Risk A", "probability": 2, "impact": 2})
    client.post("/api/risks", json={"title": "Risk B", "probability": 5, "impact": 5})

    response = client.get("/api/risks")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2


def test_filter_risks_by_status(client):
    """Test filtering risks by status."""
    # Create and update one
    risk1 = client.post("/api/risks", json={"title": "Active Risk"}).json()
    risk2 = client.post("/api/risks", json={"title": "Closed Risk"}).json()
    client.patch(f"/api/risks/{risk2['id']}", json={"status": "closed"})

    response = client.get("/api/risks?status=identified")
    assert response.status_code == 200

    data = response.json()
    # All returned should be identified status
    assert all(i["status"] == "identified" for i in data["items"])


def test_get_risk(client):
    """Test getting a specific risk."""
    create_response = client.post(
        "/api/risks",
        json={"title": "Specific Risk", "probability": 4, "impact": 5},
    )
    risk_id = create_response.json()["id"]

    response = client.get(f"/api/risks/{risk_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Specific Risk"
    assert response.json()["score"] == 20
    assert response.json()["severity"] == "high"


def test_update_risk(client):
    """Test updating a risk."""
    create_response = client.post(
        "/api/risks",
        json={"title": "Original Title", "probability": 3, "impact": 3},
    )
    risk_id = create_response.json()["id"]

    response = client.patch(
        f"/api/risks/{risk_id}",
        json={
            "title": "Updated Title",
            "status": "mitigating",
            "probability": 2,
            "impact": 2,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["status"] == "mitigating"
    assert data["score"] == 4
    assert data["severity"] == "low"


def test_delete_risk(client):
    """Test soft deleting a risk."""
    create_response = client.post(
        "/api/risks",
        json={"title": "To Be Deleted"},
    )
    risk_id = create_response.json()["id"]

    response = client.delete(f"/api/risks/{risk_id}")
    assert response.status_code == 204

    # Should not be found
    get_response = client.get(f"/api/risks/{risk_id}")
    assert get_response.status_code == 404


def test_risk_score_calculations(client):
    """Test that risk scores are calculated correctly."""
    # Low risk (score <= 5)
    low = client.post("/api/risks", json={"title": "Low", "probability": 1, "impact": 5}).json()
    assert low["score"] == 5
    assert low["severity"] == "low"

    # Medium risk (score 6-12)
    med = client.post("/api/risks", json={"title": "Med", "probability": 3, "impact": 4}).json()
    assert med["score"] == 12
    assert med["severity"] == "medium"

    # High risk (score 13-25)
    high = client.post("/api/risks", json={"title": "High", "probability": 5, "impact": 5}).json()
    assert high["score"] == 25
    assert high["severity"] == "high"


def test_risk_with_linked_issue(client):
    """Test creating a risk linked to an issue."""
    # Create issue
    issue_response = client.post("/api/issues", json={"title": "Related Issue"})
    issue_id = issue_response.json()["id"]

    # Create risk linked to issue
    response = client.post(
        "/api/risks",
        json={"title": "Linked Risk", "linked_issue_id": issue_id},
    )
    assert response.status_code == 201
    assert response.json()["linked_issue_id"] == issue_id


def test_get_risk_statuses(client):
    """Test getting risk statuses."""
    response = client.get("/api/risks/statuses")
    assert response.status_code == 200

    statuses = response.json()
    assert "identified" in statuses
    assert "analyzing" in statuses
    assert "mitigating" in statuses
    assert "monitoring" in statuses
    assert "closed" in statuses


def test_get_risk_matrix(client):
    """Test getting risk matrix data."""
    # Create some risks
    client.post("/api/risks", json={"title": "R1", "probability": 1, "impact": 1})
    client.post("/api/risks", json={"title": "R2", "probability": 5, "impact": 5})
    client.post("/api/risks", json={"title": "R3", "probability": 3, "impact": 3})

    response = client.get("/api/risks/matrix")
    assert response.status_code == 200

    data = response.json()
    assert "matrix" in data
    assert len(data["matrix"]) == 5  # 5x5 matrix
    assert len(data["matrix"][0]) == 5
    assert data["total_risks"] >= 3

"""Health endpoint tests."""


def test_health_check(client):
    """Test health check endpoint returns healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"

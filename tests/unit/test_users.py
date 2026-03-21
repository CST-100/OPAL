"""User endpoint tests."""


def test_create_user(client, admin_headers):
    """Test creating a new user."""
    response = client.post(
        "/api/users",
        json={"name": "Alice", "email": "alice@example.com"},
        headers=admin_headers,
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


def test_list_users(client, test_user, admin_headers):
    """Test listing users."""
    response = client.get("/api/users", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1

    # Find our test user
    user_ids = [u["id"] for u in data["items"]]
    assert test_user.id in user_ids


def test_get_user(client, test_user):
    """Test getting a specific user."""
    response = client.get(f"/api/users/{test_user.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == test_user.id
    assert data["name"] == test_user.name


def test_get_user_not_found(client):
    """Test getting a non-existent user."""
    response = client.get("/api/users/99999")
    assert response.status_code == 404


def test_update_user(client, test_user, auth_headers):
    """Test updating a user."""
    response = client.patch(
        f"/api/users/{test_user.id}",
        json={"name": "Updated Name"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["id"] == test_user.id

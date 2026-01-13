"""Parts API tests."""


def test_create_part(client):
    """Test creating a new part."""
    response = client.post(
        "/api/parts",
        json={
            "name": "Test Resistor",
            "external_pn": "RES-10K",
            "category": "Electronics",
            "unit_of_measure": "ea",
            "description": "10K ohm resistor",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Test Resistor"
    assert data["external_pn"] == "RES-10K"
    assert data["category"] == "Electronics"
    assert data["unit_of_measure"] == "ea"
    assert float(data["total_quantity"]) == 0
    assert "id" in data


def test_list_parts(client):
    """Test listing parts."""
    # Create a part first
    client.post(
        "/api/parts",
        json={"name": "Part A", "category": "Cat1"},
    )
    client.post(
        "/api/parts",
        json={"name": "Part B", "category": "Cat2"},
    )

    response = client.get("/api/parts")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


def test_list_parts_with_search(client):
    """Test searching parts."""
    client.post("/api/parts", json={"name": "Widget Alpha"})
    client.post("/api/parts", json={"name": "Gadget Beta"})

    response = client.get("/api/parts?search=Widget")
    assert response.status_code == 200

    data = response.json()
    assert all("Widget" in item["name"] for item in data["items"])


def test_list_parts_with_category_filter(client):
    """Test filtering parts by category."""
    client.post("/api/parts", json={"name": "Part X", "category": "TypeA"})
    client.post("/api/parts", json={"name": "Part Y", "category": "TypeB"})

    response = client.get("/api/parts?category=TypeA")
    assert response.status_code == 200

    data = response.json()
    assert all(item["category"] == "TypeA" for item in data["items"])


def test_get_part(client):
    """Test getting a specific part."""
    create_response = client.post(
        "/api/parts",
        json={"name": "Specific Part"},
    )
    part_id = create_response.json()["id"]

    response = client.get(f"/api/parts/{part_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == part_id
    assert data["name"] == "Specific Part"


def test_get_part_not_found(client):
    """Test getting a non-existent part."""
    response = client.get("/api/parts/99999")
    assert response.status_code == 404


def test_update_part(client):
    """Test updating a part."""
    create_response = client.post(
        "/api/parts",
        json={"name": "Original Name"},
    )
    part_id = create_response.json()["id"]

    response = client.patch(
        f"/api/parts/{part_id}",
        json={"name": "Updated Name", "category": "New Category"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["category"] == "New Category"


def test_delete_part(client):
    """Test soft deleting a part."""
    create_response = client.post(
        "/api/parts",
        json={"name": "To Be Deleted"},
    )
    part_id = create_response.json()["id"]

    response = client.delete(f"/api/parts/{part_id}")
    assert response.status_code == 204

    # Part should not be found now (soft deleted)
    get_response = client.get(f"/api/parts/{part_id}")
    assert get_response.status_code == 404


def test_get_categories(client):
    """Test getting unique categories."""
    client.post("/api/parts", json={"name": "P1", "category": "Electronics"})
    client.post("/api/parts", json={"name": "P2", "category": "Mechanical"})
    client.post("/api/parts", json={"name": "P3", "category": "Electronics"})

    response = client.get("/api/parts/categories")
    assert response.status_code == 200

    categories = response.json()
    assert "Electronics" in categories
    assert "Mechanical" in categories

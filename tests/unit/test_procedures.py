"""Procedures API tests."""


def test_create_procedure(client):
    """Test creating a new procedure."""
    response = client.post(
        "/api/procedures",
        json={
            "name": "Assembly Procedure",
            "description": "Steps for assembling widget",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Assembly Procedure"
    assert data["description"] == "Steps for assembling widget"
    assert data["status"] == "draft"
    assert "id" in data


def test_list_procedures(client):
    """Test listing procedures."""
    # Create procedures
    client.post("/api/procedures", json={"name": "Procedure A"})
    client.post("/api/procedures", json={"name": "Procedure B"})

    response = client.get("/api/procedures")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


def test_get_procedure(client):
    """Test getting a specific procedure."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Specific Procedure"},
    )
    proc_id = create_response.json()["id"]

    response = client.get(f"/api/procedures/{proc_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == proc_id
    assert data["name"] == "Specific Procedure"


def test_update_procedure(client):
    """Test updating a procedure."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Original Name"},
    )
    proc_id = create_response.json()["id"]

    response = client.patch(
        f"/api/procedures/{proc_id}",
        json={"name": "Updated Name", "status": "active"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["status"] == "active"


def test_delete_procedure(client):
    """Test soft deleting a procedure."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "To Be Deleted"},
    )
    proc_id = create_response.json()["id"]

    response = client.delete(f"/api/procedures/{proc_id}")
    assert response.status_code == 204

    # Procedure should not be found now
    get_response = client.get(f"/api/procedures/{proc_id}")
    assert get_response.status_code == 404


def test_add_step(client):
    """Test adding a step to a procedure."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Step Test Procedure"},
    )
    proc_id = create_response.json()["id"]

    response = client.post(
        f"/api/procedures/{proc_id}/steps",
        json={
            "title": "First Step",
            "instructions": "Do the thing",
            "estimated_duration_minutes": 15,
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "First Step"
    assert data["order"] == 1
    assert data["estimated_duration_minutes"] == 15


def test_add_multiple_steps(client):
    """Test adding multiple steps maintains order."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Multi-Step Procedure"},
    )
    proc_id = create_response.json()["id"]

    # Add three steps
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 1"})
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 2"})
    step3_response = client.post(
        f"/api/procedures/{proc_id}/steps",
        json={"title": "Step 3"},
    )

    assert step3_response.json()["order"] == 3

    # Get procedure with steps
    response = client.get(f"/api/procedures/{proc_id}")
    data = response.json()
    assert len(data["steps"]) == 3


def test_update_step(client):
    """Test updating a step."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Update Step Procedure"},
    )
    proc_id = create_response.json()["id"]

    step_response = client.post(
        f"/api/procedures/{proc_id}/steps",
        json={"title": "Original Title"},
    )
    step_id = step_response.json()["id"]

    response = client.patch(
        f"/api/procedures/{proc_id}/steps/{step_id}",
        json={"title": "Updated Title", "is_contingency": True},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"
    assert response.json()["is_contingency"] is True


def test_delete_step(client):
    """Test deleting a step reorders remaining steps."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Delete Step Procedure"},
    )
    proc_id = create_response.json()["id"]

    # Add three steps
    step1 = client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 1"}).json()
    step2 = client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 2"}).json()
    step3 = client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 3"}).json()

    # Delete step 2
    delete_response = client.delete(f"/api/procedures/{proc_id}/steps/{step2['id']}")
    assert delete_response.status_code == 204

    # Check remaining steps are reordered
    proc_response = client.get(f"/api/procedures/{proc_id}")
    steps = proc_response.json()["steps"]
    assert len(steps) == 2
    assert steps[0]["title"] == "Step 1"
    assert steps[0]["order"] == 1
    assert steps[1]["title"] == "Step 3"
    assert steps[1]["order"] == 2


def test_publish_version(client):
    """Test publishing a procedure version."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Version Test Procedure"},
    )
    proc_id = create_response.json()["id"]

    # Add steps
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 1"})
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 2"})

    # Publish
    response = client.post(f"/api/procedures/{proc_id}/publish")
    assert response.status_code == 201

    data = response.json()
    assert data["version_number"] == 1

    # Procedure should now be active
    proc_response = client.get(f"/api/procedures/{proc_id}")
    assert proc_response.json()["status"] == "active"
    assert proc_response.json()["current_version_id"] == data["id"]


def test_cannot_publish_without_steps(client):
    """Test cannot publish procedure without steps."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Empty Procedure"},
    )
    proc_id = create_response.json()["id"]

    response = client.post(f"/api/procedures/{proc_id}/publish")
    assert response.status_code == 400


def test_list_versions(client):
    """Test listing procedure versions."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Multiple Versions"},
    )
    proc_id = create_response.json()["id"]

    # Add step and publish twice
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 1"})
    client.post(f"/api/procedures/{proc_id}/publish")

    # Add another step and publish again
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 2"})
    client.post(f"/api/procedures/{proc_id}/publish")

    response = client.get(f"/api/procedures/{proc_id}/versions")
    assert response.status_code == 200

    versions = response.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2  # Most recent first
    assert versions[1]["version_number"] == 1


def test_kit_crud(client):
    """Test kit (bill of materials) CRUD."""
    # Create procedure
    proc_response = client.post("/api/procedures", json={"name": "Kit Test Procedure"})
    proc_id = proc_response.json()["id"]

    # Create part
    part_response = client.post("/api/parts", json={"name": "Widget Part"})
    part_id = part_response.json()["id"]

    # Add to kit
    kit_response = client.post(
        f"/api/procedures/{proc_id}/kit",
        json={"part_id": part_id, "quantity_required": 2.5},
    )
    assert kit_response.status_code == 201
    assert kit_response.json()["quantity_required"] == 2.5

    # Get kit
    get_response = client.get(f"/api/procedures/{proc_id}/kit")
    assert get_response.status_code == 200
    assert len(get_response.json()) == 1

    # Remove from kit
    delete_response = client.delete(f"/api/procedures/{proc_id}/kit/{part_id}")
    assert delete_response.status_code == 204

    # Verify removed
    verify_response = client.get(f"/api/procedures/{proc_id}/kit")
    assert len(verify_response.json()) == 0


def test_cannot_add_duplicate_kit_item(client):
    """Test cannot add same part twice to kit."""
    proc_response = client.post("/api/procedures", json={"name": "Duplicate Kit Test"})
    proc_id = proc_response.json()["id"]

    part_response = client.post("/api/parts", json={"name": "Unique Part"})
    part_id = part_response.json()["id"]

    # Add first time
    client.post(f"/api/procedures/{proc_id}/kit", json={"part_id": part_id, "quantity_required": 1})

    # Try to add again
    response = client.post(
        f"/api/procedures/{proc_id}/kit",
        json={"part_id": part_id, "quantity_required": 2},
    )
    assert response.status_code == 400

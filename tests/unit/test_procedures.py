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


def test_update_procedure_type(client):
    """Test changing procedure_type from op to build persists correctly."""
    create_response = client.post(
        "/api/procedures",
        json={"name": "Build Procedure", "procedure_type": "op"},
    )
    assert create_response.status_code == 201
    proc_id = create_response.json()["id"]
    assert create_response.json()["procedure_type"] == "op"

    # PATCH to build
    patch_response = client.patch(
        f"/api/procedures/{proc_id}",
        json={"procedure_type": "build"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["procedure_type"] == "build"

    # GET should also show build
    get_response = client.get(f"/api/procedures/{proc_id}")
    assert get_response.status_code == 200
    assert get_response.json()["procedure_type"] == "build"


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


# --- Output BOM→Kit auto-population tests ---


def _create_assembly_with_bom(client, component_quantities: list[tuple[str, int]]):
    """Helper: create an assembly part with BOM lines. Returns (assembly_id, {name: part_id})."""
    assembly = client.post("/api/parts", json={"name": "Assembly"}).json()
    assembly_id = assembly["id"]
    parts = {}
    for name, qty in component_quantities:
        comp = client.post("/api/parts", json={"name": name}).json()
        parts[name] = comp["id"]
        client.post(
            f"/api/bom/assemblies/{assembly_id}",
            json={"component_id": comp["id"], "quantity": qty},
        )
    return assembly_id, parts


def test_add_output_auto_populates_kit_from_bom(client):
    """Adding an output part with a BOM should auto-populate kit items."""
    assembly_id, parts = _create_assembly_with_bom(
        client, [("Resistor", 4), ("Capacitor", 2)]
    )
    proc = client.post("/api/procedures", json={"name": "Build Proc"}).json()
    proc_id = proc["id"]

    # Add assembly as output (quantity_produced defaults to 1)
    resp = client.post(
        f"/api/procedures/{proc_id}/outputs",
        json={"part_id": assembly_id},
    )
    assert resp.status_code == 201

    # Kit should now contain both BOM components
    kit = client.get(f"/api/procedures/{proc_id}/kit").json()
    kit_by_part = {item["part_id"]: item["quantity_required"] for item in kit}
    assert kit_by_part[parts["Resistor"]] == 4.0
    assert kit_by_part[parts["Capacitor"]] == 2.0


def test_add_output_accumulates_kit_qty_for_existing_items(client):
    """If a BOM component is already in the kit, its quantity should accumulate."""
    assembly_id, parts = _create_assembly_with_bom(client, [("Bolt", 3)])
    proc = client.post("/api/procedures", json={"name": "Accumulate Proc"}).json()
    proc_id = proc["id"]

    # Manually add Bolt to kit with qty 5
    client.post(
        f"/api/procedures/{proc_id}/kit",
        json={"part_id": parts["Bolt"], "quantity_required": 5},
    )

    # Add output → should add 3 more
    client.post(
        f"/api/procedures/{proc_id}/outputs",
        json={"part_id": assembly_id},
    )

    kit = client.get(f"/api/procedures/{proc_id}/kit").json()
    kit_by_part = {item["part_id"]: item["quantity_required"] for item in kit}
    assert kit_by_part[parts["Bolt"]] == 8.0  # 5 + 3


def test_add_output_no_bom_no_kit_changes(client):
    """Adding an output part with no BOM should not create any kit items."""
    part = client.post("/api/parts", json={"name": "Simple Part"}).json()
    proc = client.post("/api/procedures", json={"name": "No BOM Proc"}).json()
    proc_id = proc["id"]

    client.post(
        f"/api/procedures/{proc_id}/outputs",
        json={"part_id": part["id"]},
    )

    kit = client.get(f"/api/procedures/{proc_id}/kit").json()
    assert len(kit) == 0


def test_add_output_multiplies_bom_qty_by_output_qty(client):
    """Kit quantities should be bom_qty * output quantity_produced."""
    assembly_id, parts = _create_assembly_with_bom(client, [("Screw", 2)])
    proc = client.post("/api/procedures", json={"name": "Multiply Proc"}).json()
    proc_id = proc["id"]

    client.post(
        f"/api/procedures/{proc_id}/outputs",
        json={"part_id": assembly_id, "quantity_produced": 3},
    )

    kit = client.get(f"/api/procedures/{proc_id}/kit").json()
    kit_by_part = {item["part_id"]: item["quantity_required"] for item in kit}
    assert kit_by_part[parts["Screw"]] == 6.0  # 2 * 3

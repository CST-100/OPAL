"""Execution API tests."""


def _create_procedure_with_steps(client):
    """Helper to create a procedure with steps and publish it."""
    # Create procedure
    proc_response = client.post(
        "/api/procedures",
        json={"name": "Test Procedure"},
    )
    proc_id = proc_response.json()["id"]

    # Add steps
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 1"})
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 2"})
    client.post(f"/api/procedures/{proc_id}/steps", json={"title": "Step 3"})

    # Publish
    version_response = client.post(f"/api/procedures/{proc_id}/publish")
    version_id = version_response.json()["id"]

    return proc_id, version_id


def test_create_instance(client):
    """Test creating a procedure instance."""
    proc_id, version_id = _create_procedure_with_steps(client)

    response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id, "work_order_number": "WO-001"},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["procedure_id"] == proc_id
    assert data["version_id"] == version_id
    assert data["work_order_number"] == "WO-001"
    assert data["status"] == "pending"
    assert len(data["step_executions"]) == 3


def test_list_instances(client):
    """Test listing instances."""
    proc_id, _ = _create_procedure_with_steps(client)

    client.post("/api/procedure-instances", json={"procedure_id": proc_id})
    client.post("/api/procedure-instances", json={"procedure_id": proc_id})

    response = client.get("/api/procedure-instances")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2


def test_get_instance(client):
    """Test getting a specific instance."""
    proc_id, _ = _create_procedure_with_steps(client)

    create_response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id},
    )
    instance_id = create_response.json()["id"]

    response = client.get(f"/api/procedure-instances/{instance_id}")
    assert response.status_code == 200
    assert response.json()["id"] == instance_id


def test_start_step(client):
    """Test starting a step."""
    proc_id, _ = _create_procedure_with_steps(client)

    instance_response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id},
    )
    instance_id = instance_response.json()["id"]

    # Start step 1
    response = client.post(f"/api/procedure-instances/{instance_id}/steps/1/start")
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert response.json()["started_at"] is not None

    # Instance should now be in_progress
    instance = client.get(f"/api/procedure-instances/{instance_id}").json()
    assert instance["status"] == "in_progress"


def test_complete_step(client):
    """Test completing a step."""
    proc_id, _ = _create_procedure_with_steps(client)

    instance_response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id},
    )
    instance_id = instance_response.json()["id"]

    # Start and complete step 1
    client.post(f"/api/procedure-instances/{instance_id}/steps/1/start")
    response = client.post(
        f"/api/procedure-instances/{instance_id}/steps/1/complete",
        json={"data_captured": {"notes": "Done"}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["data_captured"] == {"notes": "Done"}


def test_complete_all_steps_completes_instance(client):
    """Test that completing all steps completes the instance."""
    proc_id, _ = _create_procedure_with_steps(client)

    instance_response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id},
    )
    instance_id = instance_response.json()["id"]

    # Complete all steps
    for step in [1, 2, 3]:
        client.post(f"/api/procedure-instances/{instance_id}/steps/{step}/start")
        client.post(f"/api/procedure-instances/{instance_id}/steps/{step}/complete", json={})

    # Instance should be completed
    instance = client.get(f"/api/procedure-instances/{instance_id}").json()
    assert instance["status"] == "completed"
    assert instance["completed_at"] is not None


def test_log_non_conformance(client):
    """Test logging a non-conformance creates an issue."""
    proc_id, _ = _create_procedure_with_steps(client)

    instance_response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id},
    )
    instance_id = instance_response.json()["id"]

    # Start step and log NC
    client.post(f"/api/procedure-instances/{instance_id}/steps/1/start")
    response = client.post(
        f"/api/procedure-instances/{instance_id}/steps/1/nc",
        json={
            "title": "Test NC",
            "description": "Something went wrong",
            "priority": "high",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Test NC"
    assert data["issue_type"] == "non_conformance"
    assert data["priority"] == "high"
    assert data["procedure_instance_id"] == instance_id


def test_abort_instance(client):
    """Test aborting an instance."""
    proc_id, _ = _create_procedure_with_steps(client)

    instance_response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id},
    )
    instance_id = instance_response.json()["id"]

    # Start instance
    client.post(f"/api/procedure-instances/{instance_id}/steps/1/start")

    # Abort
    response = client.patch(
        f"/api/procedure-instances/{instance_id}",
        json={"status": "aborted"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "aborted"
    assert response.json()["completed_at"] is not None


def test_cannot_start_completed_step(client):
    """Test cannot start a step that's already completed."""
    proc_id, _ = _create_procedure_with_steps(client)

    instance_response = client.post(
        "/api/procedure-instances",
        json={"procedure_id": proc_id},
    )
    instance_id = instance_response.json()["id"]

    # Start and complete step 1
    client.post(f"/api/procedure-instances/{instance_id}/steps/1/start")
    client.post(f"/api/procedure-instances/{instance_id}/steps/1/complete", json={})

    # Try to start again
    response = client.post(f"/api/procedure-instances/{instance_id}/steps/1/start")
    assert response.status_code == 400

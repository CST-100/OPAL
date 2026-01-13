"""Datasets API tests."""


def test_create_dataset(client):
    """Test creating a new dataset."""
    response = client.post(
        "/api/datasets",
        json={
            "name": "Temperature Readings",
            "description": "Daily temperature measurements",
            "schema": {
                "fields": [
                    {"name": "temperature", "type": "number", "unit": "C"},
                    {"name": "humidity", "type": "number", "unit": "%"},
                ]
            },
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Temperature Readings"
    assert data["schema"]["fields"][0]["name"] == "temperature"
    assert data["point_count"] == 0


def test_list_datasets(client):
    """Test listing datasets."""
    client.post("/api/datasets", json={"name": "Dataset A", "schema": {"fields": []}})
    client.post("/api/datasets", json={"name": "Dataset B", "schema": {"fields": []}})

    response = client.get("/api/datasets")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 2


def test_get_dataset(client):
    """Test getting a specific dataset."""
    create_response = client.post(
        "/api/datasets",
        json={"name": "Specific Dataset", "schema": {"fields": [{"name": "value", "type": "number"}]}},
    )
    dataset_id = create_response.json()["id"]

    response = client.get(f"/api/datasets/{dataset_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Specific Dataset"


def test_update_dataset(client):
    """Test updating a dataset."""
    create_response = client.post(
        "/api/datasets",
        json={"name": "Original Name", "schema": {"fields": []}},
    )
    dataset_id = create_response.json()["id"]

    response = client.patch(
        f"/api/datasets/{dataset_id}",
        json={"name": "Updated Name", "description": "Added description"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Added description"


def test_delete_dataset(client):
    """Test soft deleting a dataset."""
    create_response = client.post(
        "/api/datasets",
        json={"name": "To Be Deleted", "schema": {"fields": []}},
    )
    dataset_id = create_response.json()["id"]

    response = client.delete(f"/api/datasets/{dataset_id}")
    assert response.status_code == 204

    # Should not be found
    get_response = client.get(f"/api/datasets/{dataset_id}")
    assert get_response.status_code == 404


def test_add_data_point(client):
    """Test adding a data point to a dataset."""
    # Create dataset
    dataset = client.post(
        "/api/datasets",
        json={
            "name": "Test Dataset",
            "schema": {"fields": [{"name": "value", "type": "number"}]},
        },
    ).json()

    # Add data point
    response = client.post(
        f"/api/datasets/{dataset['id']}/points",
        json={"values": {"value": 42.5}},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["values"]["value"] == 42.5
    assert data["dataset_id"] == dataset["id"]


def test_list_data_points(client):
    """Test listing data points."""
    # Create dataset
    dataset = client.post(
        "/api/datasets",
        json={
            "name": "Test Dataset",
            "schema": {"fields": [{"name": "value", "type": "number"}]},
        },
    ).json()

    # Add multiple points
    client.post(f"/api/datasets/{dataset['id']}/points", json={"values": {"value": 1}})
    client.post(f"/api/datasets/{dataset['id']}/points", json={"values": {"value": 2}})
    client.post(f"/api/datasets/{dataset['id']}/points", json={"values": {"value": 3}})

    response = client.get(f"/api/datasets/{dataset['id']}/points")
    assert response.status_code == 200

    points = response.json()
    assert len(points) == 3


def test_delete_data_point(client):
    """Test deleting a data point."""
    # Create dataset
    dataset = client.post(
        "/api/datasets",
        json={
            "name": "Test Dataset",
            "schema": {"fields": [{"name": "value", "type": "number"}]},
        },
    ).json()

    # Add data point
    point = client.post(
        f"/api/datasets/{dataset['id']}/points",
        json={"values": {"value": 42}},
    ).json()

    # Delete it
    response = client.delete(f"/api/datasets/{dataset['id']}/points/{point['id']}")
    assert response.status_code == 204

    # Should be gone
    points = client.get(f"/api/datasets/{dataset['id']}/points").json()
    assert len(points) == 0


def test_get_chart_data(client):
    """Test getting chart-ready data."""
    # Create dataset
    dataset = client.post(
        "/api/datasets",
        json={
            "name": "Chart Test",
            "schema": {"fields": [{"name": "temperature", "type": "number"}]},
        },
    ).json()

    # Add data points
    client.post(f"/api/datasets/{dataset['id']}/points", json={"values": {"temperature": 20}})
    client.post(f"/api/datasets/{dataset['id']}/points", json={"values": {"temperature": 22}})
    client.post(f"/api/datasets/{dataset['id']}/points", json={"values": {"temperature": 21}})

    response = client.get(f"/api/datasets/{dataset['id']}/chart?field=temperature")
    assert response.status_code == 200

    data = response.json()
    assert "labels" in data
    assert "datasets" in data
    assert len(data["labels"]) == 3
    assert data["datasets"][0]["label"] == "temperature"
    assert data["datasets"][0]["data"] == [20.0, 22.0, 21.0]


def test_dataset_with_procedure_link(client):
    """Test creating a dataset linked to a procedure."""
    # Create procedure
    proc_response = client.post("/api/procedures", json={"name": "Test Proc"})
    proc_id = proc_response.json()["id"]

    # Create dataset linked to procedure
    response = client.post(
        "/api/datasets",
        json={
            "name": "Procedure Dataset",
            "procedure_id": proc_id,
            "schema": {"fields": []},
        },
    )
    assert response.status_code == 201
    assert response.json()["procedure_id"] == proc_id


def test_filter_datasets_by_procedure(client):
    """Test filtering datasets by procedure."""
    # Create procedure
    proc = client.post("/api/procedures", json={"name": "Filter Test"}).json()

    # Create datasets
    client.post("/api/datasets", json={"name": "Linked", "procedure_id": proc["id"], "schema": {"fields": []}})
    client.post("/api/datasets", json={"name": "Unlinked", "schema": {"fields": []}})

    response = client.get(f"/api/datasets?procedure_id={proc['id']}")
    assert response.status_code == 200

    data = response.json()
    assert all(d["procedure_id"] == proc["id"] for d in data["items"])

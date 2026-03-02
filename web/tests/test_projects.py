"""Tests for project CRUD endpoints."""


# ── List projects ────────────────────────────────────────────────────────────


def test_list_projects_empty(test_client):
    """GET /api/projects returns empty list initially"""
    resp = test_client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_projects(test_client, project_store):
    """GET /api/projects returns created projects"""
    project_store.create_project(name="Project A", workdir="/tmp")
    project_store.create_project(name="Project B", workdir="/tmp")
    resp = test_client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = [p["name"] for p in data]
    assert "Project A" in names
    assert "Project B" in names


# ── Create project ───────────────────────────────────────────────────────────


def test_create_project(test_client, tmp_path):
    """POST /api/projects creates project and inits .cody/"""
    resp = test_client.post("/api/projects", json={
        "name": "My Project",
        "description": "A test project",
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["description"] == "A test project"
    assert data["workdir"] == str(tmp_path)
    assert data["session_id"] is not None  # Session created via SessionStore
    assert len(data["id"]) == 12
    # .cody/ directory should be initialized
    assert (tmp_path / ".cody").is_dir()
    assert (tmp_path / ".cody" / "config.json").exists()


def test_create_project_bad_workdir(test_client):
    """POST /api/projects with nonexistent workdir returns 404"""
    resp = test_client.post("/api/projects", json={
        "name": "Bad",
        "workdir": "/nonexistent/path/xyz",
    })
    assert resp.status_code == 404


def test_create_project_missing_name(test_client):
    """POST /api/projects without name fails validation"""
    resp = test_client.post("/api/projects", json={
        "workdir": "/tmp",
    })
    assert resp.status_code == 422


# ── Get project ──────────────────────────────────────────────────────────────


def test_get_project(test_client, project_store):
    """GET /api/projects/:id returns project"""
    p = project_store.create_project(name="Test", workdir="/tmp")
    resp = test_client.get(f"/api/projects/{p.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test"


def test_get_project_not_found(test_client):
    """GET /api/projects/:id returns 404 for nonexistent"""
    resp = test_client.get("/api/projects/nonexistent")
    assert resp.status_code == 404


# ── Update project ───────────────────────────────────────────────────────────


def test_update_project(test_client, project_store):
    """PUT /api/projects/:id updates name and description"""
    p = project_store.create_project(name="Old Name", workdir="/tmp")
    resp = test_client.put(f"/api/projects/{p.id}", json={
        "name": "New Name",
        "description": "Updated",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["description"] == "Updated"


def test_update_project_partial(test_client, project_store):
    """PUT /api/projects/:id with partial data only updates provided fields"""
    p = project_store.create_project(
        name="Keep", description="Original", workdir="/tmp"
    )
    resp = test_client.put(f"/api/projects/{p.id}", json={
        "description": "Changed",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Keep"
    assert data["description"] == "Changed"


def test_update_project_not_found(test_client):
    """PUT /api/projects/:id returns 404 for nonexistent"""
    resp = test_client.put("/api/projects/nonexistent", json={"name": "X"})
    assert resp.status_code == 404


# ── Delete project ───────────────────────────────────────────────────────────


def test_delete_project(test_client, project_store):
    """DELETE /api/projects/:id deletes the project"""
    p = project_store.create_project(name="To Delete", workdir="/tmp")
    resp = test_client.delete(f"/api/projects/{p.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert project_store.get_project(p.id) is None


def test_delete_project_not_found(test_client):
    """DELETE /api/projects/:id returns 404 for nonexistent"""
    resp = test_client.delete("/api/projects/nonexistent")
    assert resp.status_code == 404

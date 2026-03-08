"""Tests for task CRUD endpoints."""


# ── List tasks ──────────────────────────────────────────────────────────────


def test_list_tasks_project_not_found(test_client):
    """GET /api/projects/:id/tasks returns 404 for nonexistent project"""
    resp = test_client.get("/api/projects/nonexistent/tasks")
    assert resp.status_code == 404


def test_list_tasks_empty(test_client, project_store):
    """GET /api/projects/:id/tasks returns empty list initially"""
    p = project_store.create_project(name="Test", workdir="/tmp")
    resp = test_client.get(f"/api/projects/{p.id}/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_tasks(test_client, project_store):
    """GET /api/projects/:id/tasks returns tasks"""
    p = project_store.create_project(name="Test", workdir="/tmp")
    project_store.create_task(project_id=p.id, name="Task A", branch_name="feat-a")
    project_store.create_task(project_id=p.id, name="Task B", branch_name="feat-b")
    resp = test_client.get(f"/api/projects/{p.id}/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = [t["name"] for t in data]
    assert "Task A" in names
    assert "Task B" in names


# ── Get task ────────────────────────────────────────────────────────────────


def test_get_task(test_client, project_store):
    """GET /api/tasks/:id returns task"""
    p = project_store.create_project(name="Test", workdir="/tmp")
    t = project_store.create_task(project_id=p.id, name="My Task", branch_name="feat-x")
    resp = test_client.get(f"/api/tasks/{t.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "My Task"
    assert data["branch_name"] == "feat-x"
    assert data["project_id"] == p.id


def test_get_task_not_found(test_client):
    """GET /api/tasks/:id returns 404 for nonexistent"""
    resp = test_client.get("/api/tasks/nonexistent")
    assert resp.status_code == 404


# ── Update task ─────────────────────────────────────────────────────────────


def test_update_task(test_client, project_store):
    """PUT /api/tasks/:id updates task fields"""
    p = project_store.create_project(name="Test", workdir="/tmp")
    t = project_store.create_task(project_id=p.id, name="Old", branch_name="feat-old")
    resp = test_client.put(f"/api/tasks/{t.id}", json={
        "name": "New Name",
        "status": "in_progress",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["status"] == "in_progress"


def test_update_task_not_found(test_client):
    """PUT /api/tasks/:id returns 404 for nonexistent"""
    resp = test_client.put("/api/tasks/nonexistent", json={"name": "X"})
    assert resp.status_code == 404


# ── Delete task ─────────────────────────────────────────────────────────────


def test_delete_task(test_client, project_store):
    """DELETE /api/tasks/:id deletes the task"""
    p = project_store.create_project(name="Test", workdir="/tmp")
    t = project_store.create_task(project_id=p.id, name="To Delete", branch_name="feat-del")
    resp = test_client.delete(f"/api/tasks/{t.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert project_store.get_task(t.id) is None


def test_delete_task_not_found(test_client):
    """DELETE /api/tasks/:id returns 404 for nonexistent"""
    resp = test_client.delete("/api/tasks/nonexistent")
    assert resp.status_code == 404

"""Tests for /skills endpoints — migrated from test_server.py."""

from fastapi.testclient import TestClient

from web.backend.app import app


def test_skills_list():
    """GET /skills returns a list."""
    client = TestClient(app)
    resp = client.get("/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" in data
    assert isinstance(data["skills"], list)


def test_skills_list_contains_builtin():
    """Built-in git skill should appear."""
    client = TestClient(app)
    resp = client.get("/skills")
    names = [s["name"] for s in resp.json()["skills"]]
    assert "git" in names


def test_skills_list_has_expected_fields():
    """Each skill should have name, description, enabled, source."""
    client = TestClient(app)
    resp = client.get("/skills")
    for skill in resp.json()["skills"]:
        assert "name" in skill
        assert "enabled" in skill
        assert "source" in skill


def test_skill_detail():
    """GET /skills/git returns skill documentation."""
    client = TestClient(app)
    resp = client.get("/skills/git")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "git"
    assert "documentation" in data
    assert len(data["documentation"]) > 0


def test_skill_not_found():
    """GET /skills/nonexistent returns 404."""
    client = TestClient(app)
    resp = client.get("/skills/nonexistent_skill_xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "SKILL_NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()

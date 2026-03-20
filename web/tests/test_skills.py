"""Tests for /skills endpoints — migrated from test_server.py."""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from web.backend.app import app


def _setup_skill_dir():
    """Create a temp dir with a project-level skill for testing."""
    tmp = tempfile.mkdtemp()
    skill_dir = Path(tmp) / ".cody" / "skills" / "git"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: git\ndescription: Git operations for version control workflows.\n"
        "metadata:\n  author: cody\n  version: \"1.0\"\n---\n\n"
        "# Git\n\nGit skill instructions."
    )
    return tmp


def test_skills_list():
    """GET /skills returns a list."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.get("/skills", params={"workdir": workdir})
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" in data
    assert isinstance(data["skills"], list)


def test_skills_list_contains_project_skill():
    """Project-level git skill should appear."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.get("/skills", params={"workdir": workdir})
    names = [s["name"] for s in resp.json()["skills"]]
    assert "git" in names


def test_skills_list_has_expected_fields():
    """Each skill should have name, description, enabled, source."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.get("/skills", params={"workdir": workdir})
    for skill in resp.json()["skills"]:
        assert "name" in skill
        assert "enabled" in skill
        assert "source" in skill


def test_skill_detail():
    """GET /skills/git returns skill documentation."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.get("/skills/git", params={"workdir": workdir})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "git"
    assert "documentation" in data
    assert len(data["documentation"]) > 0


def test_skill_not_found():
    """GET /skills/nonexistent returns 404."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.get("/skills/nonexistent_skill_xyz", params={"workdir": workdir})
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "SKILL_NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


# ── Enable / Disable ─────────────────────────────────────────────────────────


def test_enable_skill():
    """POST /skills/git/enable enables the skill."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.post("/skills/git/enable", params={"workdir": workdir})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "git"
    assert data["enabled"] is True


def test_disable_skill():
    """POST /skills/git/disable disables the skill."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.post("/skills/git/disable", params={"workdir": workdir})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "git"
    assert data["enabled"] is False


def test_enable_skill_not_found():
    """POST /skills/nonexistent/enable returns 404."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.post("/skills/nonexistent_skill_xyz/enable", params={"workdir": workdir})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SKILL_NOT_FOUND"


def test_disable_skill_not_found():
    """POST /skills/nonexistent/disable returns 404."""
    workdir = _setup_skill_dir()
    client = TestClient(app)
    resp = client.post("/skills/nonexistent_skill_xyz/disable", params={"workdir": workdir})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SKILL_NOT_FOUND"

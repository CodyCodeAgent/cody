"""Tests for directory browsing endpoint."""

from pathlib import Path


def test_list_directories(test_client, tmp_path):
    """GET /api/directories lists entries in a directory"""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.txt").write_text("hello")

    resp = test_client.get("/api/directories", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == str(tmp_path)
    names = [e["name"] for e in data["entries"]]
    assert "subdir" in names
    assert "file.txt" in names
    entry_map = {e["name"]: e["is_dir"] for e in data["entries"]}
    assert entry_map["subdir"] is True
    assert entry_map["file.txt"] is False


def test_list_directories_hides_dotfiles(test_client, tmp_path):
    """GET /api/directories skips dotfiles/dotdirs"""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()

    resp = test_client.get("/api/directories", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()["entries"]]
    assert "visible" in names
    assert ".hidden" not in names


def test_list_directories_default_path(test_client):
    """GET /api/directories without path defaults to home"""
    resp = test_client.get("/api/directories")
    assert resp.status_code == 200
    assert resp.json()["path"] == str(Path.home())


def test_list_directories_not_found(test_client):
    """GET /api/directories with nonexistent path returns 404"""
    resp = test_client.get(
        "/api/directories", params={"path": "/nonexistent/path/xyz"}
    )
    assert resp.status_code == 404

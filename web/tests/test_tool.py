"""Tests for /tool endpoint — migrated from test_server.py."""

from fastapi.testclient import TestClient

from web.backend.app import app


def test_tool_read_file(tmp_path):
    """Call read_file tool through /tool endpoint."""
    (tmp_path / "hello.txt").write_text("hello from tool test")

    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "read_file",
        "params": {"path": "hello.txt"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "hello from tool test" in data["result"]


def test_tool_write_file(tmp_path):
    """Call write_file tool through /tool endpoint."""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "write_file",
        "params": {"path": "out.txt", "content": "written via tool endpoint"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 200
    assert "Written" in resp.json()["result"]
    assert (tmp_path / "out.txt").read_text() == "written via tool endpoint"


def test_tool_list_directory(tmp_path):
    """Call list_directory tool through /tool endpoint."""
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")

    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "list_directory",
        "params": {"path": "."},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert "a.py" in result
    assert "b.txt" in result


def test_tool_not_found():
    """Request a tool that doesn't exist."""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "nonexistent_tool",
        "params": {},
    })
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "TOOL_NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


def test_tool_missing_params():
    """POST /tool without params field should fail validation."""
    client = TestClient(app)
    resp = client.post("/tool", json={"tool": "read_file"})
    assert resp.status_code == 422


def test_tool_path_traversal(tmp_path):
    """write_file should block path traversal."""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "write_file",
        "params": {"path": "../../../evil.txt", "content": "bad"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 403
    assert "outside" in resp.json()["error"]["message"].lower()

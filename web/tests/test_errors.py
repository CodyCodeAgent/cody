"""Tests for structured error responses via HTTP endpoints."""

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from web.backend.app import app


def _mock_ready_config():
    """Return a mock Config that passes is_ready() check."""
    cfg = MagicMock()
    cfg.is_ready.return_value = True
    cfg.model = "test-model"
    cfg.model_base_url = "https://test.example.com"
    cfg.model_api_key = "sk-test"
    cfg.enable_thinking = False
    cfg.thinking_budget = None
    cfg.extra_roots = None
    return cfg


def test_tool_not_found_structured():
    client = TestClient(app)
    resp = client.post("/tool", json={"tool": "nope", "params": {}})
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "TOOL_NOT_FOUND"
    assert "nope" in data["error"]["message"]


def test_skill_not_found_structured():
    client = TestClient(app)
    resp = client.get("/skills/nonexistent_xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "SKILL_NOT_FOUND"


def test_session_not_found_structured(session_store, test_client):
    resp = test_client.get("/sessions/nonexistent_id")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "SESSION_NOT_FOUND"


def test_tool_error_includes_details(tmp_path):
    """write_file should return 403 for path traversal"""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "write_file",
        "params": {"path": "../../../evil.txt", "content": "bad"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "PERMISSION_DENIED"


def test_run_error_structured():
    with patch("web.backend.routes.run.AgentRunner") as MockRunner, \
         patch("web.backend.routes.run.config_from_run_request", return_value=_mock_ready_config()):
        instance = MockRunner.return_value
        instance.run = AsyncMock(side_effect=RuntimeError("model down"))
        client = TestClient(app)
        resp = client.post("/run", json={"prompt": "test"})
    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == "SERVER_ERROR"
    assert "model down" in data["error"]["message"]


def test_stream_error_structured(test_client):
    async def failing_stream(prompt, message_history=None, **kwargs):
        raise RuntimeError("stream broke")
        yield  # make it a generator

    with patch("web.backend.routes.run.AgentRunner") as MockRunner, \
         patch("web.backend.routes.run.config_from_run_request", return_value=_mock_ready_config()):
        instance = MockRunner.return_value
        instance.run_stream = failing_stream
        resp = test_client.post("/run/stream", json={"prompt": "test"})

    # SSE streams still return 200 but error in body
    assert resp.status_code == 200
    assert '"code": "SERVER_ERROR"' in resp.text
    assert "stream broke" in resp.text

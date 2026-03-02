"""Tests for structured error responses"""

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from cody.core.errors import CodyAPIError, ErrorCode, ErrorDetail
from web.backend.app import app


# ── ErrorDetail model ───────────────────────────────────────────────────────


def test_error_detail_model():
    detail = ErrorDetail(code=ErrorCode.TOOL_NOT_FOUND, message="not found")
    assert detail.code == ErrorCode.TOOL_NOT_FOUND
    assert detail.message == "not found"
    assert detail.details is None


def test_error_detail_with_extra():
    detail = ErrorDetail(
        code=ErrorCode.TOOL_ERROR,
        message="failed",
        details={"tool": "grep"},
    )
    assert detail.details["tool"] == "grep"


# ── CodyAPIError ────────────────────────────────────────────────────────────


def test_cody_api_error_to_detail():
    err = CodyAPIError(
        code=ErrorCode.SESSION_NOT_FOUND,
        message="Session not found: abc",
        status_code=404,
    )
    body = err.to_detail()
    assert body["error"]["code"] == "SESSION_NOT_FOUND"
    assert body["error"]["message"] == "Session not found: abc"


def test_cody_api_error_with_details():
    err = CodyAPIError(
        code=ErrorCode.TOOL_ERROR,
        message="failed",
        status_code=500,
        details={"tool": "grep", "reason": "timeout"},
    )
    body = err.to_detail()
    assert body["error"]["details"]["tool"] == "grep"
    assert body["error"]["details"]["reason"] == "timeout"


# ── Server structured error format ──────────────────────────────────────────


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


def test_session_not_found_structured(isolated_store, test_client):
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
    with patch("web.backend.routes.run.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(side_effect=RuntimeError("model down"))
        client = TestClient(app)
        resp = client.post("/run", json={"prompt": "test"})
    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == "SERVER_ERROR"
    assert "model down" in data["error"]["message"]


def test_stream_error_structured(test_client):
    async def failing_stream(prompt, message_history=None):
        raise RuntimeError("stream broke")
        yield  # make it a generator

    with patch("web.backend.routes.run.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = failing_stream
        resp = test_client.post("/run/stream", json={"prompt": "test"})

    # SSE streams still return 200 but error in body
    assert resp.status_code == 200
    assert '"code": "SERVER_ERROR"' in resp.text
    assert "stream broke" in resp.text


# ── ErrorCode enum ──────────────────────────────────────────────────────────


def test_error_code_values():
    assert ErrorCode.INVALID_PARAMS == "INVALID_PARAMS"
    assert ErrorCode.TOOL_NOT_FOUND == "TOOL_NOT_FOUND"
    assert ErrorCode.SESSION_NOT_FOUND == "SESSION_NOT_FOUND"
    assert ErrorCode.SERVER_ERROR == "SERVER_ERROR"
    assert ErrorCode.MCP_ERROR == "MCP_ERROR"
    assert ErrorCode.AGENT_ERROR == "AGENT_ERROR"
    assert ErrorCode.AGENT_NOT_FOUND == "AGENT_NOT_FOUND"
    assert ErrorCode.AGENT_LIMIT_REACHED == "AGENT_LIMIT_REACHED"

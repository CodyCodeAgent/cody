"""Tests for core error types (no web/FastAPI dependency)."""

from cody.core.errors import CodyAPIError, ErrorCode, ErrorDetail


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

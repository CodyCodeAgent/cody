"""Tests for HTTP middleware (auth, rate limit, audit)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web.backend.app import app


@pytest.fixture
def client():
    """Bare test client without dependency overrides."""
    return TestClient(app)


# ── Auth middleware ──────────────────────────────────────────────────────────


def test_auth_public_paths(client):
    """Public paths (/health, /api/health) should not require auth."""
    resp = client.get("/health")
    assert resp.status_code == 200

    resp = client.get("/api/health")
    assert resp.status_code == 200


@patch("web.backend.middleware.get_auth_manager")
def test_auth_missing_token(mock_get_auth, client):
    """Missing Authorization header returns 401 when auth is configured."""
    mock_mgr = MagicMock()
    mock_mgr.is_configured = True
    mock_get_auth.return_value = mock_mgr

    resp = client.get("/sessions")
    assert resp.status_code == 401
    assert "AUTH_FAILED" in resp.text


@patch("web.backend.middleware.get_auth_manager")
def test_auth_invalid_token(mock_get_auth, client):
    """Invalid token returns 401."""
    from cody.core.auth import AuthError
    mock_mgr = MagicMock()
    mock_mgr.is_configured = True
    mock_mgr.validate.side_effect = AuthError("Invalid token")
    mock_get_auth.return_value = mock_mgr

    resp = client.get("/sessions", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401


@patch("web.backend.middleware.get_auth_manager")
def test_auth_valid_token(mock_get_auth, client):
    """Valid token passes through to the endpoint."""
    mock_mgr = MagicMock()
    mock_mgr.is_configured = True
    mock_mgr.validate.return_value = None
    mock_get_auth.return_value = mock_mgr

    resp = client.get("/sessions", headers={"Authorization": "Bearer valid-token"})
    # Should reach the endpoint (200) rather than being blocked (401)
    assert resp.status_code == 200


# ── Rate limit middleware ────────────────────────────────────────────────────


@patch("web.backend.middleware.get_rate_limiter")
@patch("web.backend.middleware.get_auth_manager")
def test_rate_limit_exceeded(mock_get_auth, mock_get_limiter, client):
    """Rate limited requests return 429 with Retry-After header."""
    mock_get_auth.return_value = None  # No auth

    mock_result = MagicMock()
    mock_result.allowed = False
    mock_result.retry_after = 30
    mock_result.limit = 100

    mock_limiter = MagicMock()
    mock_limiter.hit.return_value = mock_result
    mock_get_limiter.return_value = mock_limiter

    resp = client.get("/sessions")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.headers["Retry-After"] == "30"


@patch("web.backend.middleware.get_rate_limiter")
@patch("web.backend.middleware.get_auth_manager")
def test_rate_limit_headers(mock_get_auth, mock_get_limiter, client):
    """Normal requests include X-RateLimit-* headers."""
    mock_get_auth.return_value = None  # No auth

    mock_result = MagicMock()
    mock_result.allowed = True
    mock_result.limit = 100
    mock_result.remaining = 99

    mock_limiter = MagicMock()
    mock_limiter.hit.return_value = mock_result
    mock_get_limiter.return_value = mock_limiter

    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" in resp.headers
    assert resp.headers["X-RateLimit-Limit"] == "100"
    assert resp.headers["X-RateLimit-Remaining"] == "99"


# ── Audit middleware ─────────────────────────────────────────────────────────


@patch("web.backend.middleware.get_audit_logger")
@patch("web.backend.middleware.get_auth_manager")
def test_audit_logs_request(mock_get_auth, mock_get_audit, client):
    """Audit logger is called for API requests (non-public)."""
    mock_get_auth.return_value = None  # No auth
    mock_audit = MagicMock()
    mock_get_audit.return_value = mock_audit

    client.get("/sessions")
    mock_audit.log.assert_called()

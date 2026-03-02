"""Tests for health endpoint."""

from unittest.mock import AsyncMock

from web.backend.app import app, get_cody_client


def test_health_with_core_connected(test_client):
    """GET /api/health reports core connected when client works"""
    resp = test_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["core_server"] == "connected"
    assert data["core_version"] == "1.3.0"


def test_health_with_core_unavailable(test_client):
    """GET /api/health reports core unavailable when client fails"""
    failing_client = AsyncMock()
    failing_client.health = AsyncMock(side_effect=ConnectionError("refused"))
    app.dependency_overrides[get_cody_client] = lambda: failing_client

    resp = test_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["core_server"] == "unavailable"
    assert data["core_version"] is None

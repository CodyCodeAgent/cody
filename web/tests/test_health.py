"""Tests for health endpoints."""


def test_api_health(test_client):
    """GET /api/health returns status and version."""
    resp = test_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_rpc_health(test_client):
    """GET /health returns status and version (RPC endpoint)."""
    resp = test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data

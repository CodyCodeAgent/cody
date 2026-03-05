"""Tests for /agent endpoints — spawn, status, kill."""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from cody.core.sub_agent import SubAgentResult, AgentStatus
from web.backend.app import app


def _mock_result(agent_id="agent-123", status=AgentStatus.COMPLETED,
                 output="done", error=None):
    """Create a SubAgentResult for testing."""
    return SubAgentResult(
        agent_id=agent_id,
        status=status,
        output=output,
        error=error,
        created_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


# ── POST /agent/spawn ────────────────────────────────────────────────────────


def test_spawn_agent():
    """POST /agent/spawn creates a sub-agent and returns its ID."""
    result = _mock_result()

    mock_manager = MagicMock()
    mock_manager.spawn = AsyncMock(return_value="agent-123")
    mock_manager.get_status.return_value = result

    with patch("web.backend.routes.agents.get_sub_agent_manager",
               new_callable=AsyncMock, return_value=mock_manager):
        client = TestClient(app)
        resp = client.post("/agent/spawn", json={
            "task": "write unit tests",
            "type": "test",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "agent-123"
    assert "status" in data


def test_spawn_agent_limit_reached():
    """POST /agent/spawn returns 429 when max agents exceeded."""
    mock_manager = MagicMock()
    mock_manager.spawn = AsyncMock(side_effect=RuntimeError("Max agents reached"))

    with patch("web.backend.routes.agents.get_sub_agent_manager",
               new_callable=AsyncMock, return_value=mock_manager):
        client = TestClient(app)
        resp = client.post("/agent/spawn", json={"task": "test"})

    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "AGENT_LIMIT_REACHED"


def test_spawn_agent_missing_task():
    """POST /agent/spawn without task fails validation."""
    client = TestClient(app)
    resp = client.post("/agent/spawn", json={})
    assert resp.status_code == 422


# ── GET /agent/{agent_id} ────────────────────────────────────────────────────


def test_get_agent_status():
    """GET /agent/{id} returns agent status and output."""
    result = _mock_result(output="all tests passed")

    mock_manager = MagicMock()
    mock_manager.get_status.return_value = result

    with patch("web.backend.routes.agents.get_sub_agent_manager",
               new_callable=AsyncMock, return_value=mock_manager):
        client = TestClient(app)
        resp = client.get("/agent/agent-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "agent-123"
    assert data["output"] == "all tests passed"
    assert data["status"] == "completed"


def test_get_agent_not_found():
    """GET /agent/{id} returns 404 for unknown agent."""
    mock_manager = MagicMock()
    mock_manager.get_status.return_value = None

    with patch("web.backend.routes.agents.get_sub_agent_manager",
               new_callable=AsyncMock, return_value=mock_manager):
        client = TestClient(app)
        resp = client.get("/agent/nonexistent")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


# ── DELETE /agent/{agent_id} ─────────────────────────────────────────────────


def test_kill_agent():
    """DELETE /agent/{id} kills a running agent."""
    result = _mock_result(status=AgentStatus.RUNNING)

    mock_manager = MagicMock()
    mock_manager.get_status.return_value = result
    mock_manager.kill = AsyncMock(return_value=True)

    with patch("web.backend.routes.agents.get_sub_agent_manager",
               new_callable=AsyncMock, return_value=mock_manager):
        client = TestClient(app)
        resp = client.delete("/agent/agent-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["killed"] is True
    assert data["status"] == "killed"


def test_kill_agent_not_found():
    """DELETE /agent/{id} returns 404 for unknown agent."""
    mock_manager = MagicMock()
    mock_manager.get_status.return_value = None

    with patch("web.backend.routes.agents.get_sub_agent_manager",
               new_callable=AsyncMock, return_value=mock_manager):
        client = TestClient(app)
        resp = client.delete("/agent/nonexistent")

    assert resp.status_code == 404

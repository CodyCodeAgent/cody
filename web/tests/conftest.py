"""Shared fixtures for web backend tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from web.backend.app import app, get_project_store, get_cody_client
from web.backend.db import ProjectStore


@pytest.fixture
def project_store(tmp_path):
    """A ProjectStore backed by a temp database."""
    return ProjectStore(db_path=tmp_path / "test_web.db")


@pytest.fixture
def mock_cody_client():
    """Mock AsyncCodyClient for testing without core server."""
    client = AsyncMock()
    client.health = AsyncMock(return_value={"status": "ok", "version": "1.3.0"})

    mock_session = MagicMock()
    mock_session.id = "session_abc123"
    mock_session.title = "New session"
    client.create_session = AsyncMock(return_value=mock_session)
    client.delete_session = AsyncMock()

    return client


@pytest.fixture
def test_client(project_store, mock_cody_client):
    """FastAPI TestClient with injected test dependencies."""
    app.dependency_overrides[get_project_store] = lambda: project_store
    app.dependency_overrides[get_cody_client] = lambda: mock_cody_client
    yield TestClient(app)
    app.dependency_overrides.clear()

"""Shared fixtures for web backend tests."""

import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from cody.core.session import SessionStore
from web.backend.app import app, get_project_store
from web.backend.db import ProjectStore


@pytest.fixture
def project_store(tmp_path):
    """A ProjectStore backed by a temp database."""
    return ProjectStore(db_path=tmp_path / "test_web.db")


@pytest.fixture
def session_store(tmp_path):
    """A SessionStore backed by a temp database."""
    return SessionStore(db_path=tmp_path / "test_sessions.db")


@pytest.fixture
def test_client(project_store, session_store):
    """FastAPI TestClient with injected test dependencies."""
    app.dependency_overrides[get_project_store] = lambda: project_store
    with patch("web.backend.routes.projects.get_session_store", return_value=session_store):
        yield TestClient(app)
    app.dependency_overrides.clear()

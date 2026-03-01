"""Shared pytest fixtures for the test suite."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from cody.core.session import SessionStore
from cody.server import app


@pytest.fixture
def isolated_store(tmp_path):
    """A SessionStore backed by a temp DB, patched into the server."""
    store = SessionStore(db_path=tmp_path / "test.db")
    with patch("cody.server._get_session_store", return_value=store):
        yield store


@pytest.fixture
def test_client():
    """A plain FastAPI TestClient for the Cody server app."""
    return TestClient(app)

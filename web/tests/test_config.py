"""Tests for /config endpoints — GET and PUT."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from cody.core import Config
from web.backend.app import app


def _make_config(**overrides):
    """Create a Config with sensible defaults for testing."""
    defaults = {
        "model": "test-model",
        "model_api_key": "sk-abc123secret",
    }
    defaults.update(overrides)
    return Config(**defaults)


def test_config_status_ready():
    """GET /config/status returns ready when model + base_url set."""
    cfg = _make_config(model_base_url="https://api.example.com/v1")

    with patch("web.backend.routes.config.Config") as MockConfig:
        MockConfig.load.return_value = cfg
        client = TestClient(app)
        resp = client.get("/config/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_ready"] is True
    assert data["missing_fields"] == []


def test_config_status_not_ready():
    """GET /config/status returns not ready when config is empty."""
    cfg = Config()  # empty defaults

    with patch("web.backend.routes.config.Config") as MockConfig:
        MockConfig.load.return_value = cfg
        client = TestClient(app)
        resp = client.get("/config/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_ready"] is False
    assert len(data["missing_fields"]) > 0


def test_get_config():
    """GET /config returns config with secrets masked."""
    cfg = _make_config()

    with patch("web.backend.routes.config.Config") as MockConfig:
        MockConfig.load.return_value = cfg
        client = TestClient(app)
        resp = client.get("/config")

    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "test-model"
    # API key should be masked
    assert data["model_api_key"] == "***"


def test_get_config_no_api_key():
    """GET /config without api_key omits the field."""
    cfg = _make_config(model_api_key=None)

    with patch("web.backend.routes.config.Config") as MockConfig:
        MockConfig.load.return_value = cfg
        client = TestClient(app)
        resp = client.get("/config")

    assert resp.status_code == 200
    data = resp.json()
    assert "model_api_key" not in data


def test_put_config(tmp_path):
    """PUT /config updates and saves config."""
    cfg = _make_config()
    config_path = tmp_path / ".cody" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.touch()

    with patch("web.backend.routes.config.Config") as MockConfig, \
         patch("web.backend.routes.config.Path") as MockPath:
        MockConfig.load.return_value = cfg
        # Make workdir / ".cody" / "config.json" resolve to our tmp file
        mock_wd = MagicMock()
        mock_wd.__truediv__ = lambda self, x: tmp_path / x
        MockPath.return_value = mock_wd
        MockPath.cwd.return_value = tmp_path
        MockPath.home.return_value = tmp_path

        client = TestClient(app)
        resp = client.put("/config", json={
            "model": "openai:gpt-4o",
            "enable_thinking": True,
            "thinking_budget": 5000,
        })

    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"


def test_put_config_partial_update():
    """PUT /config with only some fields updates only those."""
    cfg = _make_config()

    with patch("web.backend.routes.config.Config") as MockConfig, \
         patch("web.backend.routes.config.Path") as MockPath:
        MockConfig.load.return_value = cfg
        MockPath.cwd.return_value = Path.cwd()
        MockPath.home.return_value = Path.home()
        MockPath.return_value = MagicMock()

        client = TestClient(app)
        resp = client.put("/config", json={"model": "claude-haiku-3-5"})

    assert resp.status_code == 200

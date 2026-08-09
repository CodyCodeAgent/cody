"""Tests for Web API-key authentication."""

import pytest

from cody.core.auth import AuthError, AuthManager, AuthToken
from cody.core.config import AuthConfig


def test_default_auth_type():
    manager = AuthManager()
    assert manager.auth_type == "api_key"


def test_is_configured_false_by_default():
    assert AuthManager().is_configured is False


def test_is_configured_with_api_key():
    manager = AuthManager(AuthConfig(api_key="test_key"))
    assert manager.is_configured is True


def test_create_api_key():
    key = AuthManager().create_api_key()
    assert key.startswith("cody_")
    assert len(key) > 20


def test_validate_api_key_success():
    manager = AuthManager(AuthConfig(api_key="my_secret_key"))
    assert manager.validate_api_key("my_secret_key") is True


def test_validate_api_key_failure():
    manager = AuthManager(AuthConfig(api_key="my_secret_key"))
    assert manager.validate_api_key("wrong_key") is False


def test_validate_api_key_not_configured():
    assert AuthManager().validate_api_key("anything") is False


def test_validate_returns_api_key_identity():
    manager = AuthManager(AuthConfig(api_key="my_key"))
    result = manager.validate("my_key")
    assert isinstance(result, AuthToken)
    assert result.token_id == "api_key"
    assert result.scopes == ["*"]


def test_validate_rejects_wrong_api_key():
    manager = AuthManager(AuthConfig(api_key="my_key"))
    with pytest.raises(AuthError, match="Invalid API key"):
        manager.validate("wrong_key")


def test_auth_error_fields():
    error = AuthError("expired", code="custom_code")
    assert error.code == "custom_code"
    assert str(error) == "expired"

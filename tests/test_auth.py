"""Tests for authentication"""

import time

import pytest

from cody.core.auth import AuthError, AuthManager, AuthToken
from cody.core.config import AuthConfig


# ── AuthManager construction ─────────────────────────────────────────────────


def test_default_auth_type():
    mgr = AuthManager()
    assert mgr.auth_type == "api_key"


def test_oauth_auth_type():
    config = AuthConfig(type="oauth")
    mgr = AuthManager(config=config)
    assert mgr.auth_type == "oauth"


def test_is_configured_false_by_default():
    mgr = AuthManager()
    assert mgr.is_configured is False


def test_is_configured_with_api_key():
    config = AuthConfig(type="api_key", api_key="test_key")
    mgr = AuthManager(config=config)
    assert mgr.is_configured is True


def test_is_configured_with_token():
    config = AuthConfig(type="oauth", token="test_token")
    mgr = AuthManager(config=config)
    assert mgr.is_configured is True


# ── API key ──────────────────────────────────────────────────────────────────


def test_create_api_key():
    mgr = AuthManager()
    key = mgr.create_api_key()
    assert key.startswith("cody_")
    assert len(key) > 20


def test_validate_api_key_success():
    config = AuthConfig(type="api_key", api_key="my_secret_key")
    mgr = AuthManager(config=config)
    assert mgr.validate_api_key("my_secret_key") is True


def test_validate_api_key_failure():
    config = AuthConfig(type="api_key", api_key="my_secret_key")
    mgr = AuthManager(config=config)
    assert mgr.validate_api_key("wrong_key") is False


def test_validate_api_key_not_configured():
    mgr = AuthManager()
    assert mgr.validate_api_key("anything") is False


# ── Token creation and validation ────────────────────────────────────────────


def test_create_token():
    mgr = AuthManager(secret_key="test_secret")
    token = mgr.create_token(expires_in=3600)
    assert "." in token
    assert len(token) > 20


def test_validate_token_success():
    mgr = AuthManager(secret_key="test_secret")
    token = mgr.create_token(expires_in=3600)

    result = mgr.validate_token(token)
    assert isinstance(result, AuthToken)
    assert result.token_id != ""
    assert result.scopes == ["*"]


def test_validate_token_custom_scopes():
    mgr = AuthManager(secret_key="test_secret")
    token = mgr.create_token(expires_in=3600, scopes=["read", "write"])

    result = mgr.validate_token(token)
    assert result.scopes == ["read", "write"]


def test_validate_token_invalid_format():
    mgr = AuthManager(secret_key="test_secret")
    with pytest.raises(AuthError, match="Invalid token format"):
        mgr.validate_token("not_a_valid_token")


def test_validate_token_invalid_signature():
    mgr1 = AuthManager(secret_key="secret1")
    mgr2 = AuthManager(secret_key="secret2")

    token = mgr1.create_token(expires_in=3600)
    with pytest.raises(AuthError, match="Invalid token signature"):
        mgr2.validate_token(token)


def test_validate_token_expired():
    mgr = AuthManager(secret_key="test_secret")
    # Create a token that expires immediately
    token = mgr.create_token(expires_in=0)
    time.sleep(0.1)

    with pytest.raises(AuthError, match="Token expired"):
        mgr.validate_token(token)


def test_validate_token_bad_encoding():
    mgr = AuthManager(secret_key="test_secret")
    with pytest.raises(AuthError):
        mgr.validate_token("!!!invalid_base64!!!.fakesig")


# ── validate (auto-detect) ──────────────────────────────────────────────────


def test_validate_api_key_mode():
    config = AuthConfig(type="api_key", api_key="my_key")
    mgr = AuthManager(config=config)

    result = mgr.validate("my_key")
    assert isinstance(result, AuthToken)
    assert result.token_id == "api_key"
    assert result.scopes == ["*"]


def test_validate_api_key_mode_failure():
    config = AuthConfig(type="api_key", api_key="my_key")
    mgr = AuthManager(config=config)

    with pytest.raises(AuthError, match="Invalid API key"):
        mgr.validate("wrong_key")


def test_validate_oauth_mode():
    config = AuthConfig(type="oauth")
    mgr = AuthManager(config=config, secret_key="secret")

    token = mgr.create_token(expires_in=3600)
    result = mgr.validate(token)
    assert isinstance(result, AuthToken)


# ── refresh ──────────────────────────────────────────────────────────────────


def test_refresh_token():
    mgr = AuthManager(secret_key="test_secret")
    refresh = mgr.create_token(expires_in=86400)

    new_token = mgr.refresh(refresh, expires_in=3600)
    assert new_token != refresh

    result = mgr.validate_token(new_token)
    assert isinstance(result, AuthToken)


def test_refresh_with_expired_token():
    mgr = AuthManager(secret_key="test_secret")
    old_token = mgr.create_token(expires_in=0)
    time.sleep(0.1)

    with pytest.raises(AuthError, match="Token expired"):
        mgr.refresh(old_token)


# ── AuthError ────────────────────────────────────────────────────────────────


def test_auth_error_default_code():
    err = AuthError("something failed")
    assert err.code == "auth_failed"
    assert str(err) == "something failed"


def test_auth_error_custom_code():
    err = AuthError("expired", code="token_expired")
    assert err.code == "token_expired"

"""Authentication for Cody"""

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .config import AuthConfig


@dataclass
class AuthToken:
    """Represents a validated authentication token."""
    token_id: str
    issued_at: str
    expires_at: str
    scopes: list[str]


class AuthError(Exception):
    """Authentication error."""

    def __init__(self, message: str, code: str = "auth_failed"):
        self.code = code
        super().__init__(message)


class AuthManager:
    """Manage constant-time API-key authentication for Cody's Web API."""

    def __init__(
        self,
        config: Optional[AuthConfig] = None,
    ):
        self._config = config or AuthConfig()

    @property
    def auth_type(self) -> str:
        return self._config.type

    @property
    def is_configured(self) -> bool:
        """Check if authentication is configured with credentials."""
        return self._config.api_key is not None

    def create_api_key(self) -> str:
        """Generate a new API key."""
        return "cody_" + secrets.token_hex(24)

    def validate_api_key(self, key: str) -> bool:
        """Validate an API key against the configured key."""
        if not self._config.api_key:
            return False
        return hmac.compare_digest(key, self._config.api_key)

    def validate(self, credential: str) -> AuthToken:
        """Validate an API key.

        Returns AuthToken on success. Raises AuthError on failure.
        """
        if self.validate_api_key(credential):
            return AuthToken(
                token_id="api_key",
                issued_at=datetime.now(timezone.utc).isoformat(),
                expires_at="",
                scopes=["*"],
            )
        raise AuthError("Invalid API key")

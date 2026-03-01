"""Authentication for Cody"""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    """Manages authentication for Cody.

    Supports two modes:
    - api_key: Simple API key comparison
    - oauth: Token issuance and validation using HMAC-SHA256 signatures
    """

    def __init__(
        self,
        config: Optional[AuthConfig] = None,
        secret_key: Optional[str] = None,
    ):
        self._config = config or AuthConfig()
        self._secret = secret_key or secrets.token_hex(32)

    @property
    def auth_type(self) -> str:
        return self._config.type

    @property
    def is_configured(self) -> bool:
        """Check if authentication is configured with credentials."""
        if self._config.type == "api_key":
            return self._config.api_key is not None
        return self._config.token is not None

    def create_api_key(self) -> str:
        """Generate a new API key."""
        return "cody_" + secrets.token_hex(24)

    def create_token(
        self,
        expires_in: int = 3600,
        scopes: Optional[list[str]] = None,
    ) -> str:
        """Create a signed token.

        Args:
            expires_in: Seconds until expiration (default 1 hour).
            scopes: Optional list of permission scopes.

        Returns:
            Signed token string in format: <base64-payload>.<hex-signature>
        """
        now = datetime.now(timezone.utc)
        payload = {
            "tid": secrets.token_hex(8),
            "iat": now.isoformat(),
            "exp": (now + timedelta(seconds=expires_in)).isoformat(),
            "scopes": scopes or ["*"],
        }
        payload_json = json.dumps(payload, sort_keys=True)
        signature = self._sign(payload_json)
        encoded = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
        return f"{encoded}.{signature}"

    def validate_token(self, token: str) -> AuthToken:
        """Validate a signed token and return parsed AuthToken.

        Raises AuthError if invalid or expired.
        """
        parts = token.split(".")
        if len(parts) != 2:
            raise AuthError("Invalid token format")

        encoded_payload, signature = parts

        # Restore base64 padding
        padding = 4 - len(encoded_payload) % 4
        if padding != 4:
            encoded_payload += "=" * padding

        try:
            payload_json = base64.urlsafe_b64decode(encoded_payload).decode()
        except Exception as exc:
            raise AuthError("Invalid token encoding") from exc

        expected_sig = self._sign(payload_json)
        if not hmac.compare_digest(signature, expected_sig):
            raise AuthError("Invalid token signature")

        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise AuthError("Invalid token payload") from exc

        # Check expiration
        exp = payload.get("exp")
        if exp:
            exp_dt = datetime.fromisoformat(exp)
            if datetime.now(timezone.utc) > exp_dt:
                raise AuthError("Token expired", code="token_expired")

        return AuthToken(
            token_id=payload.get("tid", ""),
            issued_at=payload.get("iat", ""),
            expires_at=payload.get("exp", ""),
            scopes=payload.get("scopes", []),
        )

    def validate_api_key(self, key: str) -> bool:
        """Validate an API key against the configured key."""
        if not self._config.api_key:
            return False
        return hmac.compare_digest(key, self._config.api_key)

    def validate(self, credential: str) -> AuthToken:
        """Validate a credential (auto-detect api_key vs token).

        Returns AuthToken on success. Raises AuthError on failure.
        """
        if self._config.type == "api_key":
            if self.validate_api_key(credential):
                return AuthToken(
                    token_id="api_key",
                    issued_at=datetime.now(timezone.utc).isoformat(),
                    expires_at="",
                    scopes=["*"],
                )
            raise AuthError("Invalid API key")
        return self.validate_token(credential)

    def refresh(self, refresh_token_str: str, expires_in: int = 3600) -> str:
        """Refresh a token using a refresh token.

        Validates the refresh token, then issues a new token.
        """
        self.validate_token(refresh_token_str)
        return self.create_token(expires_in=expires_in)

    def _sign(self, data: str) -> str:
        """Create HMAC-SHA256 signature."""
        return hmac.new(
            self._secret.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()

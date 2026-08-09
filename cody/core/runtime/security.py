"""Runtime action authorization primitives."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any
import hmac
import json
import time


class RuntimeActionEffect(str, Enum):
    """Security effect associated with a runtime action."""

    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class RuntimeActionDecision:
    """Authorization decision for one runtime action."""

    allowed: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason}


@dataclass(frozen=True)
class RuntimeActionPolicy:
    """Allow/deny policy for CLI, TUI, and Web runtime actions."""

    allowed_actions: frozenset[str] | None = None
    denied_actions: frozenset[str] = field(default_factory=frozenset)
    mutating_actions: frozenset[str] = field(default_factory=lambda: frozenset({
        "approvals.approve",
        "approvals.reject",
        "artifacts.save",
    }))
    require_actor_for_writes: bool = True
    actor_allowed_actions: dict[str, frozenset[str]] = field(default_factory=dict)

    def authorize(self, action: str, *, actor_id: str | None = None) -> RuntimeActionDecision:
        if action in self.denied_actions:
            return RuntimeActionDecision(False, f"Action is denied: {action}")
        if self.allowed_actions is not None and action not in self.allowed_actions:
            return RuntimeActionDecision(False, f"Action is not allowlisted: {action}")
        if action in self.mutating_actions and self.require_actor_for_writes and not actor_id:
            return RuntimeActionDecision(False, f"Action requires actor_id: {action}")
        if actor_id and actor_id in self.actor_allowed_actions:
            allowed = self.actor_allowed_actions[actor_id]
            if action not in allowed:
                return RuntimeActionDecision(False, f"Actor is not allowed to perform action: {action}")
        return RuntimeActionDecision(True)

    def effect_for(self, action: str) -> RuntimeActionEffect:
        return RuntimeActionEffect.WRITE if action in self.mutating_actions else RuntimeActionEffect.READ


class RuntimeAuthError(RuntimeError):
    """Raised when runtime token authentication fails."""


@dataclass(frozen=True)
class RuntimePrincipal:
    """Authenticated runtime actor."""

    actor_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "scopes": sorted(self.scopes),
            "metadata": self.metadata,
        }


class RuntimeTokenAuthority:
    """Small HMAC token issuer/verifier for local runtime surfaces."""

    def __init__(self, secret: str | bytes):
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret

    def issue(self, principal: RuntimePrincipal, *, expires_in_seconds: int = 3600) -> str:
        payload = {
            "actor_id": principal.actor_id,
            "scopes": sorted(principal.scopes),
            "metadata": principal.metadata,
            "exp": int(time.time()) + expires_in_seconds,
        }
        body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = _b64(hmac.new(self.secret, body.encode("ascii"), sha256).digest())
        return f"{body}.{signature}"

    def verify(self, token: str) -> RuntimePrincipal:
        try:
            body, signature = token.split(".", 1)
        except ValueError as exc:
            raise RuntimeAuthError("Invalid runtime token format") from exc
        expected = _b64(hmac.new(self.secret, body.encode("ascii"), sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise RuntimeAuthError("Invalid runtime token signature")
        try:
            payload = json.loads(urlsafe_b64decode(_pad_b64(body)).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeAuthError("Invalid runtime token payload") from exc
        if int(payload.get("exp", 0)) < int(time.time()):
            raise RuntimeAuthError("Runtime token expired")
        return RuntimePrincipal(
            actor_id=payload["actor_id"],
            scopes=frozenset(payload.get("scopes") or ()),
            metadata=dict(payload.get("metadata") or {}),
        )


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _pad_b64(data: str) -> bytes:
    return (data + "=" * (-len(data) % 4)).encode("ascii")

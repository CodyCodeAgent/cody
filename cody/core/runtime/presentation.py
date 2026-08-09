"""Transport-light adapters for CLI, TUI, and Web runtime surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json

from .interface import RuntimeAPIResponse, RuntimeInterface
from .security import RuntimeAuthError, RuntimeTokenAuthority


@dataclass(frozen=True)
class RuntimeActionRequest:
    """Normalized request from CLI, TUI, or Web callers."""

    action: str
    params: dict[str, Any] = field(default_factory=dict)
    actor_id: str | None = None
    token: str | None = None


class RuntimeCommandRouter:
    """Parse simple CLI-style arguments and dispatch to `RuntimeInterface`."""

    def __init__(self, runtime: RuntimeInterface, *, token_authority: RuntimeTokenAuthority | None = None):
        self.runtime = runtime
        self.token_authority = token_authority

    def run(self, argv: list[str]) -> RuntimeAPIResponse:
        if not argv:
            return RuntimeAPIResponse(ok=False, error="Missing runtime action")
        action = argv[0]
        params = dict(self._parse_arg(arg) for arg in argv[1:])
        actor_id = params.pop("actor_id", None)
        return self.runtime.handle(action, actor_id=actor_id, **params)

    def _parse_arg(self, arg: str) -> tuple[str, Any]:
        if "=" not in arg:
            raise ValueError(f"Runtime CLI args must use key=value form: {arg}")
        key, raw_value = arg.split("=", 1)
        return key.replace("-", "_"), _parse_value(raw_value)


class RuntimeWebRouter:
    """Framework-agnostic Web adapter over `RuntimeInterface`."""

    def __init__(self, runtime: RuntimeInterface, *, token_authority: RuntimeTokenAuthority | None = None):
        self.runtime = runtime
        self.token_authority = token_authority

    def handle(self, request: RuntimeActionRequest | dict[str, Any]) -> dict[str, Any]:
        normalized = request if isinstance(request, RuntimeActionRequest) else RuntimeActionRequest(
            action=request["action"],
            params=dict(request.get("params") or {}),
            actor_id=request.get("actor_id"),
            token=request.get("token"),
        )
        actor_id = normalized.actor_id
        if normalized.token and self.token_authority is not None:
            try:
                actor_id = self.token_authority.verify(normalized.token).actor_id
            except RuntimeAuthError as exc:
                return RuntimeAPIResponse(ok=False, error=str(exc)).to_dict()
        response = self.runtime.handle(normalized.action, actor_id=actor_id, **normalized.params)
        data = response.to_dict()
        if actor_id:
            data.setdefault("data", {}).setdefault("actor_id", actor_id)
        return data


class RuntimeTUIView:
    """Build TUI-friendly view models from the runtime interface."""

    def __init__(self, runtime: RuntimeInterface):
        self.runtime = runtime

    def dashboard(self) -> dict[str, Any]:
        runs = self.runtime.list_runs().to_dict()
        pending = self.runtime.list_approvals(status="pending").to_dict()
        return {
            "runs": runs["data"].get("runs", []) if runs["ok"] else [],
            "pending_approvals": pending["data"].get("approvals", []) if pending["ok"] else [],
            "errors": [error for error in (runs.get("error"), pending.get("error")) if error],
        }

    def run_detail(self, run_id: str) -> dict[str, Any]:
        timeline = self.runtime.get_timeline(run_id).to_dict()
        artifacts = self.runtime.list_artifacts(run_id=run_id).to_dict()
        return {
            "run_id": run_id,
            "timeline": timeline["data"].get("items", []) if timeline["ok"] else [],
            "artifacts": artifacts["data"].get("artifacts", []) if artifacts["ok"] else [],
            "errors": [error for error in (timeline.get("error"), artifacts.get("error")) if error],
        }


def _parse_value(raw_value: str) -> Any:
    if raw_value in {"true", "false"}:
        return raw_value == "true"
    if raw_value == "null":
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value

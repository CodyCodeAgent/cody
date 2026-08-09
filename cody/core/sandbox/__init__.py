"""Cody sandbox execution API."""

from typing import TYPE_CHECKING, Any

from .base import (
    SandboxBackend,
    SandboxError,
    SandboxHandle,
    SandboxPolicyError,
    SandboxProcess,
    SandboxUnavailableError,
)
from .models import (
    FilesystemPolicy,
    NetworkMode,
    NetworkPolicy,
    ResourceLimits,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxSnapshot,
    SandboxSpec,
    SandboxStatus,
)
from .local import (
    BubblewrapSandboxBackend,
    LocalPolicySandboxBackend,
    SeatbeltSandboxBackend,
    bubblewrap_prefix,
    seatbelt_profile,
)
from .manager import SandboxManager
from .docker import DockerSandboxBackend, DockerSandboxHandle
from .remote import RemoteSandboxBackend, RemoteSandboxHandle, RemoteSandboxTransport

if TYPE_CHECKING:
    from cody.core.config import Config


def sandbox_spec_from_config(
    config: "Config",
    *,
    run_id: str,
    workdir: Any,
    sandbox_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SandboxSpec:
    """Build a spec without importing configuration/model dependencies eagerly."""

    from .factory import sandbox_spec_from_config as build_spec

    return build_spec(
        config,
        run_id=run_id,
        workdir=workdir,
        sandbox_id=sandbox_id,
        metadata=metadata,
    )

__all__ = [
    "FilesystemPolicy",
    "BubblewrapSandboxBackend",
    "DockerSandboxBackend",
    "DockerSandboxHandle",
    "LocalPolicySandboxBackend",
    "NetworkMode",
    "NetworkPolicy",
    "ResourceLimits",
    "RemoteSandboxBackend",
    "RemoteSandboxHandle",
    "RemoteSandboxTransport",
    "SandboxBackend",
    "SandboxError",
    "SandboxExecutionRequest",
    "SandboxExecutionResult",
    "SandboxHandle",
    "SandboxManager",
    "SandboxPolicyError",
    "SandboxProcess",
    "SandboxSnapshot",
    "SandboxSpec",
    "SandboxStatus",
    "SandboxUnavailableError",
    "SeatbeltSandboxBackend",
    "bubblewrap_prefix",
    "seatbelt_profile",
    "sandbox_spec_from_config",
]

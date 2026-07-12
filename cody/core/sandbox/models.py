"""Stable data model shared by all Cody sandbox backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class SandboxStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    TERMINATED = "terminated"
    FAILED = "failed"


class NetworkMode(str, Enum):
    DISABLED = "disabled"
    ALLOWLIST = "allowlist"
    PROXIED = "proxied"
    UNRESTRICTED = "unrestricted"


@dataclass(frozen=True)
class FilesystemPolicy:
    read_roots: tuple[Path, ...] = ()
    write_roots: tuple[Path, ...] = ()
    denied_roots: tuple[Path, ...] = ()
    private_workspace: bool = False

    def normalized(self) -> "FilesystemPolicy":
        return FilesystemPolicy(
            read_roots=tuple(path.expanduser().resolve() for path in self.read_roots),
            write_roots=tuple(path.expanduser().resolve() for path in self.write_roots),
            denied_roots=tuple(path.expanduser().resolve() for path in self.denied_roots),
            private_workspace=self.private_workspace,
        )


@dataclass(frozen=True)
class NetworkPolicy:
    mode: NetworkMode = NetworkMode.DISABLED
    allowed_domains: tuple[str, ...] = ()
    allowed_cidrs: tuple[str, ...] = ()
    proxy_url: str | None = None


@dataclass(frozen=True)
class ResourceLimits:
    cpu_count: float | None = None
    memory_mb: int | None = None
    process_limit: int | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class SandboxSpec:
    run_id: str
    workdir: Path
    sandbox_id: str = field(default_factory=lambda: f"sandbox_{uuid4().hex}")
    backend: str = "auto"
    image: str | None = None
    filesystem: FilesystemPolicy = field(default_factory=FilesystemPolicy)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    env: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    fail_if_unavailable: bool = True

    def normalized(self) -> "SandboxSpec":
        return SandboxSpec(
            sandbox_id=self.sandbox_id,
            run_id=self.run_id,
            workdir=self.workdir.expanduser().resolve(),
            backend=self.backend,
            image=self.image,
            filesystem=self.filesystem.normalized(),
            network=self.network,
            resources=self.resources,
            env=dict(self.env),
            metadata=dict(self.metadata),
            fail_if_unavailable=self.fail_if_unavailable,
        )


@dataclass(frozen=True)
class SandboxExecutionRequest:
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    stdin: str | None = None
    timeout_seconds: float | None = None
    capture_limit: int = 1_000_000

    @classmethod
    def shell(
        cls,
        command: str,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> "SandboxExecutionRequest":
        return cls(
            argv=("/bin/sh", "-lc", command),
            cwd=cwd,
            env=env or {},
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True)
class SandboxExecutionResult:
    sandbox_id: str
    argv: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    timed_out: bool = False


@dataclass(frozen=True)
class SandboxSnapshot:
    snapshot_id: str
    sandbox_id: str
    backend: str
    reference: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "sandbox_id": self.sandbox_id,
            "backend": self.backend,
            "reference": self.reference,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SandboxSnapshot":
        return cls(
            snapshot_id=str(data["snapshot_id"]),
            sandbox_id=str(data["sandbox_id"]),
            backend=str(data["backend"]),
            reference=str(data["reference"]),
            metadata=dict(data.get("metadata") or {}),
        )

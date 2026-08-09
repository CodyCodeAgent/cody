"""Sandbox backend and live-handle contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import (
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxSnapshot,
    SandboxSpec,
    SandboxStatus,
)


class SandboxError(RuntimeError):
    pass


class SandboxUnavailableError(SandboxError):
    pass


class SandboxPolicyError(SandboxError):
    pass


class SandboxProcess(ABC):
    """Interactive child process whose transport crosses the sandbox boundary."""

    stdin: Any
    stdout: Any
    stderr: Any

    @property
    @abstractmethod
    def returncode(self) -> int | None: ...

    @abstractmethod
    async def wait(self) -> int: ...

    @abstractmethod
    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]: ...

    @abstractmethod
    def terminate(self) -> None: ...

    @abstractmethod
    def kill(self) -> None: ...


class SandboxHandle(ABC):
    """One isolated environment associated with a Runtime Run."""

    spec: SandboxSpec
    backend_name: str

    @property
    @abstractmethod
    def status(self) -> SandboxStatus: ...

    @abstractmethod
    async def exec(self, request: SandboxExecutionRequest) -> SandboxExecutionResult: ...

    @abstractmethod
    async def spawn(self, request: SandboxExecutionRequest) -> SandboxProcess: ...

    @abstractmethod
    async def pause(self) -> None: ...

    @abstractmethod
    async def resume(self) -> None: ...

    @abstractmethod
    async def snapshot(self) -> SandboxSnapshot: ...

    @abstractmethod
    async def restore(self, snapshot: SandboxSnapshot) -> None: ...

    @abstractmethod
    async def fork(
        self, *, sandbox_id: str | None = None, run_id: str | None = None
    ) -> "SandboxHandle": ...

    @abstractmethod
    async def terminate(self) -> None: ...

    async def __aenter__(self) -> "SandboxHandle":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.terminate()


class SandboxBackend(ABC):
    name: str

    @abstractmethod
    async def available(self) -> bool: ...

    @abstractmethod
    async def create(self, spec: SandboxSpec) -> SandboxHandle: ...

"""Provider-neutral remote sandbox adapter."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from uuid import uuid4

from .base import SandboxBackend, SandboxHandle, SandboxPolicyError, SandboxProcess
from .models import (
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxSnapshot,
    SandboxSpec,
    SandboxStatus,
)


class RemoteSandboxTransport(Protocol):
    async def available(self) -> bool: ...
    async def create(self, spec: SandboxSpec) -> str: ...
    async def exec(self, remote_id: str, request: SandboxExecutionRequest) -> SandboxExecutionResult: ...
    async def spawn(self, remote_id: str, request: SandboxExecutionRequest) -> SandboxProcess: ...
    async def pause(self, remote_id: str) -> None: ...
    async def resume(self, remote_id: str) -> None: ...
    async def snapshot(self, remote_id: str) -> str: ...
    async def restore(self, remote_id: str, reference: str) -> None: ...
    async def fork(self, remote_id: str, spec: SandboxSpec) -> str: ...
    async def terminate(self, remote_id: str) -> None: ...


class RemoteSandboxHandle(SandboxHandle):
    backend_name = "remote"

    def __init__(self, spec: SandboxSpec, transport: RemoteSandboxTransport, remote_id: str):
        self.spec = spec.normalized()
        self.transport = transport
        self.remote_id = remote_id
        self._status = SandboxStatus.RUNNING

    @property
    def status(self) -> SandboxStatus:
        return self._status

    async def exec(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        if self._status != SandboxStatus.RUNNING:
            raise SandboxPolicyError(f"Sandbox is not running: {self._status.value}")
        result = await self.transport.exec(self.remote_id, request)
        return replace(result, sandbox_id=self.spec.sandbox_id)

    async def spawn(self, request: SandboxExecutionRequest) -> SandboxProcess:
        if self._status != SandboxStatus.RUNNING:
            raise SandboxPolicyError(f"Sandbox is not running: {self._status.value}")
        return await self.transport.spawn(self.remote_id, request)

    async def pause(self) -> None:
        await self.transport.pause(self.remote_id)
        self._status = SandboxStatus.PAUSED

    async def resume(self) -> None:
        await self.transport.resume(self.remote_id)
        self._status = SandboxStatus.RUNNING

    async def snapshot(self) -> SandboxSnapshot:
        reference = await self.transport.snapshot(self.remote_id)
        return SandboxSnapshot(
            snapshot_id=f"snapshot_{uuid4().hex}",
            sandbox_id=self.spec.sandbox_id,
            backend=self.backend_name,
            reference=reference,
            metadata={"remote_id": self.remote_id},
        )

    async def restore(self, snapshot: SandboxSnapshot) -> None:
        await self.transport.restore(self.remote_id, snapshot.reference)

    async def fork(
        self, *, sandbox_id: str | None = None, run_id: str | None = None
    ) -> SandboxHandle:
        spec = replace(
            self.spec,
            sandbox_id=sandbox_id or f"sandbox_{uuid4().hex}",
            run_id=run_id or self.spec.run_id,
        )
        remote_id = await self.transport.fork(self.remote_id, spec)
        return RemoteSandboxHandle(spec, self.transport, remote_id)

    async def terminate(self) -> None:
        if self._status != SandboxStatus.TERMINATED:
            await self.transport.terminate(self.remote_id)
            self._status = SandboxStatus.TERMINATED


class RemoteSandboxBackend(SandboxBackend):
    name = "remote"

    def __init__(self, transport: RemoteSandboxTransport, *, name: str = "remote"):
        self.transport = transport
        self.name = name

    async def available(self) -> bool:
        return await self.transport.available()

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        remote_id = await self.transport.create(spec.normalized())
        return RemoteSandboxHandle(spec, self.transport, remote_id)

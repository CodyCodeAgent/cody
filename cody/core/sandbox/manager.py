"""Backend registry and policy-aware sandbox selection."""

from __future__ import annotations

import platform

from .base import SandboxBackend, SandboxHandle, SandboxUnavailableError
from .local import BubblewrapSandboxBackend, LocalPolicySandboxBackend, SeatbeltSandboxBackend
from .docker import DockerSandboxBackend
from .models import SandboxSpec


class SandboxManager:
    def __init__(self, backends: list[SandboxBackend] | None = None):
        defaults = backends or [
            LocalPolicySandboxBackend(),
            SeatbeltSandboxBackend(),
            BubblewrapSandboxBackend(),
            DockerSandboxBackend(),
            DockerSandboxBackend("podman"),
        ]
        self.backends = {backend.name: backend for backend in defaults}

    def register(self, backend: SandboxBackend) -> None:
        if backend.name in self.backends:
            raise ValueError(f"Duplicate sandbox backend: {backend.name}")
        self.backends[backend.name] = backend

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        normalized = spec.normalized()
        name = normalized.backend
        if name == "auto":
            name = "seatbelt" if platform.system() == "Darwin" else "bubblewrap"
        backend = self.backends.get(name)
        if backend is not None and await backend.available():
            return await backend.create(normalized)
        if not normalized.fail_if_unavailable:
            fallback = self.backends.get("local-policy")
            if fallback is not None:
                return await fallback.create(normalized)
        raise SandboxUnavailableError(f"Sandbox backend is unavailable: {name}")

"""Long-lived Docker/Podman sandbox backend."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import time
from uuid import uuid4

from .base import SandboxBackend, SandboxHandle, SandboxPolicyError, SandboxProcess, SandboxUnavailableError
from .models import (
    NetworkMode,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxSnapshot,
    SandboxSpec,
    SandboxStatus,
)
from .process import run_process, spawn_process
from .local import LocalSandboxHandle


class DockerSandboxHandle(SandboxHandle):
    backend_name = "docker"

    def __init__(self, spec: SandboxSpec, *, executable: str, container_id: str):
        self.spec = spec.normalized()
        self.executable = executable
        self.container_id = container_id
        self._status = SandboxStatus.RUNNING

    @property
    def status(self) -> SandboxStatus:
        return self._status

    async def _control(self, *argv: str) -> SandboxExecutionResult:
        return await run_process(
            self.spec.sandbox_id,
            SandboxExecutionRequest(argv=(self.executable, *argv)),
            default_cwd=self.spec.workdir,
        )

    async def exec(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        if self._status != SandboxStatus.RUNNING:
            raise SandboxPolicyError(f"Sandbox is not running: {self._status.value}")
        args = [self.executable, "exec"]
        cwd = request.cwd or self.spec.workdir
        args.extend(("--workdir", str(cwd)))
        for key, value in {**self.spec.env, **request.env}.items():
            args.extend(("--env", f"{key}={value}"))
        args.append(self.container_id)
        args.extend(request.argv)
        started = time.monotonic()
        result = await run_process(
            self.spec.sandbox_id,
            replace(request, argv=tuple(args), cwd=self.spec.workdir, env={}),
            default_cwd=self.spec.workdir,
            default_timeout=self.spec.resources.timeout_seconds,
        )
        return replace(
            result,
            argv=request.argv,
            duration_seconds=time.monotonic() - started,
        )

    def _exec_argv(self, request: SandboxExecutionRequest) -> tuple[str, ...]:
        args = [self.executable, "exec", "-i"]
        args.extend(("--workdir", str(request.cwd or self.spec.workdir)))
        for key, value in {**self.spec.env, **request.env}.items():
            args.extend(("--env", f"{key}={value}"))
        args.append(self.container_id)
        args.extend(request.argv)
        return tuple(args)

    async def spawn(self, request: SandboxExecutionRequest) -> SandboxProcess:
        if self._status != SandboxStatus.RUNNING:
            raise SandboxPolicyError(f"Sandbox is not running: {self._status.value}")
        return await spawn_process(
            replace(request, argv=self._exec_argv(request), cwd=self.spec.workdir, env={}),
            default_cwd=self.spec.workdir,
        )

    async def pause(self) -> None:
        if self._status == SandboxStatus.RUNNING:
            result = await self._control("pause", self.container_id)
            if result.returncode != 0:
                raise SandboxUnavailableError(result.stderr)
            self._status = SandboxStatus.PAUSED

    async def resume(self) -> None:
        if self._status == SandboxStatus.PAUSED:
            result = await self._control("unpause", self.container_id)
            if result.returncode != 0:
                raise SandboxUnavailableError(result.stderr)
            self._status = SandboxStatus.RUNNING

    async def snapshot(self) -> SandboxSnapshot:
        snapshot_id = f"snapshot_{uuid4().hex}"
        image = f"cody-sandbox-snapshot:{snapshot_id}"
        result = await self._control("commit", self.container_id, image)
        if result.returncode != 0:
            raise SandboxUnavailableError(result.stderr)
        workspace_handle = LocalSandboxHandle(
            replace(
                self.spec,
                sandbox_id=f"{self.spec.sandbox_id}_workspace",
                backend="local-policy",
            )
        )
        workspace_snapshot = await workspace_handle.snapshot()
        await workspace_handle.terminate()
        return SandboxSnapshot(
            snapshot_id=snapshot_id,
            sandbox_id=self.spec.sandbox_id,
            backend=self.backend_name,
            reference=image,
            metadata={
                "container_id": self.container_id,
                "workspace_snapshot": workspace_snapshot.to_dict(),
            },
        )

    async def restore(self, snapshot: SandboxSnapshot) -> None:
        await self.terminate()
        replacement = await DockerSandboxBackend(self.executable).create(
            replace(self.spec, image=snapshot.reference)
        )
        assert isinstance(replacement, DockerSandboxHandle)
        self.container_id = replacement.container_id
        self._status = SandboxStatus.RUNNING
        workspace_data = snapshot.metadata.get("workspace_snapshot")
        if isinstance(workspace_data, dict):
            workspace_handle = LocalSandboxHandle(
                replace(
                    self.spec,
                    sandbox_id=f"{self.spec.sandbox_id}_workspace_restore",
                    backend="local-policy",
                )
            )
            await workspace_handle.restore(SandboxSnapshot.from_dict(workspace_data))
            await workspace_handle.terminate()

    async def fork(
        self, *, sandbox_id: str | None = None, run_id: str | None = None
    ) -> SandboxHandle:
        snapshot = await self.snapshot()
        fork_id = sandbox_id or f"sandbox_{uuid4().hex}"
        fork_workdir = self.spec.workdir
        if self.spec.filesystem.private_workspace:
            local = LocalSandboxHandle(self.spec)
            local_fork = await local.fork(sandbox_id=fork_id)
            fork_workdir = local_fork.spec.workdir
            await local.terminate()
            await local_fork.terminate()
        filesystem = self.spec.filesystem
        if fork_workdir != self.spec.workdir:
            filesystem = replace(
                filesystem,
                read_roots=(fork_workdir,),
                write_roots=(fork_workdir,),
            )
        return await DockerSandboxBackend(self.executable).create(
            replace(
                self.spec,
                sandbox_id=fork_id,
                run_id=run_id or self.spec.run_id,
                workdir=fork_workdir,
                filesystem=filesystem,
                image=snapshot.reference,
            )
        )

    async def terminate(self) -> None:
        if self._status == SandboxStatus.TERMINATED:
            return
        await self._control("rm", "-f", self.container_id)
        self._status = SandboxStatus.TERMINATED


class DockerSandboxBackend(SandboxBackend):
    name = "docker"

    def __init__(self, executable: str = "docker"):
        self.executable = executable
        if executable == "podman":
            self.name = "podman"

    async def available(self) -> bool:
        if shutil.which(self.executable) is None:
            return False
        result = await run_process(
            "sandbox_probe",
            SandboxExecutionRequest(argv=(self.executable, "info"), timeout_seconds=5),
            default_cwd=Path.cwd(),
        )
        return result.returncode == 0

    def create_argv(self, spec: SandboxSpec) -> tuple[str, ...]:
        if spec.network.mode in {NetworkMode.ALLOWLIST, NetworkMode.PROXIED} and not spec.network.proxy_url:
            raise SandboxPolicyError("Docker allowlist/proxied mode requires proxy_url")
        if spec.network.mode in {NetworkMode.ALLOWLIST, NetworkMode.PROXIED} and not spec.metadata.get("network_name"):
            raise SandboxPolicyError(
                "Docker allowlist/proxied mode requires a proxy-only network_name"
            )
        name = f"cody-{spec.sandbox_id}".replace("_", "-")[:63]
        args = [
            self.executable,
            "create",
            "--pull=never",
            "--name",
            name,
            "--workdir",
            str(spec.workdir),
        ]
        if spec.network.mode == NetworkMode.DISABLED:
            args.extend(("--network", "none"))
        elif spec.network.mode in {NetworkMode.ALLOWLIST, NetworkMode.PROXIED}:
            args.extend(("--network", str(spec.metadata["network_name"])))
        if spec.resources.cpu_count is not None:
            args.extend(("--cpus", str(spec.resources.cpu_count)))
        if spec.resources.memory_mb is not None:
            args.extend(("--memory", f"{spec.resources.memory_mb}m"))
        if spec.resources.process_limit is not None:
            args.extend(("--pids-limit", str(spec.resources.process_limit)))
        mounted: set[Path] = set()
        for root in (*spec.filesystem.read_roots, *spec.filesystem.write_roots):
            root = root.resolve()
            if root in mounted:
                continue
            mounted.add(root)
            mode = "rw" if root in spec.filesystem.write_roots else "ro"
            args.extend(("--volume", f"{root}:{root}:{mode}"))
        for root in spec.filesystem.denied_roots:
            if root.exists() and root.is_dir():
                args.extend(("--tmpfs", f"{root}:ro,noexec,nosuid,size=1m"))
            elif root.exists():
                args.extend(("--mount", f"type=bind,source=/dev/null,target={root},readonly"))
        for key, value in spec.env.items():
            args.extend(("--env", f"{key}={value}"))
        if spec.network.proxy_url:
            for key in ("HTTP_PROXY", "HTTPS_PROXY"):
                args.extend(("--env", f"{key}={spec.network.proxy_url}"))
        labels = {
            "cody.run_id": spec.run_id,
            "cody.sandbox_id": spec.sandbox_id,
        }
        for key, value in labels.items():
            args.extend(("--label", f"{key}={value}"))
        args.extend((spec.image or "ubuntu:24.04", "sleep", "infinity"))
        return tuple(args)

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        if not await self.available():
            raise SandboxUnavailableError(f"{self.executable} daemon is unavailable")
        normalized = spec.normalized()
        image = normalized.image or "ubuntu:24.04"
        pull_policy = str(normalized.metadata.get("image_pull_policy", "if_missing"))
        should_pull = pull_policy == "always"
        if pull_policy == "if_missing":
            inspected = await run_process(
                normalized.sandbox_id,
                SandboxExecutionRequest(
                    argv=(self.executable, "image", "inspect", image),
                    timeout_seconds=15,
                ),
                default_cwd=normalized.workdir,
            )
            should_pull = inspected.returncode != 0
        if should_pull:
            pulled = await run_process(
                normalized.sandbox_id,
                SandboxExecutionRequest(
                    argv=(self.executable, "pull", image), timeout_seconds=300
                ),
                default_cwd=normalized.workdir,
            )
            if pulled.returncode != 0:
                raise SandboxUnavailableError(pulled.stderr or pulled.stdout)
        created = await run_process(
            normalized.sandbox_id,
            SandboxExecutionRequest(argv=self.create_argv(normalized), timeout_seconds=60),
            default_cwd=normalized.workdir,
        )
        if created.returncode != 0:
            raise SandboxUnavailableError(created.stderr or created.stdout)
        container_id = created.stdout.strip()
        started = await run_process(
            normalized.sandbox_id,
            SandboxExecutionRequest(argv=(self.executable, "start", container_id), timeout_seconds=30),
            default_cwd=normalized.workdir,
        )
        if started.returncode != 0:
            await run_process(
                normalized.sandbox_id,
                SandboxExecutionRequest(argv=(self.executable, "rm", "-f", container_id)),
                default_cwd=normalized.workdir,
            )
            raise SandboxUnavailableError(started.stderr or started.stdout)
        return DockerSandboxHandle(
            normalized, executable=self.executable, container_id=container_id
        )

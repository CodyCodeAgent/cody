"""Host-policy, macOS Seatbelt, and Linux bubblewrap sandbox backends."""

from __future__ import annotations

from dataclasses import replace
import json
import platform
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import sys
import tarfile
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


def _state_root(spec: SandboxSpec) -> Path:
    configured = spec.metadata.get("state_root")
    root = Path(str(configured)).expanduser() if configured else Path.home() / ".cody" / "sandboxes"
    path = root / spec.sandbox_id
    path.mkdir(parents=True, exist_ok=True)
    # macOS exposes its temporary directory through the /var -> /private/var
    # symlink. Seatbelt compares canonical paths, so both the policy rule and
    # TMPDIR must use the resolved spelling or child process writes are denied.
    return path.resolve()


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


class LocalSandboxHandle(SandboxHandle):
    backend_name = "local-policy"

    def __init__(self, spec: SandboxSpec, *, argv_prefix: tuple[str, ...] = ()):
        self.spec = spec.normalized()
        self.argv_prefix = argv_prefix
        self._status = SandboxStatus.RUNNING
        self.state_root = _state_root(self.spec)
        self._processes: list[SandboxProcess] = []

    @property
    def status(self) -> SandboxStatus:
        return self._status

    async def exec(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        if self._status != SandboxStatus.RUNNING:
            raise SandboxPolicyError(f"Sandbox is not running: {self._status.value}")
        cwd = (request.cwd or self.spec.workdir).resolve()
        allowed = self.spec.filesystem.read_roots + self.spec.filesystem.write_roots
        if allowed and not _within(cwd, allowed):
            raise SandboxPolicyError(f"Working directory is outside sandbox roots: {cwd}")
        return await run_process(
            self.spec.sandbox_id,
            replace(request, cwd=cwd),
            argv_prefix=self.argv_prefix,
            base_env=self.spec.env,
            default_cwd=self.spec.workdir,
            default_timeout=self.spec.resources.timeout_seconds,
        )

    async def spawn(self, request: SandboxExecutionRequest) -> SandboxProcess:
        if self._status != SandboxStatus.RUNNING:
            raise SandboxPolicyError(f"Sandbox is not running: {self._status.value}")
        cwd = (request.cwd or self.spec.workdir).resolve()
        allowed = self.spec.filesystem.read_roots + self.spec.filesystem.write_roots
        if allowed and not _within(cwd, allowed):
            raise SandboxPolicyError(f"Working directory is outside sandbox roots: {cwd}")
        process = await spawn_process(
            replace(request, cwd=cwd),
            argv_prefix=self.argv_prefix,
            base_env=self.spec.env,
            default_cwd=self.spec.workdir,
        )
        self._processes.append(process)
        return process

    async def pause(self) -> None:
        if self._status == SandboxStatus.RUNNING:
            # Local MCP/LSP processes are reconstructable and are stopped at a
            # durable wait boundary so no worker process remains occupied.
            await self._stop_processes()
            self._status = SandboxStatus.PAUSED

    async def resume(self) -> None:
        if self._status == SandboxStatus.PAUSED:
            self._status = SandboxStatus.RUNNING

    async def snapshot(self) -> SandboxSnapshot:
        snapshot_id = f"snapshot_{uuid4().hex}"
        if not self.spec.filesystem.private_workspace:
            return SandboxSnapshot(
                snapshot_id=snapshot_id,
                sandbox_id=self.spec.sandbox_id,
                backend=self.backend_name,
                reference=str(self.spec.workdir),
                metadata={
                    "workdir": str(self.spec.workdir),
                    "durable_shared_workspace": True,
                },
            )
        archive = self.state_root / f"{snapshot_id}.tar.gz"
        excluded_names = set(
            self.spec.metadata.get(
                "snapshot_excludes",
                (".git", ".venv", "node_modules", ".cody", "__pycache__"),
            )
        )
        with tarfile.open(archive, "w:gz") as bundle:
            def exclude_state(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
                relative = Path(tarinfo.name).relative_to("workspace")
                source = (self.spec.workdir / relative).resolve()
                state = self.state_root.resolve()
                if source == state or state in source.parents:
                    return None
                if any(part in excluded_names for part in relative.parts):
                    return None
                return tarinfo

            bundle.add(
                self.spec.workdir,
                arcname="workspace",
                filter=exclude_state,
            )
        return SandboxSnapshot(
            snapshot_id=snapshot_id,
            sandbox_id=self.spec.sandbox_id,
            backend=self.backend_name,
            reference=str(archive),
            metadata={"workdir": str(self.spec.workdir)},
        )

    async def restore(self, snapshot: SandboxSnapshot) -> None:
        if snapshot.metadata.get("durable_shared_workspace"):
            if not self.spec.workdir.is_dir():
                raise SandboxUnavailableError(
                    f"Shared sandbox workspace is unavailable: {self.spec.workdir}"
                )
            self._status = SandboxStatus.RUNNING
            return
        archive = Path(snapshot.reference)
        if not archive.is_file():
            raise SandboxUnavailableError(f"Sandbox snapshot not found: {archive}")
        # A shared host workspace is already durable across process restarts.
        # Replacing it could roll back the Runtime's own SQLite/control files.
        # Exact historical restore is intentionally reserved for private
        # workspaces (including private forks).
        if not self.spec.filesystem.private_workspace:
            self._status = SandboxStatus.RUNNING
            return
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                target = (self.spec.workdir.parent / member.name).resolve()
                if self.spec.workdir.parent.resolve() not in target.parents and target != self.spec.workdir.parent.resolve():
                    raise SandboxPolicyError("Snapshot contains a path traversal")
                if member.issym() or member.islnk():
                    link = PurePosixPath(member.linkname)
                    linked = (
                        PurePosixPath(member.name).parent / link
                        if member.issym()
                        else link
                    )
                    if link.is_absolute() or ".." in linked.parts:
                        raise SandboxPolicyError("Snapshot contains an unsafe link")
            temporary = self.state_root / f"restore_{uuid4().hex}"
            temporary.mkdir()
            for member in bundle.getmembers():
                if sys.version_info >= (3, 12):
                    bundle.extract(member, temporary, filter="fully_trusted")
                else:
                    bundle.extract(member, temporary)
        restored = temporary / "workspace"
        preserved = temporary / "preserved"
        preserved.mkdir()
        for name in (".git", ".venv", "node_modules", ".cody"):
            source = self.spec.workdir / name
            if source.exists() or source.is_symlink():
                shutil.move(str(source), preserved / name)
        if self.spec.workdir.exists():
            shutil.rmtree(self.spec.workdir)
        shutil.move(str(restored), self.spec.workdir)
        for source in preserved.iterdir():
            shutil.move(str(source), self.spec.workdir / source.name)
        shutil.rmtree(temporary, ignore_errors=True)

    async def fork(
        self, *, sandbox_id: str | None = None, run_id: str | None = None
    ) -> "SandboxHandle":
        fork_id = sandbox_id or f"sandbox_{uuid4().hex}"
        if self.spec.filesystem.private_workspace:
            fork_workdir = self.state_root.parent / fork_id / "workspace"
            shutil.copytree(self.spec.workdir, fork_workdir)
        else:
            fork_workdir = self.spec.workdir
        return type(self)(replace(
            self.spec,
            sandbox_id=fork_id,
            run_id=run_id or self.spec.run_id,
            workdir=fork_workdir,
        ))

    async def terminate(self) -> None:
        await self._stop_processes()
        self._status = SandboxStatus.TERMINATED

    async def _stop_processes(self) -> None:
        for process in self._processes:
            if process.returncode is None:
                try:
                    process.kill()
                except (ProcessLookupError, OSError):
                    pass
                try:
                    await process.wait()
                except (ProcessLookupError, OSError):
                    pass
        self._processes.clear()


class LocalPolicySandboxBackend(SandboxBackend):
    """Compatibility backend. It is intentionally not an OS security boundary."""

    name = "local-policy"

    async def available(self) -> bool:
        return True

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        return LocalSandboxHandle(spec)


def _seatbelt_quote(value: str) -> str:
    return json.dumps(value)


def seatbelt_profile(spec: SandboxSpec) -> str:
    policy = spec.filesystem
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process*)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow file-read*)",
    ]
    for root in policy.denied_roots:
        lines.append(f"(deny file-read* file-write* (subpath {_seatbelt_quote(str(root))}))")
    for root in policy.write_roots:
        lines.append(f"(allow file-write* (subpath {_seatbelt_quote(str(root))}))")
    if spec.network.mode == NetworkMode.UNRESTRICTED:
        lines.append("(allow network*)")
    elif spec.network.mode in {NetworkMode.ALLOWLIST, NetworkMode.PROXIED}:
        # Seatbelt cannot enforce hostname allowlists itself. Only the configured
        # proxy socket is reachable; the proxy owns domain authorization.
        if not spec.network.proxy_url:
            raise SandboxPolicyError("Seatbelt allowlist/proxied mode requires proxy_url")
        if not spec.network.proxy_url.startswith("unix://"):
            raise SandboxPolicyError(
                "Seatbelt proxied networking requires a unix:// policy proxy"
            )
        lines.append("(allow network-outbound (remote unix-socket))")
    return "\n".join(lines)


class SeatbeltSandboxHandle(LocalSandboxHandle):
    backend_name = "seatbelt"

    def __init__(self, spec: SandboxSpec):
        normalized = spec.normalized()
        state = _state_root(normalized)
        temporary = state / "tmp"
        temporary.mkdir(exist_ok=True)
        effective = replace(
            normalized,
            filesystem=replace(
                normalized.filesystem,
                write_roots=(*normalized.filesystem.write_roots, temporary),
            ),
            env={**normalized.env, "TMPDIR": str(temporary)},
        )
        profile_path = state / "profile.sb"
        profile_path.write_text(seatbelt_profile(effective))
        super().__init__(
            effective, argv_prefix=("sandbox-exec", "-f", str(profile_path))
        )


class SeatbeltSandboxBackend(SandboxBackend):
    name = "seatbelt"

    async def available(self) -> bool:
        return platform.system() == "Darwin" and shutil.which("sandbox-exec") is not None

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        if not await self.available():
            raise SandboxUnavailableError("macOS sandbox-exec is unavailable")
        return SeatbeltSandboxHandle(spec)


def bubblewrap_prefix(spec: SandboxSpec) -> tuple[str, ...]:
    if spec.network.mode in {NetworkMode.ALLOWLIST, NetworkMode.PROXIED} and not spec.network.proxy_url:
        raise SandboxPolicyError("bubblewrap allowlist/proxied mode requires proxy_url")
    if (
        spec.network.mode in {NetworkMode.ALLOWLIST, NetworkMode.PROXIED}
        and spec.network.proxy_url
        and not spec.network.proxy_url.startswith("unix://")
    ):
        raise SandboxPolicyError(
            "bubblewrap proxied networking requires a unix:// policy proxy"
        )
    args = [
        "bwrap", "--die-with-parent", "--new-session", "--unshare-pid",
        "--unshare-uts", "--unshare-ipc", "--ro-bind", "/", "/",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
    ]
    if spec.network.mode != NetworkMode.UNRESTRICTED:
        args.append("--unshare-net")
    for root in spec.filesystem.write_roots:
        args.extend(("--bind", str(root), str(root)))
    for root in spec.filesystem.denied_roots:
        if root.exists() and root.is_dir():
            args.extend(("--tmpfs", str(root)))
        elif root.exists():
            args.extend(("--ro-bind", "/dev/null", str(root)))
    args.extend(("--chdir", str(spec.workdir), "--"))
    return tuple(args)


class BubblewrapSandboxHandle(LocalSandboxHandle):
    backend_name = "bubblewrap"

    def __init__(self, spec: SandboxSpec):
        normalized = spec.normalized()
        effective = replace(normalized, env={**normalized.env, "TMPDIR": "/tmp"})
        super().__init__(effective, argv_prefix=bubblewrap_prefix(effective))


class BubblewrapSandboxBackend(SandboxBackend):
    name = "bubblewrap"

    async def available(self) -> bool:
        return platform.system() == "Linux" and shutil.which("bwrap") is not None

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        if not await self.available():
            raise SandboxUnavailableError("Linux bubblewrap is unavailable")
        return BubblewrapSandboxHandle(spec)

"""Shared subprocess implementation used by local sandbox backends."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from .models import SandboxExecutionRequest, SandboxExecutionResult
from .base import SandboxProcess


_SAFE_HOST_ENV = {
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "PATH",
    "SHELL",
    "TERM",
    "TMPDIR",
    "USER",
    "VIRTUAL_ENV",
    # Container clients need their daemon endpoint/context when the engine is
    # provided by Colima, Docker Desktop, Podman Machine, or a remote socket.
    # These values identify transports and config locations; credential values
    # are still excluded from implicit inheritance.
    "CONTAINER_HOST",
    "DOCKER_CONFIG",
    "DOCKER_CONTEXT",
    "DOCKER_HOST",
}


def _sandbox_env(
    base_env: dict[str, str] | None, request_env: dict[str, str]
) -> dict[str, str]:
    # API keys and other host secrets are never inherited implicitly. Callers
    # must deliberately inject a secret through SandboxSpec/Request policy.
    safe = {key: value for key, value in os.environ.items() if key in _SAFE_HOST_ENV}
    return {**safe, **(base_env or {}), **request_env}


class LocalSandboxProcess(SandboxProcess):
    def __init__(self, process: asyncio.subprocess.Process):
        self.process = process
        self.stdin = process.stdin
        self.stdout = process.stdout
        self.stderr = process.stderr

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    @property
    def pid(self) -> int | None:
        return getattr(self.process, "pid", None)

    async def wait(self) -> int:
        return await self.process.wait()

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        return await self.process.communicate(input)

    def terminate(self) -> None:
        self.process.terminate()

    def kill(self) -> None:
        self.process.kill()


async def spawn_process(
    request: SandboxExecutionRequest,
    *,
    argv_prefix: tuple[str, ...] = (),
    base_env: dict[str, str] | None = None,
    default_cwd: Path,
) -> LocalSandboxProcess:
    argv = (*argv_prefix, *request.argv)
    env = _sandbox_env(base_env, request.env)
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(request.cwd or default_cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return LocalSandboxProcess(process)


async def run_process(
    sandbox_id: str,
    request: SandboxExecutionRequest,
    *,
    argv_prefix: tuple[str, ...] = (),
    base_env: dict[str, str] | None = None,
    default_cwd: Path,
    default_timeout: float | None = None,
) -> SandboxExecutionResult:
    timeout = (
        request.timeout_seconds
        if request.timeout_seconds is not None
        else default_timeout
    )
    started = time.monotonic()
    spawned = await spawn_process(
        request,
        argv_prefix=argv_prefix,
        base_env=base_env,
        default_cwd=default_cwd,
    )
    process = spawned.process
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(
                request.stdin.encode() if request.stdin is not None else None
            ),
            timeout=timeout,
        )
        timed_out = False
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        timed_out = True
    limit = max(0, request.capture_limit)
    stdout = stdout[-limit:] if limit else b""
    stderr = stderr[-limit:] if limit else b""
    returncode = 124 if timed_out else process.returncode
    if returncode is None:
        raise RuntimeError("Sandbox process exited without a return code")
    return SandboxExecutionResult(
        sandbox_id=sandbox_id,
        argv=request.argv,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        returncode=returncode,
        duration_seconds=time.monotonic() - started,
        timed_out=timed_out,
    )

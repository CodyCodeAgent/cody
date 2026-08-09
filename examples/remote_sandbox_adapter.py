"""Implement the provider-neutral Remote Sandbox transport contract offline."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from cody.core.sandbox import (
    FilesystemPolicy,
    RemoteSandboxBackend,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxSpec,
)


class DemoRemoteTransport:
    """Replace these methods with calls to your remote sandbox provider."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def available(self) -> bool:
        return True

    async def create(self, _spec: SandboxSpec) -> str:
        self.calls.append("create")
        return "provider-sandbox-1"

    async def exec(self, _remote_id: str, request: SandboxExecutionRequest):
        self.calls.append("exec")
        return SandboxExecutionResult("remote", request.argv, "remote-ok", "", 0, 0.01)

    async def spawn(self, _remote_id: str, _request: SandboxExecutionRequest):
        self.calls.append("spawn")
        return object()

    async def pause(self, _remote_id: str) -> None:
        self.calls.append("pause")

    async def resume(self, _remote_id: str) -> None:
        self.calls.append("resume")

    async def snapshot(self, _remote_id: str) -> str:
        self.calls.append("snapshot")
        return "provider-snapshot-reference"

    async def restore(self, _remote_id: str, _reference: str) -> None:
        self.calls.append("restore")

    async def fork(self, _remote_id: str, _spec: SandboxSpec) -> str:
        self.calls.append("fork")
        return "provider-sandbox-2"

    async def terminate(self, _remote_id: str) -> None:
        self.calls.append("terminate")


async def run() -> None:
    with TemporaryDirectory(prefix="cody-remote-demo-") as temporary:
        workdir = Path(temporary)
        transport = DemoRemoteTransport()
        backend = RemoteSandboxBackend(transport)
        handle = await backend.create(
            SandboxSpec(
                run_id="demo_remote_sandbox",
                workdir=workdir,
                backend="remote",
                filesystem=FilesystemPolicy(
                    read_roots=(workdir,),
                    write_roots=(workdir,),
                ),
            )
        )
        result = await handle.exec(SandboxExecutionRequest(argv=("echo", "hello")))
        await handle.pause()
        await handle.resume()
        snapshot = await handle.snapshot()
        await handle.restore(snapshot)
        fork = await handle.fork(run_id="demo_remote_fork")
        await handle.terminate()
        await fork.terminate()
        print("result:", result.stdout)
        print("provider calls:", transport.calls)


if __name__ == "__main__":
    asyncio.run(run())

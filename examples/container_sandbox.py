"""Execute a command in a hardened Docker or Podman Sandbox."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cody.core.sandbox import (
    DockerSandboxBackend,
    FilesystemPolicy,
    NetworkMode,
    NetworkPolicy,
    ResourceLimits,
    SandboxExecutionRequest,
    SandboxSpec,
)


async def run(engine: str, image: str, workdir: Path) -> None:
    backend = DockerSandboxBackend(engine)
    if not await backend.available():
        raise SystemExit(f"{engine} is unavailable; start its daemon or machine first")
    handle = await backend.create(
        SandboxSpec(
            run_id=f"demo_{engine}_sandbox",
            workdir=workdir,
            backend=engine,
            image=image,
            filesystem=FilesystemPolicy(
                read_roots=(workdir,),
                write_roots=(workdir,),
            ),
            network=NetworkPolicy(mode=NetworkMode.DISABLED),
            resources=ResourceLimits(
                cpu_count=1,
                memory_mb=256,
                process_limit=64,
                timeout_seconds=20,
            ),
        )
    )
    try:
        result = await handle.exec(
            SandboxExecutionRequest(
                argv=("python", "-c", "print('CONTAINER_SANDBOX_OK')")
            )
        )
        print("returncode:", result.returncode)
        print("stdout:", result.stdout.strip())
    finally:
        await handle.terminate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("docker", "podman"), default="docker")
    parser.add_argument("--image", default="python:3.13-slim")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    asyncio.run(run(args.engine, args.image, args.workdir.resolve()))


if __name__ == "__main__":
    main()

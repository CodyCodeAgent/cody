"""Exercise Sandbox exec, secret filtering, snapshot, restore, and lifecycle."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from cody.core.sandbox import (
    FilesystemPolicy,
    LocalPolicySandboxBackend,
    NetworkMode,
    NetworkPolicy,
    SandboxExecutionRequest,
    SandboxSpec,
)


async def run() -> None:
    with TemporaryDirectory(prefix="cody-sandbox-demo-") as temporary:
        workdir = Path(temporary) / "workspace"
        workdir.mkdir()
        os.environ["CODY_DEMO_SECRET"] = "must-not-reach-guest"
        spec = SandboxSpec(
            run_id="demo_sandbox",
            workdir=workdir,
            backend="local-policy",
            filesystem=FilesystemPolicy(
                read_roots=(workdir,),
                write_roots=(workdir,),
                private_workspace=True,
            ),
            network=NetworkPolicy(mode=NetworkMode.DISABLED),
            metadata={"state_root": str(Path(temporary) / "state")},
        )
        handle = await LocalPolicySandboxBackend().create(spec)
        try:
            result = await handle.exec(
                SandboxExecutionRequest(
                    argv=(
                        sys.executable,
                        "-c",
                        "import os; print(os.getenv('CODY_DEMO_SECRET', 'filtered'))",
                    )
                )
            )
            print("guest secret value:", result.stdout.strip())

            value = workdir / "value.txt"
            value.write_text("before", encoding="utf-8")
            snapshot = await handle.snapshot()
            value.write_text("after", encoding="utf-8")
            await handle.restore(snapshot)
            print("restored value:", value.read_text(encoding="utf-8"))
        finally:
            await handle.terminate()
            os.environ.pop("CODY_DEMO_SECRET", None)
        print("sandbox status:", handle.status.value)


if __name__ == "__main__":
    asyncio.run(run())

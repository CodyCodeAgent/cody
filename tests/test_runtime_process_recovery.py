import os
from pathlib import Path
import subprocess
import sys

import pytest

from cody.core.runtime import (
    CodyRuntime,
    RunEventType,
    RunStatus,
    RuntimeStoreBundle,
)


@pytest.mark.asyncio
async def test_process_crash_recovers_from_last_committed_batch(tmp_path):
    runtime_root = tmp_path / "crash-runtime"
    repository_root = Path(__file__).resolve().parents[1]
    child = r'''
import asyncio
import os
import sys
from cody.core.runtime import CodyRuntime, RuntimeStoreBundle, Workflow, WorkflowNodeType

async def main():
    stores = RuntimeStoreBundle.sqlite(sys.argv[1])
    workflow = (
        Workflow("crash", workflow_id="workflow_process_crash")
        .node("committed", WorkflowNodeType.FUNCTION)
        .node("crash", WorkflowNodeType.FUNCTION)
        .edge("committed", "crash")
        .compile()
    )
    def handler(_state, node):
        if node.node_id == "crash":
            os._exit(23)
        return {"committed": True}
    runtime = CodyRuntime(
        object(), stores=stores, node_handlers={"function": handler}, poll_interval=0
    )
    handle = await runtime.start(workflow, {"task": "survive"}, run_id="run_crash")
    await handle.result()

asyncio.run(main())
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(repository_root)

    crashed = subprocess.run(
        [sys.executable, "-c", child, str(runtime_root)],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert crashed.returncode == 23
    stores = RuntimeStoreBundle.sqlite(runtime_root)
    orphan = stores.run_store.get_run("run_crash")
    assert orphan is not None
    assert orphan.status == RunStatus.RUNNING

    executed = []

    def recover_handler(_state, node):
        executed.append(node.node_id)
        return {"recovered": True}

    runtime = CodyRuntime(
        object(),
        stores=stores,
        node_handlers={"function": recover_handler},
        poll_interval=0,
    )
    recovered = await runtime.recover("run_crash")
    result = await recovered.result()

    assert result.run.status == RunStatus.COMPLETED
    assert result.state.data["committed"] is True
    assert result.state.data["recovered"] is True
    assert executed == ["crash"]
    event_types = [
        event.event_type for event in stores.trace_store.list_events("run_crash")
    ]
    assert RunEventType.RUN_RECOVERING in event_types
    assert event_types[-1] == RunEventType.RUN_COMPLETED

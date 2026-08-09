import asyncio
import json

from click.testing import CliRunner
import pytest

from cody.cli.main import main
from cody.sdk.client import AsyncCodyClient
from cody.core.runtime import (
    ApprovalRequestRecord,
    ArtifactRecord,
    ArtifactType,
    CheckpointRecord,
    CodyRuntime,
    RunEvent,
    RunEventType,
    RunRecord,
    RunStatus,
    RuntimeStoreBundle,
    StepRecord,
    StepType,
    Workflow,
    WorkflowCancelled,
    WorkflowNodeType,
    runtime_root_for_workdir,
)


def seed_runtime(workdir, runtime_home):
    stores = RuntimeStoreBundle.for_workdir(workdir, base_dir=runtime_home)
    run = stores.run_store.save_run(
        RunRecord(
            task="shared surface",
            run_id="run_shared_surface",
            status=RunStatus.COMPLETED,
            workdir=str(workdir),
        )
    )
    stores.run_store.save_step(
        StepRecord(
            run_id=run.run_id,
            step_id="step_shared",
            step_type=StepType.SYSTEM,
        ).start().complete()
    )
    event = stores.trace_store.append(
        RunEvent(
            RunEventType.RUN_COMPLETED,
            run_id=run.run_id,
            step_id="step_shared",
            payload={"output": "done"},
        )
    )
    checkpoint = stores.checkpoint_store.save(
        CheckpointRecord(
            run_id=run.run_id,
            step_id="step_shared",
            workflow_state={"workflow_id": "shared", "run_id": run.run_id},
            metadata={"runtime_event_id": event.event_id},
        )
    )
    artifact = stores.artifact_store.save(
        ArtifactRecord(
            run_id=run.run_id,
            step_id="step_shared",
            checkpoint_id=checkpoint.checkpoint_id,
            event_id=event.event_id,
            artifact_type=ArtifactType.GENERIC,
            content={"result": "done"},
        )
    )
    approval = stores.approval_store.save(
        ApprovalRequestRecord(
            run_id=run.run_id,
            node_id="approval",
            request={"action": "ship"},
        )
    )
    return stores, run, checkpoint, artifact, approval


def test_runtime_root_is_stable_per_resolved_workdir(tmp_path):
    base = tmp_path / "runtime-home"
    project = tmp_path / "project"
    project.mkdir()

    first = runtime_root_for_workdir(project, base_dir=base)
    second = runtime_root_for_workdir(project / ".", base_dir=base)
    other = runtime_root_for_workdir(tmp_path, base_dir=base)

    assert first == second
    assert first != other
    assert first.parent == base


def test_runtime_interface_exposes_linked_run_state(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    stores, run, checkpoint, artifact, _ = seed_runtime(
        project,
        tmp_path / "runtime-home",
    )
    interface = stores.interface()

    assert interface.get_run(run.run_id).data["run"]["status"] == "completed"
    assert interface.list_steps(run.run_id).data["steps"][0]["step_id"] == "step_shared"
    assert (
        interface.list_checkpoints(run.run_id).data["checkpoints"][0]["checkpoint_id"]
        == checkpoint.checkpoint_id
    )
    assert interface.get_artifact(artifact.artifact_id).data["artifact"]["event_id"]
    assert interface.list_runs(limit=1).data["total"] == 1


def test_cli_runtime_commands_read_and_decide_shared_durable_state(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    runtime_home = tmp_path / "runtime-home"
    monkeypatch.setenv("CODY_RUNTIME_HOME", str(runtime_home))
    _, run, _, artifact, approval = seed_runtime(project, runtime_home)
    runner = CliRunner()

    listed = runner.invoke(
        main,
        ["runs", "list", "--workdir", str(project), "--json"],
    )
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["runs"][0]["run_id"] == run.run_id

    shown = runner.invoke(
        main,
        ["runs", "show", run.run_id, "--workdir", str(project), "--json"],
    )
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["steps"][0]["step_id"] == "step_shared"

    artifact_result = runner.invoke(
        main,
        [
            "artifacts",
            "show",
            artifact.artifact_id,
            "--workdir",
            str(project),
            "--json",
        ],
    )
    assert artifact_result.exit_code == 0, artifact_result.output
    assert json.loads(artifact_result.output)["artifact"]["content"] == {"result": "done"}

    approved = runner.invoke(
        main,
        ["approvals", "approve", approval.approval_id, "--workdir", str(project)],
    )
    assert approved.exit_code == 0, approved.output
    reopened = RuntimeStoreBundle.for_workdir(project)
    assert reopened.approval_store.get(approval.approval_id).status.value == "approved"


@pytest.mark.asyncio
async def test_control_request_from_reopened_bundle_cancels_active_runtime(tmp_path):
    class UnusedRunner:
        pass

    root = tmp_path / "shared-control"
    owner_stores = RuntimeStoreBundle.sqlite(root)
    controller_stores = RuntimeStoreBundle.sqlite(root)
    started = asyncio.Event()
    handler_cancelled = asyncio.Event()

    async def blocking(_state, _node):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            handler_cancelled.set()
            raise

    workflow = (
        Workflow("external-cancel", workflow_id="workflow_external_cancel")
        .node("block", WorkflowNodeType.FUNCTION)
        .compile()
    )
    runtime = CodyRuntime(
        UnusedRunner(),
        stores=owner_stores,
        node_handlers={"function": blocking},
    )
    run = await runtime.start(workflow, run_id="run_external_cancel")
    await asyncio.wait_for(started.wait(), timeout=0.2)

    response = controller_stores.interface().request_cancel(run.run_id)
    assert response.ok
    with pytest.raises(WorkflowCancelled):
        await asyncio.wait_for(run.result(), timeout=0.5)

    assert handler_cancelled.is_set()
    assert run.record.status == RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_new_runtime_recovers_run_orphaned_by_process_termination(tmp_path):
    class UnusedRunner:
        pass

    root = tmp_path / "recovery"
    started = asyncio.Event()

    async def interrupted(_state, _node):
        started.set()
        await asyncio.Event().wait()

    workflow = (
        Workflow("recover", workflow_id="workflow_process_recover")
        .node("work", WorkflowNodeType.FUNCTION)
        .compile()
    )
    first = CodyRuntime(
        UnusedRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": interrupted},
    )
    orphan = await first.start(workflow, run_id="run_process_recover")
    await asyncio.wait_for(started.wait(), timeout=0.2)
    orphan._execution.cancel()
    await asyncio.gather(orphan._execution, return_exceptions=True)
    assert orphan.record.status == RunStatus.RUNNING

    second = CodyRuntime(
        UnusedRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": lambda _state, _node: {"recovered": True}},
    )
    recovered = await second.recover(orphan.run_id)
    result = await recovered.result()

    assert result.run.status == RunStatus.COMPLETED
    assert result.state.data["recovered"] is True
    event_types = [
        event.event_type
        for event in second.stores.trace_store.list_events(orphan.run_id)
    ]
    assert RunEventType.RUN_RECOVERING in event_types


@pytest.mark.asyncio
async def test_sdk_client_exposes_cached_canonical_runtime(tmp_path, monkeypatch):
    class FakeRunner:
        def __init__(self):
            self._trace_store = None
            self._checkpoint_store = None
            self.stopped = []

        async def stop_mcp(self):
            self.stopped.append("mcp")

        async def stop_lsp(self):
            self.stopped.append("lsp")

    monkeypatch.setenv("CODY_RUNTIME_HOME", str(tmp_path / "runtime-home"))
    client = AsyncCodyClient(workdir=str(tmp_path))
    fake = FakeRunner()
    client._runner = fake

    runtime = client.get_runtime()

    assert client.get_runtime() is runtime
    assert runtime.runner is fake
    assert runtime.stores.control_store is not None
    assert fake._trace_store is runtime.stores.trace_store
    await client.close()
    assert fake.stopped == ["mcp", "lsp"]

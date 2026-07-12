"""High-level canonical runtime service and live run handle."""

from __future__ import annotations

import asyncio
import inspect
import json
from hashlib import sha256
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

from ..prompt import ImageData, MultimodalPrompt, Prompt, prompt_images, prompt_text
from ..sandbox import (
    FilesystemPolicy,
    SandboxHandle,
    SandboxManager,
    SandboxSnapshot,
    SandboxSpec,
    sandbox_spec_from_config,
)
from .adapters import queued_human_approval_node_handler
from .async_coordinator import (
    AsyncMultiAgentCoordinator,
    async_multi_agent_node_handler,
)
from .async_quality import AsyncEvaluator, AsyncQualityGateRunner, async_quality_gate_node_handler
from .artifact import ArtifactRecord, ArtifactType
from .approval import ApprovalRequestRecord, ApprovalStatus
from .bridge import stream_event_to_run_event
from .checkpoint import CheckpointRecord
from .control import WorkflowCancelled, WorkflowPaused, WorkflowWaiting
from .environment import RuntimeStoreBundle
from .events import RunEvent, RunEventType
from .extensions import RuntimeExtensionRegistry
from .manager import WorkflowRunManager
from .models import RunRecord, RunStatus
from .tools import (
    ToolPolicy,
    ToolRegistry,
    idempotent_registry_tool_node_handler,
)
from .workflow import CompiledWorkflow, Workflow, WorkflowNode, WorkflowNodeType, WorkflowState
from ..interaction import InteractionResponse


@dataclass(frozen=True)
class RuntimeRunResult:
    """Structured terminal result returned by a canonical runtime run."""

    run: RunRecord
    state: WorkflowState
    output: str
    artifact_ids: tuple[str, ...] = ()
    session_id: str | None = None
    model_result: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": self.run.to_dict(),
            "state": self.state.to_dict(),
            "output": self.output,
            "artifact_ids": list(self.artifact_ids),
            "session_id": self.session_id,
        }


@dataclass(frozen=True)
class RuntimeRunContext:
    """Governance identity and tenancy attached to a Run."""

    actor_id: str | None = None
    service_account_id: str | None = None
    project_id: str | None = None
    permissions: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RuntimeBudget:
    """Run-level limits; node timeout/retry budgets remain workflow metadata."""

    max_steps: int = 100
    max_duration_seconds: float | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None


@dataclass
class _RunExecutionOptions:
    """Transient execution context for a live single-agent runtime run."""

    prompt: Prompt
    message_history: Any = None
    session_store: Any = None
    session_id: str | None = None
    include_tools: list[str] | None = None
    exclude_tools: list[str] | None = None
    model_result: Any = None
    session_saved: bool = False
    legacy_session_runner: bool = False
    budget: RuntimeBudget | None = None
    sandbox: SandboxHandle | None = None


class RuntimeRun:
    """Live handle for observing and controlling one in-process run."""

    def __init__(
        self,
        *,
        run_id: str,
        manager: WorkflowRunManager,
        stores: RuntimeStoreBundle,
        execution: "asyncio.Task[RuntimeRunResult]",
        cancel_event: asyncio.Event,
        poll_interval: float,
        sandbox: SandboxHandle,
    ):
        self.run_id = run_id
        self._manager = manager
        self._stores = stores
        self._execution = execution
        self._cancel_event = cancel_event
        self._poll_interval = poll_interval
        self.sandbox = sandbox

    async def events(self, *, from_index: int = 0) -> AsyncIterator[RunEvent]:
        """Yield the persisted canonical event stream in append order."""

        index = max(0, from_index)
        while True:
            events = self._stores.trace_store.list_events(self.run_id)
            while index < len(events):
                yield events[index]
                index += 1
            if self._execution.done():
                # Read once more so events appended immediately before task
                # completion cannot be missed by the observer.
                final_events = self._stores.trace_store.list_events(self.run_id)
                if index >= len(final_events):
                    break
                continue
            await asyncio.sleep(self._poll_interval)

    async def result(self) -> RuntimeRunResult:
        """Wait for and return the structured terminal result."""

        return await self._execution

    def cancel(self) -> None:
        """Request cooperative cancellation at model and workflow boundaries."""

        self._cancel_event.set()
        self._manager.request_cancel(self.run_id)

    def pause(self, *, before_node_id: str | None = None) -> None:
        """Request a durable pause at the next safe workflow boundary."""

        self._manager.request_pause(self.run_id, before_node_id=before_node_id)

    @property
    def record(self) -> RunRecord | None:
        return self._stores.run_store.get_run(self.run_id)

    @property
    def done(self) -> bool:
        return self._execution.done()

    def follow(self, resumed: "RuntimeRun") -> None:
        """Continue this live handle with a resumed execution of the same Run.

        Observers such as the SDK stream can stay attached while a durable
        human-input wait is approved and resumed in-process. The canonical
        event cursor remains valid because both handles share the same stores
        and ``run_id``.
        """

        if resumed.run_id != self.run_id:
            raise ValueError(
                f"Cannot follow a different run: {self.run_id} != {resumed.run_id}"
            )
        self._execution = resumed._execution
        self._cancel_event = resumed._cancel_event
        self.sandbox = resumed.sandbox


class CodyRuntime:
    """Canonical application runtime for AgentRunner-backed workflows.

    The runtime owns the Run lifecycle and durable stores.  ``AgentRunner`` is
    treated as an executor for agent workflow nodes, while its legacy stream is
    retained only as an input compatibility surface for canonical ``RunEvent``
    recording.
    """

    def __init__(
        self,
        runner: Any,
        *,
        stores: RuntimeStoreBundle | None = None,
        node_handlers: dict[str, Any] | None = None,
        condition_handlers: dict[str, Any] | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_policy: ToolPolicy | None = None,
        multi_agent_coordinator: AsyncMultiAgentCoordinator | None = None,
        quality_evaluators: dict[str, AsyncEvaluator] | None = None,
        extensions: RuntimeExtensionRegistry | None = None,
        sandbox_manager: SandboxManager | None = None,
        max_concurrency: int = 8,
        default_node_timeout: float | None = None,
        poll_interval: float = 0.01,
    ):
        self.runner = runner
        self.stores = stores or RuntimeStoreBundle.in_memory()
        self.extensions = extensions or RuntimeExtensionRegistry()
        self.sandbox_manager = sandbox_manager or SandboxManager()
        self.node_handlers = {
            **self.extensions.workflow_node_handlers(),
            **dict(node_handlers or {}),
        }
        self.condition_handlers = dict(condition_handlers or {})
        self.tool_registry = tool_registry
        self.tool_policy = tool_policy
        self.multi_agent_coordinator = multi_agent_coordinator
        self.quality_evaluators = dict(quality_evaluators or {})
        self.max_concurrency = max_concurrency
        self.default_node_timeout = default_node_timeout
        self.poll_interval = poll_interval
        self._runs: dict[str, RuntimeRun] = {}
        self._execution_options: dict[str, _RunExecutionOptions] = {}
        self._sandboxes: dict[str, SandboxHandle] = {}
        self._bind_runner_stores()

    async def __aenter__(self) -> "CodyRuntime":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Cancel active runs and close runner-owned external resources."""

        active = [run for run in self._runs.values() if not run.done]
        for run in active:
            run.cancel()
        if active:
            await asyncio.gather(*(run.result() for run in active), return_exceptions=True)
        stop_mcp = getattr(self.runner, "stop_mcp", None)
        if stop_mcp is not None:
            stopped = stop_mcp()
            if inspect.isawaitable(stopped):
                await stopped
        stop_lsp = getattr(self.runner, "stop_lsp", None)
        if stop_lsp is not None:
            stopped = stop_lsp()
            if inspect.isawaitable(stopped):
                await stopped

    @classmethod
    def from_config(
        cls,
        config: Any,
        workdir: str | Path,
        *,
        stores: RuntimeStoreBundle | None = None,
        node_handlers: dict[str, Any] | None = None,
        condition_handlers: dict[str, Any] | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_policy: ToolPolicy | None = None,
        multi_agent_coordinator: AsyncMultiAgentCoordinator | None = None,
        quality_evaluators: dict[str, AsyncEvaluator] | None = None,
        extensions: RuntimeExtensionRegistry | None = None,
        sandbox_manager: SandboxManager | None = None,
        max_concurrency: int = 8,
        default_node_timeout: float | None = None,
        poll_interval: float = 0.01,
        **runner_kwargs: Any,
    ) -> "CodyRuntime":
        """Create a runtime and an AgentRunner sharing the canonical stores."""

        from ..runner import AgentRunner

        bundle = stores or RuntimeStoreBundle.in_memory()
        runner = AgentRunner(
            config=config,
            workdir=Path(workdir),
            trace_store=bundle.trace_store,
            checkpoint_store=bundle.checkpoint_store,
            **runner_kwargs,
        )
        return cls(
            runner,
            stores=bundle,
            node_handlers=node_handlers,
            condition_handlers=condition_handlers,
            tool_registry=tool_registry,
            tool_policy=tool_policy,
            multi_agent_coordinator=multi_agent_coordinator,
            quality_evaluators=quality_evaluators,
            extensions=extensions,
            sandbox_manager=sandbox_manager,
            max_concurrency=max_concurrency,
            default_node_timeout=default_node_timeout,
            poll_interval=poll_interval,
        )

    async def start(
        self,
        workflow: CompiledWorkflow | Workflow | Prompt,
        input: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        max_steps: int = 100,
        session_store: Any = None,
        session_id: str | None = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        cancel_event: asyncio.Event | None = None,
        context: RuntimeRunContext | None = None,
        budget: RuntimeBudget | None = None,
    ) -> RuntimeRun:
        """Start a workflow or a single-agent task and return a live handle."""

        compiled, initial_data = self._prepare_workflow(workflow, input)
        runtime_run_id = run_id or f"run_{uuid4().hex}"
        run_context = context or RuntimeRunContext()
        run_budget = budget or RuntimeBudget(max_steps=max_steps)
        max_steps = min(max_steps, run_budget.max_steps)
        task_text = str(initial_data.get("task") or compiled.name)
        effective_cancel_event = cancel_event or asyncio.Event()
        effective_session_id = session_id
        sandbox = await self._create_sandbox(runtime_run_id)
        self._sandboxes[runtime_run_id] = sandbox
        bind_sandbox = getattr(self.runner, "bind_sandbox", None)
        if bind_sandbox is not None:
            bound = bind_sandbox(sandbox)
            if inspect.isawaitable(bound):
                await bound
        if isinstance(workflow, (str, MultimodalPrompt)):
            history = None
            legacy_session_runner = not inspect.isasyncgenfunction(
                getattr(self.runner, "run_events", None)
            )
            if session_store is not None:
                prepared = self.runner.prepare_session(session_store, session_id)
                if isinstance(prepared, tuple) and len(prepared) == 2:
                    effective_session_id, history = prepared
                else:
                    # Compatibility for injected runner-like SDK test doubles and
                    # third-party adapters that only implement the old session API.
                    legacy_session_runner = True
            self._execution_options[runtime_run_id] = _RunExecutionOptions(
                prompt=workflow,
                message_history=history,
                session_store=session_store,
                session_id=effective_session_id,
                include_tools=include_tools,
                exclude_tools=exclude_tools,
                legacy_session_runner=legacy_session_runner,
                budget=run_budget,
                sandbox=sandbox,
            )
            if isinstance(workflow, MultimodalPrompt):
                prompt_artifact = self.stores.artifact_store.save(
                    ArtifactRecord(
                        run_id=runtime_run_id,
                        artifact_type=ArtifactType.CONTEXT_PACK,
                        name="runtime-prompt.json",
                        content={
                            "text": workflow.text,
                            "images": [image.to_dict() for image in workflow.images],
                        },
                        metadata={"kind": "runtime_prompt", "recoverable": True},
                    )
                )
                initial_data["prompt_artifact_id"] = prompt_artifact.artifact_id
        manager = self._build_manager(effective_cancel_event, sandbox=sandbox)
        manager.clear_pause(runtime_run_id)
        manager.clear_cancel(runtime_run_id)

        self.stores.run_store.save_run(
            RunRecord(
                task=task_text,
                run_id=runtime_run_id,
                status=RunStatus.CREATED,
                workflow_id=compiled.workflow_id,
                session_id=effective_session_id,
                project_id=run_context.project_id,
                workdir=str(getattr(self.runner, "workdir", "")) or None,
                metadata={
                    "workflow_name": compiled.name,
                    "workflow_definition": compiled.to_dict(),
                    "actor_id": run_context.actor_id,
                    "service_account_id": run_context.service_account_id,
                    "permissions": run_context.permissions or {},
                    "budget": {
                        "max_steps": max_steps,
                        "max_duration_seconds": run_budget.max_duration_seconds,
                        "max_tokens": run_budget.max_tokens,
                        "max_cost_usd": run_budget.max_cost_usd,
                    },
                    "model": str(getattr(getattr(self.runner, "config", None), "model", "")),
                    "sandbox": {
                        "sandbox_id": sandbox.spec.sandbox_id,
                        "backend": sandbox.backend_name,
                        "status": sandbox.status.value,
                    },
                    **(run_context.metadata or {}),
                },
            )
        )
        self.stores.trace_store.append(
            RunEvent(
                RunEventType.RUN_STARTED,
                run_id=runtime_run_id,
                step_id="run_start",
                payload={"task": task_text, "workflow_id": compiled.workflow_id},
            )
        )
        self._append_sandbox_event(
            RunEventType.SANDBOX_CREATED,
            runtime_run_id,
            sandbox,
        )
        self._append_sandbox_event(
            RunEventType.SANDBOX_STARTED,
            runtime_run_id,
            sandbox,
        )
        if effective_session_id is not None:
            self.stores.trace_store.append(
                RunEvent(
                    RunEventType.SESSION_STARTED,
                    run_id=runtime_run_id,
                    step_id="session_start",
                    payload={"session_id": effective_session_id},
                )
            )
        execution_coro = self._execute_managed(
            sandbox,
            self._execute(
                manager,
                compiled,
                runtime_run_id,
                initial_data,
                max_steps=max_steps,
                checkpoint_id=None,
            ),
        )
        if run_budget.max_duration_seconds is not None:
            execution_coro = self._execute_with_deadline(
                execution_coro,
                runtime_run_id,
                run_budget.max_duration_seconds,
            )
        execution = asyncio.create_task(
            execution_coro,
            name=f"cody-runtime-{runtime_run_id}",
        )
        handle = RuntimeRun(
            run_id=runtime_run_id,
            manager=manager,
            stores=self.stores,
            execution=execution,
            cancel_event=effective_cancel_event,
            poll_interval=self.poll_interval,
            sandbox=sandbox,
        )
        self._runs[runtime_run_id] = handle
        return handle

    async def _execute_with_deadline(
        self,
        execution,
        run_id: str,
        timeout: float,
    ) -> RuntimeRunResult:
        try:
            return await asyncio.wait_for(execution, timeout=timeout)
        except asyncio.TimeoutError:
            record = self.stores.run_store.get_run(run_id)
            if record is not None:
                self.stores.run_store.save_run(
                    record.transition(RunStatus.FAILED, completed=True)
                )
            self._append_terminal(
                RunEventType.RUN_FAILED,
                run_id,
                {"error": f"Run exceeded {timeout}s duration budget", "budget_exceeded": True},
            )
            raise

    async def _create_sandbox(
        self,
        run_id: str,
        *,
        sandbox_id: str | None = None,
    ) -> SandboxHandle:
        config = getattr(self.runner, "config", None)
        workdir = Path(getattr(self.runner, "workdir", Path.cwd())).resolve()
        sandbox_config = getattr(config, "sandbox", None)
        has_concrete_sandbox_config = (
            isinstance(getattr(sandbox_config, "enabled", None), bool)
            and isinstance(getattr(sandbox_config, "backend", None), str)
            and isinstance(getattr(sandbox_config, "network_mode", None), str)
        )
        if config is not None and has_concrete_sandbox_config:
            spec = sandbox_spec_from_config(
                config,
                run_id=run_id,
                workdir=workdir,
                sandbox_id=sandbox_id,
            )
        else:
            spec = SandboxSpec(
                run_id=run_id,
                workdir=workdir,
                sandbox_id=sandbox_id or f"sandbox_{uuid4().hex}",
                backend="local-policy",
                filesystem=FilesystemPolicy(
                    read_roots=(workdir,), write_roots=(workdir,)
                ),
            )
        return await self.sandbox_manager.create(spec)

    def _append_sandbox_event(
        self,
        event_type: RunEventType,
        run_id: str,
        sandbox: SandboxHandle,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.stores.trace_store.append(
            RunEvent(
                event_type,
                run_id=run_id,
                step_id=f"sandbox_{event_type.value.rsplit('.', 1)[-1]}",
                payload={
                    "sandbox_id": sandbox.spec.sandbox_id,
                    "backend": sandbox.backend_name,
                    "status": sandbox.status.value,
                    **(payload or {}),
                },
            )
        )

    async def _execute_managed(self, sandbox: SandboxHandle, execution) -> RuntimeRunResult:
        run_id = sandbox.spec.run_id
        try:
            result = await execution
        except WorkflowWaiting as exc:
            await self._snapshot_and_pause(run_id, sandbox)
            self._append_terminal(
                RunEventType.RUN_WAITING, run_id, {"reason": str(exc)}
            )
            raise
        except WorkflowPaused as exc:
            await self._snapshot_and_pause(run_id, sandbox)
            self._append_terminal(
                RunEventType.RUN_PAUSED, run_id, {"reason": str(exc)}
            )
            raise
        except WorkflowCancelled as exc:
            await sandbox.terminate()
            self._append_sandbox_event(
                RunEventType.SANDBOX_TERMINATED, run_id, sandbox
            )
            self._append_terminal(
                RunEventType.RUN_CANCELLED, run_id, {"reason": str(exc)}
            )
            raise
        except asyncio.CancelledError:
            await sandbox.terminate()
            self._append_sandbox_event(
                RunEventType.SANDBOX_TERMINATED, run_id, sandbox
            )
            raise
        except BaseException as exc:
            try:
                await sandbox.terminate()
                self._append_sandbox_event(
                    RunEventType.SANDBOX_TERMINATED, run_id, sandbox
                )
            except Exception as sandbox_error:
                self._append_sandbox_event(
                    RunEventType.SANDBOX_FAILED,
                    run_id,
                    sandbox,
                    {"error": str(sandbox_error)},
                )
            self._append_terminal(
                RunEventType.RUN_FAILED, run_id, {"error": str(exc)}
            )
            raise
        try:
            await sandbox.terminate()
            self._append_sandbox_event(
                RunEventType.SANDBOX_TERMINATED, run_id, sandbox
            )
        except Exception as sandbox_error:
            self._append_sandbox_event(
                RunEventType.SANDBOX_FAILED,
                run_id,
                sandbox,
                {"error": str(sandbox_error), "phase": "termination"},
            )
        self._append_completed(result)
        return result

    def _append_completed(self, result: RuntimeRunResult) -> None:
        model_result = result.model_result
        usage_reader = getattr(model_result, "usage", None)
        raw_usage = usage_reader() if callable(usage_reader) else None
        usage = {
            "input_tokens": int(getattr(raw_usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(raw_usage, "output_tokens", 0) or 0),
            "total_tokens": int(getattr(raw_usage, "total_tokens", 0) or 0),
        }
        if not usage["total_tokens"]:
            usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
        self._append_terminal(
            RunEventType.RUN_COMPLETED,
            result.run.run_id,
            {
                "output": result.output,
                "artifact_ids": list(result.artifact_ids),
                "session_id": result.session_id,
                "usage": usage,
            },
        )

    async def _snapshot_and_pause(
        self, run_id: str, sandbox: SandboxHandle
    ) -> SandboxSnapshot:
        snapshot = await sandbox.snapshot()
        artifact = self.stores.artifact_store.save(
            ArtifactRecord(
                run_id=run_id,
                artifact_type=ArtifactType.SANDBOX_SNAPSHOT,
                name=f"sandbox-snapshot:{snapshot.snapshot_id}",
                content=snapshot.to_dict(),
                metadata={
                    "kind": "sandbox_snapshot",
                    "sandbox_id": sandbox.spec.sandbox_id,
                    "backend": sandbox.backend_name,
                },
            )
        )
        latest = self.stores.checkpoint_store.latest(run_id)
        if latest is not None:
            self.stores.checkpoint_store.save(
                replace(
                    latest,
                    checkpoint_id=f"ckpt_{uuid4().hex}",
                    parent_checkpoint_id=latest.checkpoint_id,
                    step_id=f"sandbox_snapshot_{snapshot.snapshot_id}",
                    artifact_refs=[*latest.artifact_refs, artifact.artifact_id],
                    metadata={
                        **latest.metadata,
                        "sandbox_snapshot_artifact_id": artifact.artifact_id,
                    },
                )
            )
        self._append_sandbox_event(
            RunEventType.SANDBOX_SNAPSHOT_CREATED,
            run_id,
            sandbox,
            {
                "snapshot_id": snapshot.snapshot_id,
                "artifact_id": artifact.artifact_id,
            },
        )
        await sandbox.pause()
        self._append_sandbox_event(RunEventType.SANDBOX_PAUSED, run_id, sandbox)
        return snapshot

    async def resume(
        self,
        run_id: str,
        workflow: CompiledWorkflow | Workflow | None = None,
        *,
        max_steps: int = 100,
    ) -> RuntimeRun:
        """Resume a waiting/paused run from its latest durable checkpoint."""

        record = self.stores.run_store.get_run(run_id)
        if record is None:
            raise KeyError(f"Runtime run not found: {run_id}")
        if record.status not in {RunStatus.WAITING, RunStatus.PAUSED}:
            raise ValueError(
                f"Run must be waiting or paused to resume: {run_id} ({record.status.value})"
            )
        return await self._restart(
            run_id,
            workflow,
            event_type=RunEventType.RUN_RESUMED,
            max_steps=max_steps,
        )

    async def retry(
        self,
        run_id: str,
        workflow: CompiledWorkflow | Workflow | None = None,
        *,
        checkpoint_id: str | None = None,
        max_steps: int = 100,
    ) -> RuntimeRun:
        """Retry a failed/cancelled run from a durable checkpoint."""

        record = self.stores.run_store.get_run(run_id)
        if record is None:
            raise KeyError(f"Runtime run not found: {run_id}")
        if record.status not in {RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ValueError(
                f"Run must be failed or cancelled to retry: {run_id} ({record.status.value})"
            )
        return await self._restart(
            run_id,
            workflow,
            event_type=RunEventType.RUN_RETRYING,
            checkpoint_id=checkpoint_id,
            max_steps=max_steps,
        )

    async def recover(
        self,
        run_id: str,
        workflow: CompiledWorkflow | Workflow | None = None,
        *,
        max_steps: int = 100,
    ) -> RuntimeRun:
        """Recover an orphaned running Run after process/service restart."""

        record = self.stores.run_store.get_run(run_id)
        if record is None:
            raise KeyError(f"Runtime run not found: {run_id}")
        if record.status != RunStatus.RUNNING:
            raise ValueError(
                f"Only an orphaned running Run can recover: {run_id} "
                f"({record.status.value})"
            )
        return await self._restart(
            run_id,
            workflow,
            event_type=RunEventType.RUN_RECOVERING,
            max_steps=max_steps,
        )

    async def fork(
        self,
        checkpoint_id: str,
        *,
        new_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        max_steps: int = 100,
    ) -> RuntimeRun:
        """Fork a new run from any historical checkpoint and start it."""

        # Forking only manipulates durable workflow state here. The executable
        # sandbox is created and restored by ``_restart`` below.
        manager = self._build_manager(asyncio.Event(), sandbox=None)
        checkpoint = manager.fork_from_checkpoint(
            checkpoint_id,
            new_run_id=new_run_id,
            metadata=metadata,
        )
        parent_run_id = checkpoint.metadata.get("forked_from_run_id")
        source_sandbox = self._sandboxes.get(str(parent_run_id))
        fork_sandbox = None
        if source_sandbox is not None:
            fork_sandbox = await source_sandbox.fork(run_id=checkpoint.run_id)
        return await self._restart(
            checkpoint.run_id,
            None,
            event_type=RunEventType.RUN_FORKED,
            checkpoint_id=checkpoint.checkpoint_id,
            max_steps=max_steps,
            event_payload={
                "parent_run_id": checkpoint.metadata.get("forked_from_run_id"),
                "parent_checkpoint_id": checkpoint.parent_checkpoint_id,
            },
            sandbox_override=fork_sandbox,
        )

    def approve(
        self,
        approval_id: str,
        response: dict[str, Any] | None = None,
    ) -> None:
        """Persist an approval decision for a waiting workflow node."""

        self.stores.approval_store.approve(approval_id, response=response)

    async def _restart(
        self,
        run_id: str,
        workflow: CompiledWorkflow | Workflow | None,
        *,
        event_type: RunEventType,
        checkpoint_id: str | None = None,
        max_steps: int,
        event_payload: dict[str, Any] | None = None,
        sandbox_override: SandboxHandle | None = None,
    ) -> RuntimeRun:
        record = self.stores.run_store.get_run(run_id)
        if record is None:
            raise KeyError(f"Runtime run not found: {run_id}")
        compiled = self._workflow_for_run(record, workflow)
        cancel_event = asyncio.Event()
        sandbox = sandbox_override or await self._create_sandbox(run_id)
        self._sandboxes[run_id] = sandbox
        self.stores.run_store.save_run(
            replace(
                record,
                metadata={
                    **record.metadata,
                    "sandbox": {
                        "sandbox_id": sandbox.spec.sandbox_id,
                        "backend": sandbox.backend_name,
                        "status": sandbox.status.value,
                    },
                },
            )
        )
        bind_sandbox = getattr(self.runner, "bind_sandbox", None)
        if bind_sandbox is not None:
            bound = bind_sandbox(sandbox)
            if inspect.isawaitable(bound):
                await bound
        manager = self._build_manager(cancel_event, sandbox=sandbox)
        manager.clear_pause(run_id)
        manager.clear_cancel(run_id)
        checkpoint = (
            manager.get_checkpoint(checkpoint_id)
            if checkpoint_id is not None
            else manager.latest_checkpoint(run_id)
        )
        if checkpoint is None:
            raise ValueError(f"Run has no checkpoint to restart: {run_id}")
        if checkpoint.run_id != run_id:
            raise ValueError(
                f"Checkpoint belongs to {checkpoint.run_id}, not requested run {run_id}"
            )
        self.stores.trace_store.append(
            RunEvent(
                event_type,
                run_id=run_id,
                step_id=f"run_{event_type.value.split('.')[-1]}",
                payload={
                    "workflow_id": compiled.workflow_id,
                    "checkpoint_id": checkpoint.checkpoint_id,
                    **(event_payload or {}),
                },
            )
        )
        snapshot = self._snapshot_for_checkpoint(checkpoint)
        if snapshot is not None:
            await sandbox.restore(snapshot)
            if sandbox.status.value == "paused":
                await sandbox.resume()
            self._append_sandbox_event(
                RunEventType.SANDBOX_RESUMED,
                run_id,
                sandbox,
                {"snapshot_id": snapshot.snapshot_id},
            )
        else:
            self._append_sandbox_event(RunEventType.SANDBOX_STARTED, run_id, sandbox)
        execution = asyncio.create_task(
            self._execute_managed(
                sandbox,
                self._execute(
                    manager,
                    compiled,
                    run_id,
                    {},
                    max_steps=max_steps,
                    checkpoint_id=checkpoint.checkpoint_id,
                ),
            ),
            name=f"cody-runtime-{event_type.value}-{run_id}",
        )
        handle = RuntimeRun(
            run_id=run_id,
            manager=manager,
            stores=self.stores,
            execution=execution,
            cancel_event=cancel_event,
            poll_interval=self.poll_interval,
            sandbox=sandbox,
        )
        self._runs[run_id] = handle
        return handle

    def _snapshot_for_checkpoint(
        self, checkpoint: CheckpointRecord
    ) -> SandboxSnapshot | None:
        artifact_id = checkpoint.metadata.get("sandbox_snapshot_artifact_id")
        if not artifact_id:
            return None
        artifact = self.stores.artifact_store.get(str(artifact_id))
        if artifact is None or not isinstance(artifact.content, dict):
            raise ValueError(
                f"Sandbox snapshot artifact is unavailable: {artifact_id}"
            )
        return SandboxSnapshot.from_dict(artifact.content)

    def _workflow_for_run(
        self,
        record: RunRecord,
        workflow: CompiledWorkflow | Workflow | None,
    ) -> CompiledWorkflow:
        if workflow is not None:
            return workflow.compile() if isinstance(workflow, Workflow) else workflow
        definition = record.metadata.get("workflow_definition")
        if not isinstance(definition, dict):
            raise ValueError(f"Run has no persisted workflow definition: {record.run_id}")
        return CompiledWorkflow.from_dict(definition)

    async def _execute(
        self,
        manager: WorkflowRunManager,
        workflow: CompiledWorkflow,
        run_id: str,
        initial_data: dict[str, Any],
        *,
        max_steps: int,
        checkpoint_id: str | None,
    ) -> RuntimeRunResult:
        try:
            if checkpoint_id is not None:
                state = await manager.resume_from_checkpoint_async(
                    workflow,
                    checkpoint_id,
                    max_steps=max_steps,
                )
            else:
                state = await manager.start_async(
                    workflow,
                    run_id=run_id,
                    initial_data=initial_data,
                    max_steps=max_steps,
                )
        except (WorkflowCancelled, WorkflowWaiting, WorkflowPaused):
            raise
        except Exception:
            raise

        output = str(state.data.get("agent_output") or state.data.get("output") or "")
        artifact = self.stores.artifact_store.save(
            ArtifactRecord(
                run_id=run_id,
                artifact_type=ArtifactType.GENERIC,
                name="runtime-result.json",
                content={"output": output, "state": state.to_dict()},
                metadata={"kind": "runtime_result"},
            )
        )
        options = self._execution_options.get(run_id)
        record = self.stores.run_store.get_run(run_id)
        if record is None:
            raise RuntimeError(f"Runtime run record disappeared: {run_id}")
        return RuntimeRunResult(
            run=record,
            state=state,
            output=output,
            artifact_ids=(artifact.artifact_id,),
            session_id=(options.session_id if options is not None else record.session_id),
            model_result=(
                options.model_result
                if options is not None
                else None
            ),
        )

    def _build_manager(
        self,
        cancel_event: asyncio.Event,
        *,
        sandbox: SandboxHandle | None,
    ) -> WorkflowRunManager:
        handlers = dict(self.node_handlers)
        handlers.setdefault(
            WorkflowNodeType.AGENT.value,
            self._agent_handler(cancel_event, sandbox),
        )
        handlers.setdefault(
            WorkflowNodeType.HUMAN_APPROVAL.value,
            queued_human_approval_node_handler(self.stores.approval_store),
        )
        if self.tool_registry is not None:
            handlers.setdefault(
                WorkflowNodeType.TOOL.value,
                idempotent_registry_tool_node_handler(
                    self.tool_registry,
                    policy=self.tool_policy,
                    artifact_store=self.stores.artifact_store,
                    trace_store=self.stores.trace_store,
                ),
            )
        if self.multi_agent_coordinator is not None:
            coordinator = self.multi_agent_coordinator.clone(
                trace_store=self.stores.trace_store,
                checkpoint_store=self.stores.checkpoint_store,
                artifact_store=self.stores.artifact_store,
                cancel_event=cancel_event,
                max_concurrency=self.max_concurrency,
            )
            handlers.setdefault(
                WorkflowNodeType.AGENT_TEAM.value,
                async_multi_agent_node_handler(coordinator),
            )
        if self.quality_evaluators:
            if sandbox is not None:
                for evaluator in self.quality_evaluators.values():
                    binder = getattr(evaluator, "bind_sandbox", None)
                    if binder is not None:
                        binder(sandbox)
            quality_runner = AsyncQualityGateRunner(
                evaluators=self.quality_evaluators,
                trace_store=self.stores.trace_store,
                checkpoint_store=self.stores.checkpoint_store,
                artifact_store=self.stores.artifact_store,
            )
            handlers.setdefault(
                WorkflowNodeType.QUALITY_GATE.value,
                async_quality_gate_node_handler(quality_runner),
            )
        return WorkflowRunManager(
            trace_store=self.stores.trace_store,
            checkpoint_store=self.stores.checkpoint_store,
            run_store=self.stores.run_store,
            control_state=self.stores.control_store,
            async_node_handlers=handlers,
            async_condition_handlers=self.condition_handlers,
            cancel_event=cancel_event,
            max_concurrency=self.max_concurrency,
            default_node_timeout=self.default_node_timeout,
            force_async_scheduler=True,
        )

    def _agent_handler(
        self, cancel_event: asyncio.Event, sandbox: SandboxHandle | None
    ):
        async def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
            instruction = str(node.metadata.get("prompt") or "")
            task = str(state.data.get("task") or "")
            options = self._execution_options.get(state.run_id)
            if options is None and not instruction:
                options = self._restore_execution_options(state)
                if options is not None:
                    self._execution_options[state.run_id] = options
            prompt: Prompt = (
                options.prompt
                if options is not None and not instruction
                else (
                    task
                    if not instruction
                    else f"Task:\n{task}\n\nRole instruction:\n{instruction}"
                )
            )
            output = ""
            text_parts: list[str] = []
            if options is not None and options.legacy_session_runner:
                return await self._run_legacy_session_adapter(
                    state, node, options, cancel_event
                )
            run_events = getattr(self.runner, "run_events", None)
            if run_events is not None:
                include_tools, exclude_tools = self._effective_agent_tool_filters(options)
                async for event in run_events(
                    prompt,
                    message_history=(options.message_history if options else None),
                    cancel_event=cancel_event,
                    include_tools=include_tools,
                    exclude_tools=exclude_tools,
                    run_id=state.run_id,
                    event_scope="step",
                    step_id_prefix=f"node_{node.node_id}_model",
                    interaction_handler=self._durable_interaction_handler(
                        state.run_id, node.node_id
                    ),
                    sandbox=sandbox,
                ):
                    if event.event_type == RunEventType.MODEL_TEXT_DELTA:
                        text_parts.append(str(event.payload.get("content") or ""))
                    elif event.event_type == RunEventType.MODEL_COMPLETED:
                        result = event.payload.get("result") or {}
                        output = str(result.get("output") or "")
                        if options is not None:
                            source = getattr(event, "source_event", None)
                            options.model_result = getattr(source, "result", None)
                            self._check_model_budget(options)
                    elif event.event_type == RunEventType.MODEL_FAILED:
                        raise WorkflowCancelled(f"Agent node cancelled: {node.node_id}")
                final_output = output or "".join(text_parts)
                self._save_session_messages(options, final_output)
                return {"agent_output": final_output}

            runner_records_canonical_events = (
                getattr(self.runner, "trace_store", None) is self.stores.trace_store
            )
            include_tools, exclude_tools = self._effective_agent_tool_filters(options)
            event_index = 0
            async for event in self.runner.run_stream(
                prompt,
                message_history=(options.message_history if options else None),
                cancel_event=cancel_event,
                include_tools=include_tools,
                exclude_tools=exclude_tools,
                run_id=state.run_id,
                event_scope="step",
                step_id_prefix=f"node_{node.node_id}_model",
                interaction_handler=self._durable_interaction_handler(
                    state.run_id, node.node_id
                ),
                sandbox=sandbox,
            ):
                event_index += 1
                if not runner_records_canonical_events:
                    self.stores.trace_store.append(
                        stream_event_to_run_event(
                            event,
                            run_id=state.run_id,
                            step_id=f"node_{node.node_id}_model_{event_index:06d}",
                            event_scope="step",
                        )
                    )
                event_type = getattr(event, "event_type", "")
                if event_type == "text_delta":
                    text_parts.append(str(getattr(event, "content", "")))
                elif event_type == "done":
                    result = getattr(event, "result", None)
                    output = str(getattr(result, "output", ""))
                    if options is not None:
                        options.model_result = result
                        self._check_model_budget(options)
                elif event_type == "cancelled":
                    raise WorkflowCancelled(f"Agent node cancelled: {node.node_id}")
            final_output = output or "".join(text_parts)
            self._save_session_messages(options, final_output)
            return {"agent_output": final_output}

        return handler

    def _check_model_budget(self, options: _RunExecutionOptions) -> None:
        budget = options.budget
        result = options.model_result
        if budget is None or result is None:
            return
        usage_reader = getattr(result, "usage", None)
        usage = usage_reader() if callable(usage_reader) else None
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        if not total_tokens:
            total_tokens = int(getattr(usage, "input_tokens", 0) or 0) + int(
                getattr(usage, "output_tokens", 0) or 0
            )
        if budget.max_tokens is not None and total_tokens > budget.max_tokens:
            raise RuntimeError(
                f"Run exceeded token budget: {total_tokens} > {budget.max_tokens}"
            )
        estimated_cost = float(
            getattr(getattr(self.runner, "_cb", None), "estimated_cost", 0) or 0
        )
        if budget.max_cost_usd is not None and estimated_cost > budget.max_cost_usd:
            raise RuntimeError(
                f"Run exceeded cost budget: ${estimated_cost:.6f} > ${budget.max_cost_usd:.6f}"
            )

    def _durable_interaction_handler(self, run_id: str, node_id: str):
        """Turn model questions and CONFIRM tools into resumable approvals."""

        async def handle(request) -> InteractionResponse:
            material = json.dumps(
                {
                    "run_id": run_id,
                    "node_id": node_id,
                    "kind": request.kind,
                    "prompt": request.prompt,
                    "context": request.context,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            approval_id = f"approval_interaction_{sha256(material.encode()).hexdigest()}"
            approval = self.stores.approval_store.get(approval_id)
            if approval is None:
                approval = self.stores.approval_store.save(
                    ApprovalRequestRecord(
                        approval_id=approval_id,
                        run_id=run_id,
                        node_id=node_id,
                        request={
                            "kind": request.kind,
                            "prompt": request.prompt,
                            "options": request.options,
                            "context": request.context,
                        },
                        metadata={"kind": "agent_interaction", "request_id": request.id},
                    )
                )
                self.stores.trace_store.append(
                    RunEvent(
                        RunEventType.HUMAN_INPUT_REQUESTED,
                        run_id=run_id,
                        step_id=f"node_{node_id}_approval",
                        payload={
                            "approval_id": approval_id,
                            "request": approval.request,
                        },
                    )
                )
            if approval.status == ApprovalStatus.PENDING:
                raise WorkflowWaiting(f"Waiting for approval: {approval_id}")
            response = approval.response
            action = str(response.get("action") or (
                "approve" if approval.status == ApprovalStatus.APPROVED else "reject"
            ))
            return InteractionResponse(
                request_id=request.id,
                action=action,
                content=str(response.get("content") or response.get("answer") or ""),
            )

        return handle

    def _effective_agent_tool_filters(
        self, options: _RunExecutionOptions | None
    ) -> tuple[list[str] | None, list[str] | None]:
        """Apply the same Runtime ToolPolicy to model-selected AgentRunner tools."""

        requested_include = set(options.include_tools) if options and options.include_tools is not None else None
        requested_exclude = set(options.exclude_tools or ()) if options else set()
        if self.tool_policy is not None:
            if self.tool_policy.allowed_tools is not None:
                allowed = set(self.tool_policy.allowed_tools)
                requested_include = allowed if requested_include is None else requested_include & allowed
            requested_exclude.update(self.tool_policy.denied_tools)
        return (
            sorted(requested_include) if requested_include is not None else None,
            sorted(requested_exclude) if requested_exclude else None,
        )

    async def _run_legacy_session_adapter(
        self,
        state: WorkflowState,
        node: WorkflowNode,
        options: _RunExecutionOptions,
        cancel_event: asyncio.Event,
    ) -> dict[str, Any]:
        """Adapt pre-Runtime injected runners without making them authoritative."""

        include_tools, exclude_tools = self._effective_agent_tool_filters(options)
        stream_method = (
            getattr(self.runner, "run_stream_with_session", None)
            if options.session_store is not None
            else getattr(self.runner, "run_stream", None)
        )
        if inspect.isasyncgenfunction(stream_method):
            output = ""
            event_index = 0
            if options.session_store is not None:
                stream = stream_method(
                    options.prompt,
                    options.session_store,
                    options.session_id,
                    cancel_event=cancel_event,
                    include_tools=include_tools,
                    exclude_tools=exclude_tools,
                )
            else:
                stream = stream_method(
                    options.prompt,
                    cancel_event=cancel_event,
                    include_tools=include_tools,
                    exclude_tools=exclude_tools,
                    run_id=state.run_id,
                    event_scope="step",
                    step_id_prefix=f"node_{node.node_id}_model",
                )
            async for item in stream:
                if options.session_store is not None:
                    event, sid = item
                else:
                    event, sid = item, options.session_id
                options.session_id = sid
                event_index += 1
                runtime_event = stream_event_to_run_event(
                    event,
                    run_id=state.run_id,
                    step_id=f"node_{node.node_id}_model_{event_index:06d}",
                    event_scope="step",
                )
                self.stores.trace_store.append(runtime_event)
                source_result = getattr(event, "result", None)
                if source_result is not None:
                    options.model_result = source_result
                    self._check_model_budget(options)
                    output = str(getattr(source_result, "output", ""))
                if getattr(event, "event_type", "") == "cancelled":
                    raise WorkflowCancelled(f"Agent node cancelled: {node.node_id}")
            return {"agent_output": output}

        run_method = (
            getattr(self.runner, "run_with_session", None)
            if options.session_store is not None
            else getattr(self.runner, "run", None)
        )
        if not callable(run_method) or not inspect.iscoroutinefunction(run_method):
            raise TypeError("Injected runner has no supported execution method")
        if options.session_store is not None:
            result, sid = await run_method(
                options.prompt,
                options.session_store,
                options.session_id,
                include_tools=include_tools,
                exclude_tools=exclude_tools,
                cancel_event=cancel_event,
            )
        else:
            result = await run_method(
                options.prompt,
                include_tools=include_tools,
                exclude_tools=exclude_tools,
                cancel_event=cancel_event,
            )
            sid = options.session_id
        options.session_id = sid
        options.model_result = result
        self._check_model_budget(options)
        output = str(getattr(result, "output", ""))
        self.stores.trace_store.append(
            RunEvent(
                RunEventType.MODEL_COMPLETED,
                run_id=state.run_id,
                step_id=f"node_{node.node_id}_model_000001",
                payload={
                    "result": {"output": output},
                    "legacy_event_type": "done",
                    "event_scope": "step",
                },
            )
        )
        return {"agent_output": output}

    def _prepare_workflow(
        self,
        workflow: CompiledWorkflow | Workflow | Prompt,
        input_data: dict[str, Any] | None,
    ) -> tuple[CompiledWorkflow, dict[str, Any]]:
        data = dict(input_data or {})
        if isinstance(workflow, (str, MultimodalPrompt)):
            data.setdefault("task", prompt_text(workflow))
            compiled = (
                Workflow("single-agent", metadata={"template": "single-agent", "version": 1})
                .node("agent", WorkflowNodeType.AGENT, name="Execute task")
                .compile()
            )
            return compiled, data
        compiled = workflow.compile() if isinstance(workflow, Workflow) else workflow
        data.setdefault("task", compiled.name)
        return compiled, data

    def _restore_execution_options(
        self, state: WorkflowState
    ) -> _RunExecutionOptions | None:
        """Restore a persisted single-agent prompt after process restart."""

        artifact_id = state.data.get("prompt_artifact_id")
        if artifact_id:
            artifact = self.stores.artifact_store.get(str(artifact_id))
            if artifact is not None and isinstance(artifact.content, dict):
                images = [
                    ImageData.from_dict(item)
                    for item in artifact.content.get("images", [])
                ]
                return _RunExecutionOptions(
                    prompt=MultimodalPrompt(
                        text=str(artifact.content.get("text") or ""), images=images
                    )
                )
        task = state.data.get("task")
        if isinstance(task, str):
            return _RunExecutionOptions(prompt=task)
        return None

    @staticmethod
    def _save_session_messages(
        options: _RunExecutionOptions | None, output: str
    ) -> None:
        if (
            options is None
            or options.session_store is None
            or options.session_id is None
            or options.session_saved
        ):
            return
        options.session_store.add_message(
            options.session_id,
            "user",
            prompt_text(options.prompt),
            images=prompt_images(options.prompt) or None,
        )
        options.session_store.add_message(options.session_id, "assistant", output)
        options.session_saved = True

    def _bind_runner_stores(self) -> None:
        if hasattr(self.runner, "_trace_store"):
            self.runner._trace_store = self.stores.trace_store
        if hasattr(self.runner, "_checkpoint_store"):
            self.runner._checkpoint_store = self.stores.checkpoint_store

    def _append_terminal(
        self,
        event_type: RunEventType,
        run_id: str,
        payload: dict[str, Any],
    ) -> None:
        self.stores.trace_store.append(
            RunEvent(event_type, run_id=run_id, step_id="run_terminal", payload=payload)
        )

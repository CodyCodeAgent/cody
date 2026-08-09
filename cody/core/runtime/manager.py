"""Workflow run manager for Cody runtime orchestration."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from .async_executor import AsyncConditionHandler, AsyncNodeHandler, AsyncWorkflowExecutor
from .async_scheduler import AsyncWorkflowScheduler
from .control import WorkflowCancelled, WorkflowControlState, WorkflowPaused, WorkflowWaiting
from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .executor import ConditionHandler, NodeHandler, WorkflowExecutor
from .models import RunRecord, RunStatus
from .registry import InMemoryRunStore, SQLiteRunStore
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import CompiledWorkflow, WorkflowEdgeType, WorkflowNodeType, WorkflowState


class WorkflowRunManagerError(RuntimeError):
    """Raised when workflow run management cannot continue."""


class WorkflowRunManager:
    """Own workflow stores and expose start/resume/fork run operations."""

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        node_handlers: dict[str, NodeHandler] | None = None,
        condition_handlers: dict[str, ConditionHandler] | None = None,
        async_node_handlers: dict[str, AsyncNodeHandler] | None = None,
        async_condition_handlers: dict[str, AsyncConditionHandler] | None = None,
        run_store: InMemoryRunStore | SQLiteRunStore | None = None,
        control_state: WorkflowControlState | None = None,
        nested_workflows: dict[str, CompiledWorkflow] | None = None,
        cancel_event: Any | None = None,
        max_concurrency: int = 8,
        default_node_timeout: float | None = None,
        force_async_scheduler: bool = False,
    ):
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.run_store = run_store or InMemoryRunStore()
        self.control_state = control_state or WorkflowControlState()
        self.node_handlers = node_handlers or {}
        self.condition_handlers = condition_handlers or {}
        self.async_node_handlers = async_node_handlers or {}
        self.async_condition_handlers = async_condition_handlers or {}
        self.nested_workflows = nested_workflows or {}
        self.cancel_event = cancel_event
        self.max_concurrency = max_concurrency
        self.default_node_timeout = default_node_timeout
        self.force_async_scheduler = force_async_scheduler

    def start(
        self,
        workflow: CompiledWorkflow,
        *,
        run_id: str | None = None,
        initial_data: dict[str, Any] | None = None,
        max_steps: int = 100,
    ) -> WorkflowState:
        runtime_run_id = run_id or f"run_{uuid4().hex}"
        self._save_run(workflow, runtime_run_id, initial_data, RunStatus.RUNNING)
        try:
            state = self._executor().run(
                workflow,
                run_id=runtime_run_id,
                initial_data=initial_data,
                max_steps=max_steps,
            )
        except WorkflowPaused:
            self._transition_run(runtime_run_id, RunStatus.PAUSED)
            raise
        except WorkflowCancelled:
            self._transition_run(runtime_run_id, RunStatus.CANCELLED, completed=True)
            raise
        except WorkflowWaiting:
            self._transition_run(runtime_run_id, RunStatus.WAITING)
            raise
        except Exception:
            self._transition_run(runtime_run_id, RunStatus.FAILED, completed=True)
            raise
        self._transition_run(runtime_run_id, RunStatus.COMPLETED, completed=True)
        return state

    async def start_async(
        self,
        workflow: CompiledWorkflow,
        *,
        run_id: str | None = None,
        initial_data: dict[str, Any] | None = None,
        max_steps: int = 100,
    ) -> WorkflowState:
        runtime_run_id = run_id or f"run_{uuid4().hex}"
        self._save_run(workflow, runtime_run_id, initial_data, RunStatus.RUNNING)
        try:
            state = await self._async_runtime(workflow).run(
                workflow,
                run_id=runtime_run_id,
                initial_data=initial_data,
                max_steps=max_steps,
            )
        except WorkflowPaused:
            self._transition_run(runtime_run_id, RunStatus.PAUSED)
            raise
        except WorkflowCancelled:
            self._transition_run(runtime_run_id, RunStatus.CANCELLED, completed=True)
            raise
        except WorkflowWaiting:
            self._transition_run(runtime_run_id, RunStatus.WAITING)
            raise
        except Exception:
            self._transition_run(runtime_run_id, RunStatus.FAILED, completed=True)
            raise
        self._transition_run(runtime_run_id, RunStatus.COMPLETED, completed=True)
        return state

    def resume_latest(
        self,
        workflow: CompiledWorkflow,
        *,
        run_id: str,
        max_steps: int = 100,
    ) -> WorkflowState:
        checkpoint = self.latest_checkpoint(run_id)
        if checkpoint is None:
            raise WorkflowRunManagerError(f"No checkpoint found for run_id: {run_id}")
        return self.resume_from_checkpoint(workflow, checkpoint.checkpoint_id, max_steps=max_steps)

    async def resume_latest_async(
        self,
        workflow: CompiledWorkflow,
        *,
        run_id: str,
        max_steps: int = 100,
    ) -> WorkflowState:
        checkpoint = self.latest_checkpoint(run_id)
        if checkpoint is None:
            raise WorkflowRunManagerError(f"No checkpoint found for run_id: {run_id}")
        return await self.resume_from_checkpoint_async(workflow, checkpoint.checkpoint_id, max_steps=max_steps)

    def resume_from_checkpoint(
        self,
        workflow: CompiledWorkflow,
        checkpoint_id: str,
        *,
        max_steps: int = 100,
    ) -> WorkflowState:
        checkpoint = self.get_checkpoint(checkpoint_id)
        self._transition_run(checkpoint.run_id, RunStatus.RUNNING)
        try:
            state = self._executor().resume(workflow, checkpoint=checkpoint, max_steps=max_steps)
        except WorkflowPaused:
            self._transition_run(checkpoint.run_id, RunStatus.PAUSED)
            raise
        except WorkflowCancelled:
            self._transition_run(checkpoint.run_id, RunStatus.CANCELLED, completed=True)
            raise
        except WorkflowWaiting:
            self._transition_run(checkpoint.run_id, RunStatus.WAITING)
            raise
        except Exception:
            self._transition_run(checkpoint.run_id, RunStatus.FAILED, completed=True)
            raise
        self._transition_run(checkpoint.run_id, RunStatus.COMPLETED, completed=True)
        return state

    async def resume_from_checkpoint_async(
        self,
        workflow: CompiledWorkflow,
        checkpoint_id: str,
        *,
        max_steps: int = 100,
    ) -> WorkflowState:
        checkpoint = self.get_checkpoint(checkpoint_id)
        self._transition_run(checkpoint.run_id, RunStatus.RUNNING)
        try:
            state = await self._async_runtime(workflow).resume(
                workflow,
                checkpoint=checkpoint,
                max_steps=max_steps,
            )
        except WorkflowPaused:
            self._transition_run(checkpoint.run_id, RunStatus.PAUSED)
            raise
        except WorkflowCancelled:
            self._transition_run(checkpoint.run_id, RunStatus.CANCELLED, completed=True)
            raise
        except WorkflowWaiting:
            self._transition_run(checkpoint.run_id, RunStatus.WAITING)
            raise
        except Exception:
            self._transition_run(checkpoint.run_id, RunStatus.FAILED, completed=True)
            raise
        self._transition_run(checkpoint.run_id, RunStatus.COMPLETED, completed=True)
        return state

    def fork_from_checkpoint(
        self,
        checkpoint_id: str,
        *,
        new_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointRecord:
        source = self.get_checkpoint(checkpoint_id)
        source_run = self.run_store.get_run(source.run_id)
        fork_run_id = new_run_id or f"run_{uuid4().hex}"
        workflow_state = dict(source.workflow_state)
        workflow_state["run_id"] = fork_run_id
        fork_metadata = dict(source_run.metadata) if source_run is not None else {}
        fork_metadata.update(source.metadata)
        fork_metadata.update(metadata or {})
        fork_metadata.update({
            "forked_from_checkpoint_id": source.checkpoint_id,
            "forked_from_run_id": source.run_id,
        })
        fork = self.checkpoint_store.save(
            replace(
                source,
                run_id=fork_run_id,
                workflow_state=workflow_state,
                metadata=fork_metadata,
                checkpoint_id=f"ckpt_{uuid4().hex}",
                parent_checkpoint_id=source.checkpoint_id,
            )
        )
        self.run_store.save_run(RunRecord(
            task=str(fork_metadata.get("task") or source.workflow_state.get("data", {}).get("task") or "forked workflow run"),
            run_id=fork_run_id,
            status=RunStatus.PAUSED,
            parent_run_id=source.run_id,
            workflow_id=workflow_state.get("workflow_id"),
            session_id=source_run.session_id if source_run is not None else None,
            project_id=source_run.project_id if source_run is not None else None,
            workdir=source_run.workdir if source_run is not None else None,
            branch=source_run.branch if source_run is not None else None,
            metadata=fork_metadata,
        ))
        return fork

    def request_pause(self, run_id: str, *, before_node_id: str | None = None) -> None:
        self.control_state.request_pause(run_id, before_node_id=before_node_id)

    def clear_pause(self, run_id: str) -> None:
        self.control_state.clear_pause(run_id)

    def request_cancel(self, run_id: str, *, before_node_id: str | None = None) -> None:
        self.control_state.request_cancel(run_id, before_node_id=before_node_id)

    def clear_cancel(self, run_id: str) -> None:
        self.control_state.clear_cancel(run_id)

    def checkpoints(self, run_id: str | None = None) -> list[CheckpointRecord]:
        return self.checkpoint_store.list_checkpoints(run_id)

    def latest_checkpoint(self, run_id: str) -> CheckpointRecord | None:
        return self.checkpoint_store.latest(run_id)

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord:
        checkpoint = self.checkpoint_store.get(checkpoint_id)
        if checkpoint is None:
            raise WorkflowRunManagerError(f"Checkpoint not found: {checkpoint_id}")
        return checkpoint

    def events(self, run_id: str | None = None):
        return self.trace_store.list_events(run_id)

    def get_run(self, run_id: str):
        return self.run_store.get_run(run_id)

    def list_runs(self, *, status: RunStatus | None = None):
        return self.run_store.list_runs(status=status)

    def _save_run(
        self,
        workflow: CompiledWorkflow,
        run_id: str,
        initial_data: dict[str, Any] | None,
        status: RunStatus,
    ) -> RunRecord:
        existing = self.run_store.get_run(run_id)
        if existing is not None:
            return self.run_store.save_run(existing.transition(status))
        task = str((initial_data or {}).get("task") or workflow.name)
        return self.run_store.save_run(RunRecord(
            task=task,
            run_id=run_id,
            status=status,
            workflow_id=workflow.workflow_id,
            metadata={"workflow_name": workflow.name},
        ))

    def _transition_run(self, run_id: str, status: RunStatus, *, completed: bool = False) -> None:
        run = self.run_store.get_run(run_id)
        if run is not None:
            self.run_store.save_run(run.transition(status, completed=completed))

    def _executor(self) -> WorkflowExecutor:
        return WorkflowExecutor(
            trace_store=self.trace_store,
            checkpoint_store=self.checkpoint_store,
            node_handlers=self.node_handlers,
            condition_handlers=self.condition_handlers,
            run_store=self.run_store,
            control_state=self.control_state,
        )

    def _async_executor(self) -> AsyncWorkflowExecutor:
        return AsyncWorkflowExecutor(
            trace_store=self.trace_store,
            checkpoint_store=self.checkpoint_store,
            node_handlers=self.async_node_handlers,
            condition_handlers=self.async_condition_handlers,
            run_store=self.run_store,
            control_state=self.control_state,
        )

    def _async_runtime(
        self,
        workflow: CompiledWorkflow,
    ) -> AsyncWorkflowExecutor | AsyncWorkflowScheduler:
        graph_edges = {
            WorkflowEdgeType.PARALLEL,
            WorkflowEdgeType.JOIN,
            WorkflowEdgeType.FALLBACK,
        }
        use_scheduler = (
            self.force_async_scheduler
            or any(edge.edge_type in graph_edges for edge in workflow.edges)
            or any(
                node.node_type == WorkflowNodeType.NESTED_WORKFLOW
                for node in workflow.nodes.values()
            )
        )
        if not use_scheduler:
            return self._async_executor()
        return AsyncWorkflowScheduler(
            trace_store=self.trace_store,
            checkpoint_store=self.checkpoint_store,
            node_handlers=self.async_node_handlers,
            condition_handlers=self.async_condition_handlers,
            nested_workflows=self.nested_workflows,
            run_store=self.run_store,
            control_state=self.control_state,
            cancel_event=self.cancel_event,
            max_concurrency=self.max_concurrency,
            default_timeout=self.default_node_timeout,
        )

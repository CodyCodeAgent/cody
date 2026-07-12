"""Concurrent async scheduler for non-linear runtime workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import inspect
from typing import Any
from uuid import uuid4

from .async_executor import AsyncConditionHandler, AsyncNodeHandler
from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .control import WorkflowCancelled, WorkflowControlState, WorkflowPaused, WorkflowWaiting
from .events import RunEvent, RunEventType
from .models import StepRecord, StepType
from .registry import InMemoryRunStore, SQLiteRunStore
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import (
    CompiledWorkflow,
    WorkflowEdge,
    WorkflowEdgeType,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowState,
)


class AsyncWorkflowScheduleError(RuntimeError):
    """Raised when concurrent graph execution cannot make safe progress."""


@dataclass(frozen=True)
class _NodeOutcome:
    node: WorkflowNode
    output: dict[str, Any]
    error: BaseException | None = None
    fallback_edges: tuple[WorkflowEdge, ...] = ()
    attempts: int = 1


class AsyncWorkflowScheduler:
    """Execute ready workflow nodes concurrently with deterministic merging."""

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        node_handlers: dict[str, AsyncNodeHandler] | None = None,
        condition_handlers: dict[str, AsyncConditionHandler] | None = None,
        nested_workflows: dict[str, CompiledWorkflow] | None = None,
        run_store: InMemoryRunStore | SQLiteRunStore | None = None,
        control_state: WorkflowControlState | None = None,
        cancel_event: asyncio.Event | None = None,
        max_concurrency: int = 8,
        default_timeout: float | None = None,
    ):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.node_handlers = node_handlers or {}
        self.condition_handlers = condition_handlers or {}
        self.nested_workflows = nested_workflows or {}
        self.run_store = run_store
        self.control_state = control_state
        self.cancel_event = cancel_event
        self.max_concurrency = max_concurrency
        self.default_timeout = default_timeout
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def run(
        self,
        workflow: CompiledWorkflow,
        *,
        run_id: str | None = None,
        initial_data: dict[str, Any] | None = None,
        max_steps: int = 100,
    ) -> WorkflowState:
        runtime_run_id = run_id or f"run_{uuid4().hex}"
        state = workflow.initial_state(runtime_run_id, data=initial_data)
        ready = [workflow.entry_node_id]
        self._checkpoint_event(
            RunEventType.WORKFLOW_STARTED,
            state,
            "scheduler_start",
            {"workflow_id": workflow.workflow_id, "entry_node_id": workflow.entry_node_id},
            ready,
        )
        return await self._run_ready_batches(
            workflow,
            state,
            ready,
            max_steps=max_steps,
        )

    async def resume(
        self,
        workflow: CompiledWorkflow,
        *,
        checkpoint: CheckpointRecord,
        max_steps: int = 100,
    ) -> WorkflowState:
        state = WorkflowState.from_dict(checkpoint.workflow_state)
        if state.workflow_id != workflow.workflow_id:
            raise AsyncWorkflowScheduleError(
                f"Checkpoint workflow mismatch: {state.workflow_id} != {workflow.workflow_id}"
            )
        ready = list(checkpoint.workflow_state.get("scheduler_ready_node_ids") or [])
        if not ready and state.current_node_id is not None:
            ready = [state.current_node_id]
        self._checkpoint_event(
            RunEventType.WORKFLOW_RESUMED,
            state,
            f"scheduler_resume_{checkpoint.step_id}",
            {
                "workflow_id": workflow.workflow_id,
                "checkpoint_id": checkpoint.checkpoint_id,
            },
            ready,
        )
        return await self._run_ready_batches(
            workflow,
            state,
            ready,
            max_steps=max_steps,
        )

    async def _run_ready_batches(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        ready: list[str],
        *,
        max_steps: int,
    ) -> WorkflowState:
        scheduled_steps = 0
        queued = set(ready)
        active_batch: list[str] = []
        try:
            while ready:
                self._check_control(state)
                batch = sorted(
                    node_id
                    for node_id in ready
                    if self._is_ready(workflow, state, node_id)
                )
                if not batch:
                    raise AsyncWorkflowScheduleError(
                        f"Workflow scheduler deadlocked with ready nodes: {sorted(ready)}"
                    )
                self._check_batch_control(state.run_id, batch)
                scheduled_steps += len(batch)
                if scheduled_steps > max_steps:
                    raise AsyncWorkflowScheduleError(
                        f"Workflow exceeded max_steps={max_steps}"
                    )
                for node_id in batch:
                    ready.remove(node_id)
                    queued.discard(node_id)

                active_batch = list(batch)
                outcomes = await self._execute_batch(workflow, state, batch)
                state = self._merge_outcomes(workflow, state, outcomes)
                selected_edges: list[WorkflowEdge] = []
                for outcome in outcomes:
                    if outcome.error is not None:
                        if not outcome.fallback_edges:
                            raise outcome.error
                        selected_edges.extend(outcome.fallback_edges)
                    else:
                        selected_edges.extend(
                            await self._next_edges(workflow, state, outcome.node)
                        )

                for edge in sorted(
                    selected_edges,
                    key=lambda item: (item.source, item.target, item.edge_type.value),
                ):
                    self._append_event(
                        RunEventType.WORKFLOW_EDGE_SELECTED,
                        state.run_id,
                        f"edge_{edge.source}_to_{edge.target}",
                        {"workflow_id": workflow.workflow_id, "edge": edge.to_dict()},
                    )
                    if edge.metadata.get("allow_revisit"):
                        state = replace(
                            state,
                            completed_node_ids=[
                                node_id
                                for node_id in state.completed_node_ids
                                if node_id != edge.target
                            ],
                            failed_node_ids=[
                                node_id
                                for node_id in state.failed_node_ids
                                if node_id != edge.target
                            ],
                        )
                    if (
                        edge.target not in queued
                        and (
                            edge.metadata.get("allow_revisit")
                            or (
                                edge.target not in state.completed_node_ids
                                and edge.target not in state.failed_node_ids
                            )
                        )
                    ):
                        ready.append(edge.target)
                        queued.add(edge.target)

                self._checkpoint_event(
                    RunEventType.WORKFLOW_BATCH_COMPLETED,
                    state,
                    f"scheduler_batch_{scheduled_steps:06d}",
                    {
                        "workflow_id": workflow.workflow_id,
                        "completed_node_ids": [outcome.node.node_id for outcome in outcomes],
                    },
                    sorted(ready),
                )
                active_batch = []

            final_state = replace(state, current_node_id=None)
            self._checkpoint_event(
                RunEventType.WORKFLOW_COMPLETED,
                final_state,
                "scheduler_done",
                {"workflow_id": workflow.workflow_id},
                [],
            )
            return final_state
        except WorkflowPaused as exc:
            self._checkpoint_event(
                RunEventType.WORKFLOW_PAUSED,
                state,
                "scheduler_paused",
                {"workflow_id": workflow.workflow_id, "reason": str(exc)},
                sorted(set(ready) | set(active_batch)),
            )
            raise
        except WorkflowCancelled as exc:
            self._checkpoint_event(
                RunEventType.WORKFLOW_CANCELLED,
                state,
                "scheduler_cancelled",
                {"workflow_id": workflow.workflow_id, "reason": str(exc)},
                sorted(set(ready) | set(active_batch)),
            )
            raise
        except WorkflowWaiting as exc:
            self._checkpoint_event(
                RunEventType.WORKFLOW_WAITING,
                state,
                "scheduler_waiting",
                {"workflow_id": workflow.workflow_id, "reason": str(exc)},
                sorted(set(ready) | set(active_batch)),
            )
            raise
        except Exception as exc:
            self._checkpoint_event(
                RunEventType.WORKFLOW_FAILED,
                state,
                "scheduler_failed",
                {"workflow_id": workflow.workflow_id, "error": str(exc)},
                sorted(set(ready) | set(active_batch)),
            )
            raise

    async def _execute_batch(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        batch: list[str],
    ) -> list[_NodeOutcome]:
        tasks = {
            node_id: asyncio.create_task(
                self._execute_node(workflow, state, workflow.nodes[node_id]),
                name=f"workflow-node-{state.run_id}-{node_id}",
            )
            for node_id in batch
        }
        gather = asyncio.gather(*tasks.values())
        if self.cancel_event is None and self.control_state is None:
            return list(await gather)
        waiters: set[asyncio.Future[Any] | asyncio.Task[Any]] = {gather}
        control_tasks: list[asyncio.Task[Any]] = []
        if self.cancel_event is not None:
            control_tasks.append(asyncio.create_task(self.cancel_event.wait()))
        if self.control_state is not None:
            control_tasks.append(
                asyncio.create_task(
                    self._wait_for_persistent_cancel(state.run_id, batch)
                )
            )
        waiters.update(control_tasks)
        try:
            done, _ = await asyncio.wait(
                waiters,
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            gather.cancel()
            for task in control_tasks:
                task.cancel()
            await asyncio.gather(gather, *control_tasks, return_exceptions=True)
            raise
        if gather not in done:
            gather.cancel()
            await asyncio.gather(gather, return_exceptions=True)
            for task in control_tasks:
                task.cancel()
            await asyncio.gather(*control_tasks, return_exceptions=True)
            raise WorkflowCancelled("Workflow cancelled during concurrent batch")
        for task in control_tasks:
            task.cancel()
        await asyncio.gather(*control_tasks, return_exceptions=True)
        return list(await gather)

    async def _wait_for_persistent_cancel(
        self,
        run_id: str,
        batch: list[str],
    ) -> None:
        while True:
            if self.control_state is not None and (
                self.control_state.should_cancel(run_id)
                or any(
                    self.control_state.should_cancel(run_id, node_id)
                    for node_id in batch
                )
            ):
                return
            await asyncio.sleep(0.05)

    async def _execute_node(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node: WorkflowNode,
    ) -> _NodeOutcome:
        self._append_event(
            RunEventType.WORKFLOW_NODE_STARTED,
            state.run_id,
            f"node_{node.node_id}_started",
            {"workflow_id": workflow.workflow_id, "node": node.to_dict()},
        )
        step = self._start_step(state.run_id, node)
        max_retries = max(0, int(node.metadata.get("max_retries", 0)))
        backoff = max(0.0, float(node.metadata.get("retry_backoff_seconds", 0.0)))
        timeout_value = node.metadata.get("timeout_seconds", self.default_timeout)
        timeout = float(timeout_value) if timeout_value is not None else None
        attempts = 0
        while True:
            attempts += 1
            try:
                if node.node_type == WorkflowNodeType.NESTED_WORKFLOW:
                    output = await self._run_node_handler(workflow, state, node, timeout)
                else:
                    async with self._semaphore:
                        output = await self._run_node_handler(
                            workflow, state, node, timeout
                        )
                normalized = dict(output or {})
                self._append_event(
                    RunEventType.WORKFLOW_NODE_COMPLETED,
                    state.run_id,
                    f"node_{node.node_id}_completed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "node_id": node.node_id,
                        "output": normalized,
                        "attempts": attempts,
                    },
                )
                self._complete_step(step)
                return _NodeOutcome(node=node, output=normalized, attempts=attempts)
            except (WorkflowWaiting, WorkflowCancelled, WorkflowPaused):
                self._wait_step(step, "workflow control transition")
                raise
            except Exception as exc:
                if attempts <= max_retries:
                    self._append_event(
                        RunEventType.WORKFLOW_NODE_RETRYING,
                        state.run_id,
                        f"node_{node.node_id}_retry_{attempts}",
                        {
                            "workflow_id": workflow.workflow_id,
                            "node_id": node.node_id,
                            "attempt": attempts,
                            "max_attempts": max_retries + 1,
                            "error": str(exc),
                        },
                    )
                    if backoff:
                        await asyncio.sleep(backoff * attempts)
                    continue
                self._fail_step(step, str(exc))
                fallback = tuple(
                    edge
                    for edge in workflow.outgoing(node.node_id)
                    if edge.edge_type == WorkflowEdgeType.FALLBACK
                    and getattr(exc, "allow_fallback", True)
                )
                return _NodeOutcome(
                    node=node,
                    output=dict(getattr(exc, "state_updates", {}) or {}),
                    error=exc,
                    fallback_edges=fallback,
                    attempts=attempts,
                )

    async def _run_node_handler(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node: WorkflowNode,
        timeout: float | None,
    ) -> dict[str, Any] | None:
        if node.node_type == WorkflowNodeType.NESTED_WORKFLOW:
            child = self._nested_workflow_for_node(node)
            child_run_id = f"{state.run_id}_{node.node_id}"
            child_state = await self.run(
                child,
                run_id=child_run_id,
                initial_data=dict(state.data),
                max_steps=int(node.metadata.get("max_steps", 100)),
            )
            return {
                "child_run_ids": [*state.data.get("child_run_ids", []), child_run_id],
                f"{node.node_id}_result": child_state.data,
            }
        handler = self.node_handlers.get(node.node_id) or self.node_handlers.get(
            node.node_type.value
        )
        if handler is None:
            raise AsyncWorkflowScheduleError(
                f"No handler registered for workflow node: {node.node_id}"
            )
        value = handler(state, node)
        awaitable = value if inspect.isawaitable(value) else _immediate(value)
        if timeout is None or timeout <= 0:
            return await awaitable
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Workflow node timed out after {timeout}s: {node.node_id}"
            ) from exc

    async def _next_edges(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node: WorkflowNode,
    ) -> list[WorkflowEdge]:
        edges = workflow.outgoing(node.node_id)
        conditionals: list[WorkflowEdge] = []
        parallel = [edge for edge in edges if edge.edge_type == WorkflowEdgeType.PARALLEL]
        defaults = [
            edge
            for edge in edges
            if edge.edge_type in {WorkflowEdgeType.SEQUENTIAL, WorkflowEdgeType.JOIN}
        ]
        for edge in edges:
            if edge.edge_type != WorkflowEdgeType.CONDITIONAL:
                continue
            if not edge.condition:
                continue
            handler = self.condition_handlers.get(edge.condition)
            if handler is None:
                raise AsyncWorkflowScheduleError(
                    f"No condition handler registered: {edge.condition}"
                )
            selected = handler(state, edge)
            if inspect.isawaitable(selected):
                selected = await selected
            if selected:
                conditionals.append(edge)
        return [*parallel, *(conditionals if conditionals else defaults)]

    def _merge_outcomes(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        outcomes: list[_NodeOutcome],
    ) -> WorkflowState:
        data = dict(state.data)
        completed = list(state.completed_node_ids)
        failed = list(state.failed_node_ids)
        owners: dict[str, str] = {}
        merge_policy = str(workflow.metadata.get("parallel_merge_policy", "error"))
        for outcome in sorted(outcomes, key=lambda item: item.node.node_id):
            for key, value in outcome.output.items():
                if key in owners and data.get(key) != value:
                    if merge_policy == "last_write_wins":
                        pass
                    elif merge_policy == "namespace":
                        branch_outputs = dict(data.get("branch_outputs") or {})
                        branch_outputs[outcome.node.node_id] = dict(outcome.output)
                        data["branch_outputs"] = branch_outputs
                        continue
                    else:
                        raise AsyncWorkflowScheduleError(
                            f"Parallel output conflict for key {key!r}: "
                            f"{owners[key]} vs {outcome.node.node_id}"
                        )
                data[key] = value
                owners[key] = outcome.node.node_id
            if outcome.error is not None:
                if outcome.node.node_id not in failed:
                    failed.append(outcome.node.node_id)
                continue
            failed = [
                node_id for node_id in failed if node_id != outcome.node.node_id
            ]
            completed.append(outcome.node.node_id)
        return replace(
            state,
            current_node_id=None,
            data=data,
            completed_node_ids=completed,
            failed_node_ids=failed,
        )

    def _is_ready(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node_id: str,
    ) -> bool:
        joins = [
            edge
            for edge in workflow.incoming(node_id)
            if edge.edge_type == WorkflowEdgeType.JOIN
        ]
        return not joins or all(
            edge.source in state.completed_node_ids for edge in joins
        )

    def _nested_workflow_for_node(self, node: WorkflowNode) -> CompiledWorkflow:
        workflow = node.metadata.get("workflow")
        if isinstance(workflow, CompiledWorkflow):
            return workflow
        workflow_id = node.metadata.get("workflow_id")
        if workflow_id and workflow_id in self.nested_workflows:
            return self.nested_workflows[workflow_id]
        if node.node_id in self.nested_workflows:
            return self.nested_workflows[node.node_id]
        raise AsyncWorkflowScheduleError(
            f"No nested workflow registered for node: {node.node_id}"
        )

    def _check_control(self, state: WorkflowState) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise WorkflowCancelled("Workflow cancellation requested")
        if self.control_state is None:
            return
        if self.control_state.should_cancel(state.run_id, state.current_node_id):
            raise WorkflowCancelled("Workflow cancellation requested")
        if self.control_state.should_pause(state.run_id, state.current_node_id):
            raise WorkflowPaused("Workflow pause requested")

    def _check_batch_control(self, run_id: str, batch: list[str]) -> None:
        if self.control_state is None:
            return
        if any(self.control_state.should_cancel(run_id, node_id) for node_id in batch):
            raise WorkflowCancelled("Workflow cancellation requested")
        if any(self.control_state.should_pause(run_id, node_id) for node_id in batch):
            raise WorkflowPaused("Workflow pause requested")

    def _start_step(self, run_id: str, node: WorkflowNode) -> StepRecord | None:
        if self.run_store is None:
            return None
        step = StepRecord(
            run_id=run_id,
            node_id=node.node_id,
            agent_id=node.agent_name,
            step_type=_step_type_for_node(node),
            metadata={"node_type": node.node_type.value},
        ).start()
        return self.run_store.save_step(step)

    def _complete_step(self, step: StepRecord | None) -> None:
        if self.run_store is not None and step is not None:
            self.run_store.save_step(step.complete())

    def _wait_step(self, step: StepRecord | None, reason: str) -> None:
        if self.run_store is not None and step is not None:
            self.run_store.save_step(step.wait(output_ref=reason))

    def _fail_step(self, step: StepRecord | None, error: str) -> None:
        if self.run_store is not None and step is not None:
            self.run_store.save_step(step.fail(error_ref=error))

    def _append_event(
        self,
        event_type: RunEventType,
        run_id: str,
        step_id: str,
        payload: dict[str, Any],
    ) -> RunEvent:
        return self.trace_store.append(
            RunEvent(event_type, run_id=run_id, step_id=step_id, payload=payload)
        )

    def _checkpoint_event(
        self,
        event_type: RunEventType,
        state: WorkflowState,
        step_id: str,
        payload: dict[str, Any],
        ready: list[str],
    ) -> RunEvent:
        event = RunEvent(
            event_type,
            run_id=state.run_id,
            step_id=step_id,
            payload=payload,
        )
        workflow_state = state.to_dict()
        workflow_state["scheduler_ready_node_ids"] = list(ready)
        checkpoint = self.checkpoint_store.save(
            CheckpointRecord(
                run_id=state.run_id,
                step_id=step_id,
                workflow_state=workflow_state,
                child_run_ids=list(state.data.get("child_run_ids", [])),
                metadata={
                    "runtime_event_id": event.event_id,
                    "runtime_event_type": event.event_type.value,
                    "scheduler_safe_boundary": True,
                },
            )
        )
        event.payload.setdefault("checkpoint_id", checkpoint.checkpoint_id)
        self.trace_store.append(event)
        return event


async def _immediate(value: Any) -> Any:
    return value


def _step_type_for_node(node: WorkflowNode) -> StepType:
    if node.node_type == WorkflowNodeType.AGENT:
        return StepType.MODEL
    if node.node_type == WorkflowNodeType.AGENT_TEAM:
        return StepType.HANDOFF
    if node.node_type == WorkflowNodeType.QUALITY_GATE:
        return StepType.SYSTEM
    if node.node_type == WorkflowNodeType.TOOL:
        return StepType.TOOL
    if node.node_type == WorkflowNodeType.HUMAN_APPROVAL:
        return StepType.APPROVAL
    if node.node_type == WorkflowNodeType.CHECKPOINT:
        return StepType.CHECKPOINT
    return StepType.SYSTEM

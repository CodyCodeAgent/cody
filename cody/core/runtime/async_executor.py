"""Async workflow executor for Cody runtime graphs."""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, Awaitable, Callable
from uuid import uuid4

from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .control import WorkflowCancelled, WorkflowControlState, WorkflowPaused, WorkflowWaiting
from .events import RunEvent, RunEventType
from .models import StepRecord, StepType
from .registry import InMemoryRunStore, SQLiteRunStore
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import CompiledWorkflow, WorkflowEdge, WorkflowEdgeType, WorkflowNode, WorkflowState

AsyncNodeHandler = Callable[[WorkflowState, WorkflowNode], Awaitable[dict[str, Any] | None] | dict[str, Any] | None]
AsyncConditionHandler = Callable[[WorkflowState, WorkflowEdge], Awaitable[bool] | bool]


class AsyncWorkflowExecutionError(RuntimeError):
    """Raised when async workflow execution cannot continue."""


class AsyncWorkflowExecutor:
    """Execute a compiled workflow with async-aware node and condition handlers."""

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        node_handlers: dict[str, AsyncNodeHandler] | None = None,
        condition_handlers: dict[str, AsyncConditionHandler] | None = None,
        run_store: InMemoryRunStore | SQLiteRunStore | None = None,
        control_state: WorkflowControlState | None = None,
    ):
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.run_store = run_store
        self.control_state = control_state
        self.node_handlers = node_handlers or {}
        self.condition_handlers = condition_handlers or {}

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
        self._record(
            RunEventType.WORKFLOW_STARTED,
            runtime_run_id,
            "workflow_start",
            {"workflow_id": workflow.workflow_id, "entry_node_id": workflow.entry_node_id},
            state,
        )

        return await self._run_from_state(workflow, state, max_steps=max_steps)

    async def resume(
        self,
        workflow: CompiledWorkflow,
        *,
        checkpoint: CheckpointRecord,
        max_steps: int = 100,
    ) -> WorkflowState:
        state = _state_from_checkpoint(workflow, checkpoint)
        self._record(
            RunEventType.WORKFLOW_RESUMED,
            state.run_id,
            f"resume_{checkpoint.step_id}",
            {
                "workflow_id": workflow.workflow_id,
                "checkpoint_id": checkpoint.checkpoint_id,
                "checkpoint_step_id": checkpoint.step_id,
            },
            state,
        )
        return await self._run_from_state(workflow, state, max_steps=max_steps)

    async def _run_from_state(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        *,
        max_steps: int,
    ) -> WorkflowState:
        steps = 0
        try:
            while state.current_node_id is not None:
                self._check_control(state)
                steps += 1
                if steps > max_steps:
                    raise AsyncWorkflowExecutionError(f"Workflow exceeded max_steps={max_steps}")
                node = workflow.nodes[state.current_node_id]
                state = await self._execute_node(workflow, state, node)
            self._record(
                RunEventType.WORKFLOW_COMPLETED,
                state.run_id,
                "workflow_done",
                {"workflow_id": workflow.workflow_id},
                state,
            )
            return state
        except WorkflowPaused as exc:
            self._record(
                RunEventType.WORKFLOW_PAUSED,
                state.run_id,
                f"workflow_paused_{steps}",
                {"workflow_id": workflow.workflow_id, "reason": str(exc)},
                state,
            )
            raise
        except WorkflowCancelled as exc:
            self._record(
                RunEventType.WORKFLOW_CANCELLED,
                state.run_id,
                f"workflow_cancelled_{steps}",
                {"workflow_id": workflow.workflow_id, "reason": str(exc)},
                state,
            )
            raise
        except WorkflowWaiting as exc:
            self._record(
                RunEventType.WORKFLOW_WAITING,
                state.run_id,
                f"workflow_waiting_{steps}",
                {"workflow_id": workflow.workflow_id, "reason": str(exc)},
                state,
            )
            raise
        except Exception as exc:
            self._record(
                RunEventType.WORKFLOW_FAILED,
                state.run_id,
                f"workflow_failed_{steps}",
                {"workflow_id": workflow.workflow_id, "error": str(exc)},
                state,
            )
            raise

    def _check_control(self, state: WorkflowState) -> None:
        if self.control_state is None:
            return
        node_id = state.current_node_id
        if self.control_state.should_cancel(state.run_id, node_id):
            raise WorkflowCancelled(f"Workflow cancelled before node: {node_id}")
        if self.control_state.should_pause(state.run_id, node_id):
            raise WorkflowPaused(f"Workflow paused before node: {node_id}")

    async def _execute_node(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node: WorkflowNode,
    ) -> WorkflowState:
        run_id = state.run_id
        self._record(
            RunEventType.WORKFLOW_NODE_STARTED,
            run_id,
            f"node_{node.node_id}_started",
            {"workflow_id": workflow.workflow_id, "node": node.to_dict()},
            state,
        )

        step = self._start_step(run_id, node)
        try:
            handler = self.node_handlers.get(node.node_id) or self.node_handlers.get(node.node_type.value)
            output = await _maybe_await(handler(state, node)) if handler else None
            next_data = dict(state.data)
            if output:
                next_data.update(output)

            completed = [*state.completed_node_ids, node.node_id]
            edge_state = replace(
                state,
                data=next_data,
                completed_node_ids=completed,
            )
            next_edge = await self._select_edge(workflow, edge_state, node)
            next_node_id = next_edge.target if next_edge else None
            next_state = replace(edge_state, current_node_id=next_node_id)
        except WorkflowWaiting as exc:
            self._wait_step(step, output_ref=str(exc))
            raise
        except Exception as exc:
            self._fail_step(step, error_ref=str(exc))
            raise

        completed_event = self._record(
            RunEventType.WORKFLOW_NODE_COMPLETED,
            run_id,
            f"node_{node.node_id}_completed",
            {"workflow_id": workflow.workflow_id, "node_id": node.node_id, "output": output or {}},
            next_state,
        )
        self._complete_step(step, checkpoint_id=completed_event.payload.get("checkpoint_id"))
        if next_edge:
            self._record(
                RunEventType.WORKFLOW_EDGE_SELECTED,
                run_id,
                f"edge_{next_edge.source}_to_{next_edge.target}",
                {"workflow_id": workflow.workflow_id, "edge": next_edge.to_dict()},
                next_state,
            )
        return next_state

    async def _select_edge(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node: WorkflowNode,
    ) -> WorkflowEdge | None:
        edges = workflow.outgoing(node.node_id)
        if not edges:
            return None

        non_conditional = [edge for edge in edges if edge.edge_type != WorkflowEdgeType.CONDITIONAL]
        conditional = [edge for edge in edges if edge.edge_type == WorkflowEdgeType.CONDITIONAL]

        for edge in conditional:
            if edge.condition is None:
                continue
            handler = self.condition_handlers.get(edge.condition)
            if handler is None:
                raise AsyncWorkflowExecutionError(f"No condition handler registered: {edge.condition}")
            if await _maybe_await(handler(state, edge)):
                return edge

        if non_conditional:
            return non_conditional[0]
        return None

    def _start_step(self, run_id: str, node: WorkflowNode) -> StepRecord | None:
        if self.run_store is None:
            return None
        step = StepRecord(
            run_id=run_id,
            step_id=f"node_{node.node_id}",
            step_type=_step_type_for_node(node),
            node_id=node.node_id,
            agent_id=node.agent_name,
            metadata={"node_type": node.node_type.value, "node_name": node.name},
        ).start()
        return self.run_store.save_step(step)

    def _complete_step(self, step: StepRecord | None, *, checkpoint_id: str | None) -> None:
        if self.run_store is not None and step is not None:
            self.run_store.save_step(step._replace(checkpoint_id=checkpoint_id).complete())

    def _wait_step(self, step: StepRecord | None, *, output_ref: str) -> None:
        if self.run_store is not None and step is not None:
            self.run_store.save_step(step.wait(output_ref=output_ref))

    def _fail_step(self, step: StepRecord | None, *, error_ref: str) -> None:
        if self.run_store is not None and step is not None:
            self.run_store.save_step(step.fail(error_ref=error_ref))

    def _record(
        self,
        event_type: RunEventType,
        run_id: str,
        step_id: str,
        payload: dict[str, Any],
        state: WorkflowState,
    ) -> RunEvent:
        event = RunEvent(event_type=event_type, run_id=run_id, step_id=step_id, payload=payload)
        checkpoint = self.checkpoint_store.save(
            CheckpointRecord(
                run_id=run_id,
                step_id=step_id,
                workflow_state=state.to_dict(),
                metadata={
                    "runtime_event_id": event.event_id,
                    "runtime_event_type": event.event_type.value,
                },
            )
        )
        event.payload.setdefault("checkpoint_id", checkpoint.checkpoint_id)
        self.trace_store.append(event)
        return event


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _state_from_checkpoint(workflow: CompiledWorkflow, checkpoint: CheckpointRecord) -> WorkflowState:
    if not checkpoint.workflow_state:
        raise AsyncWorkflowExecutionError(f"Checkpoint has no workflow state: {checkpoint.checkpoint_id}")
    state = WorkflowState.from_dict(checkpoint.workflow_state)
    if state.workflow_id != workflow.workflow_id:
        raise AsyncWorkflowExecutionError(
            f"Checkpoint workflow_id mismatch: {state.workflow_id} != {workflow.workflow_id}"
        )
    if state.current_node_id is not None and state.current_node_id not in workflow.nodes:
        raise AsyncWorkflowExecutionError(
            f"Checkpoint current_node_id does not exist in workflow: {state.current_node_id}"
        )
    return state


def _step_type_for_node(node: WorkflowNode) -> StepType:
    node_type = node.node_type.value
    if node_type == "agent":
        return StepType.MODEL
    if node_type == "tool":
        return StepType.TOOL
    if node_type == "human_approval":
        return StepType.APPROVAL
    if node_type == "checkpoint":
        return StepType.CHECKPOINT
    return StepType.SYSTEM

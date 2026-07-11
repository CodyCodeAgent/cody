"""Graph scheduler for parallel, join, fallback, and nested workflows."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .control import WorkflowCancelled, WorkflowControlState, WorkflowPaused, WorkflowWaiting
from .events import RunEvent, RunEventType
from .executor import ConditionHandler, NodeHandler, WorkflowExecutionError, _step_type_for_node
from .models import StepRecord
from .registry import InMemoryRunStore, SQLiteRunStore
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import CompiledWorkflow, WorkflowEdge, WorkflowEdgeType, WorkflowNode, WorkflowNodeType, WorkflowState


class WorkflowScheduleError(WorkflowExecutionError):
    """Raised when scheduled graph execution cannot continue."""


class WorkflowScheduler:
    """Execute non-linear workflow graphs.

    The scheduler extends the single-cursor executor with deterministic support
    for fan-out/fan-in graphs, fallback edges, and nested workflow nodes. It is
    intentionally single-process and deterministic today; callers can later map
    the ready queue onto worker pools without changing workflow semantics.
    """

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        node_handlers: dict[str, NodeHandler] | None = None,
        condition_handlers: dict[str, ConditionHandler] | None = None,
        nested_workflows: dict[str, CompiledWorkflow] | None = None,
        run_store: InMemoryRunStore | SQLiteRunStore | None = None,
        control_state: WorkflowControlState | None = None,
    ):
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.node_handlers = node_handlers or {}
        self.condition_handlers = condition_handlers or {}
        self.nested_workflows = nested_workflows or {}
        self.run_store = run_store
        self.control_state = control_state

    def run(
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
            "scheduler_start",
            {"workflow_id": workflow.workflow_id, "entry_node_id": workflow.entry_node_id},
            state,
        )
        return self._run_ready_queue(workflow, state, [workflow.entry_node_id], max_steps=max_steps)

    def _run_ready_queue(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        ready: list[str],
        *,
        max_steps: int,
    ) -> WorkflowState:
        steps = 0
        queued = set(ready)
        try:
            while ready:
                node_id = ready.pop(0)
                queued.discard(node_id)
                if node_id in state.completed_node_ids or node_id in state.failed_node_ids:
                    continue
                if not self._is_ready(workflow, state, node_id):
                    ready.append(node_id)
                    queued.add(node_id)
                    if not any(self._is_ready(workflow, state, pending) for pending in ready):
                        raise WorkflowScheduleError(f"Workflow scheduler deadlocked before node: {node_id}")
                    continue

                state = replace(state, current_node_id=node_id)
                self._check_control(state)
                steps += 1
                if steps > max_steps:
                    raise WorkflowScheduleError(f"Workflow exceeded max_steps={max_steps}")

                node = workflow.nodes[node_id]
                state, outgoing_edges = self._execute_node(workflow, state, node)
                for edge in outgoing_edges:
                    self._record(
                        RunEventType.WORKFLOW_EDGE_SELECTED,
                        state.run_id,
                        f"edge_{edge.source}_to_{edge.target}",
                        {"workflow_id": workflow.workflow_id, "edge": edge.to_dict()},
                        state,
                    )
                    if edge.target not in queued and edge.target not in state.completed_node_ids:
                        ready.append(edge.target)
                        queued.add(edge.target)

            final_state = replace(state, current_node_id=None)
            self._record(
                RunEventType.WORKFLOW_COMPLETED,
                final_state.run_id,
                "scheduler_done",
                {"workflow_id": workflow.workflow_id},
                final_state,
            )
            return final_state
        except WorkflowPaused as exc:
            self._record(RunEventType.WORKFLOW_PAUSED, state.run_id, f"scheduler_paused_{steps}", {"workflow_id": workflow.workflow_id, "reason": str(exc)}, state)
            raise
        except WorkflowCancelled as exc:
            self._record(RunEventType.WORKFLOW_CANCELLED, state.run_id, f"scheduler_cancelled_{steps}", {"workflow_id": workflow.workflow_id, "reason": str(exc)}, state)
            raise
        except WorkflowWaiting as exc:
            self._record(RunEventType.WORKFLOW_WAITING, state.run_id, f"scheduler_waiting_{steps}", {"workflow_id": workflow.workflow_id, "reason": str(exc)}, state)
            raise
        except Exception as exc:
            self._record(RunEventType.WORKFLOW_FAILED, state.run_id, f"scheduler_failed_{steps}", {"workflow_id": workflow.workflow_id, "error": str(exc)}, state)
            raise

    def _execute_node(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node: WorkflowNode,
    ) -> tuple[WorkflowState, list[WorkflowEdge]]:
        self._record(
            RunEventType.WORKFLOW_NODE_STARTED,
            state.run_id,
            f"node_{node.node_id}_started",
            {"workflow_id": workflow.workflow_id, "node": node.to_dict()},
            state,
        )
        step = self._start_step(state.run_id, node)
        try:
            output = self._run_node_handler(workflow, state, node)
        except WorkflowWaiting as exc:
            self._wait_step(step, output_ref=str(exc))
            raise
        except Exception as exc:
            self._fail_step(step, error_ref=str(exc))
            failed_state = replace(state, failed_node_ids=[*state.failed_node_ids, node.node_id])
            fallback_edges = self._fallback_edges(workflow, failed_state, node)
            if fallback_edges:
                return failed_state, fallback_edges
            raise

        next_data = dict(state.data)
        if output:
            next_data.update(output)
        next_state = replace(
            state,
            data=next_data,
            completed_node_ids=[*state.completed_node_ids, node.node_id],
        )
        completed_event = self._record(
            RunEventType.WORKFLOW_NODE_COMPLETED,
            state.run_id,
            f"node_{node.node_id}_completed",
            {"workflow_id": workflow.workflow_id, "node_id": node.node_id, "output": output or {}},
            next_state,
        )
        self._complete_step(step, checkpoint_id=completed_event.payload.get("checkpoint_id"))
        return next_state, self._next_edges(workflow, next_state, node)

    def _run_node_handler(
        self,
        workflow: CompiledWorkflow,
        state: WorkflowState,
        node: WorkflowNode,
    ) -> dict[str, Any] | None:
        if node.node_type == WorkflowNodeType.NESTED_WORKFLOW:
            child = self._nested_workflow_for_node(node)
            child_run_id = f"{state.run_id}_{node.node_id}"
            child_state = self.run(
                child,
                run_id=child_run_id,
                initial_data=dict(state.data),
                max_steps=int(node.metadata.get("max_steps", 100)),
            )
            return {
                "child_run_ids": [*state.data.get("child_run_ids", []), child_run_id],
                f"{node.node_id}_result": child_state.data,
            }
        handler = self.node_handlers.get(node.node_id) or self.node_handlers.get(node.node_type.value)
        return handler(state, node) if handler else None

    def _nested_workflow_for_node(self, node: WorkflowNode) -> CompiledWorkflow:
        workflow = node.metadata.get("workflow")
        if isinstance(workflow, CompiledWorkflow):
            return workflow
        workflow_id = node.metadata.get("workflow_id")
        if workflow_id and workflow_id in self.nested_workflows:
            return self.nested_workflows[workflow_id]
        if node.node_id in self.nested_workflows:
            return self.nested_workflows[node.node_id]
        raise WorkflowScheduleError(f"No nested workflow registered for node: {node.node_id}")

    def _next_edges(self, workflow: CompiledWorkflow, state: WorkflowState, node: WorkflowNode) -> list[WorkflowEdge]:
        edges = workflow.outgoing(node.node_id)
        selected: list[WorkflowEdge] = []
        for edge in edges:
            if edge.edge_type == WorkflowEdgeType.FALLBACK:
                continue
            if edge.edge_type == WorkflowEdgeType.CONDITIONAL:
                if not edge.condition:
                    continue
                handler = self.condition_handlers.get(edge.condition)
                if handler is None:
                    raise WorkflowScheduleError(f"No condition handler registered: {edge.condition}")
                if handler(state, edge):
                    selected.append(edge)
                continue
            selected.append(edge)
        return selected

    def _fallback_edges(self, workflow: CompiledWorkflow, state: WorkflowState, node: WorkflowNode) -> list[WorkflowEdge]:
        return [edge for edge in workflow.outgoing(node.node_id) if edge.edge_type == WorkflowEdgeType.FALLBACK]

    def _is_ready(self, workflow: CompiledWorkflow, state: WorkflowState, node_id: str) -> bool:
        incoming = [edge for edge in workflow.incoming(node_id) if edge.edge_type == WorkflowEdgeType.JOIN]
        if not incoming:
            return True
        return all(edge.source in state.completed_node_ids for edge in incoming)

    def _check_control(self, state: WorkflowState) -> None:
        if self.control_state is None:
            return
        if self.control_state.should_cancel(state.run_id, state.current_node_id):
            raise WorkflowCancelled(f"Workflow cancelled before node: {state.current_node_id}")
        if self.control_state.should_pause(state.run_id, state.current_node_id):
            raise WorkflowPaused(f"Workflow paused before node: {state.current_node_id}")

    def _record(self, event_type: RunEventType, run_id: str, step_id: str, payload: dict[str, Any], state: WorkflowState) -> RunEvent:
        event = RunEvent(event_type=event_type, run_id=run_id, step_id=step_id, payload=payload)
        checkpoint = self.checkpoint_store.save(
            CheckpointRecord(
                run_id=run_id,
                step_id=step_id,
                workflow_state=state.to_dict(),
                child_run_ids=list(state.data.get("child_run_ids", [])),
                metadata={"runtime_event_id": event.event_id, "runtime_event_type": event.event_type.value},
            )
        )
        event.payload.setdefault("checkpoint_id", checkpoint.checkpoint_id)
        self.trace_store.append(event)
        return event

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

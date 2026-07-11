"""High-level runtime workflow APIs."""

from __future__ import annotations

from typing import Any

from .adapters import AgentCallable, ApprovalCallable, ToolCallable, agent_node_handler, human_approval_node_handler, tool_node_handler
from .checkpoint import InMemoryCheckpointStore, SQLiteCheckpointStore
from .executor import WorkflowExecutor
from .templates import coding_workflow_template, refactor_workflow_template
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import WorkflowState


def run_coding_workflow(
    *,
    task: str,
    run_agent: AgentCallable,
    call_tool: ToolCallable,
    request_approval: ApprovalCallable,
    run_id: str | None = None,
    trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
    checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
    max_steps: int = 100,
) -> WorkflowState:
    """Run the built-in coding workflow with concrete backend callbacks."""

    executor = _build_executor(
        run_agent=run_agent,
        call_tool=call_tool,
        request_approval=request_approval,
        trace_store=trace_store,
        checkpoint_store=checkpoint_store,
    )
    return executor.run(
        coding_workflow_template().compile(),
        run_id=run_id,
        initial_data={"task": task},
        max_steps=max_steps,
    )


def run_refactor_workflow(
    *,
    task: str,
    run_agent: AgentCallable,
    call_tool: ToolCallable,
    request_approval: ApprovalCallable | None = None,
    run_id: str | None = None,
    trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
    checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
    max_steps: int = 100,
) -> WorkflowState:
    """Run the built-in refactor workflow with concrete backend callbacks."""

    executor = _build_executor(
        run_agent=run_agent,
        call_tool=call_tool,
        request_approval=request_approval or (lambda request, state, node: True),
        trace_store=trace_store,
        checkpoint_store=checkpoint_store,
    )
    return executor.run(
        refactor_workflow_template().compile(),
        run_id=run_id,
        initial_data={"task": task},
        max_steps=max_steps,
    )


def _build_executor(
    *,
    run_agent: AgentCallable,
    call_tool: ToolCallable,
    request_approval: ApprovalCallable,
    trace_store: InMemoryTraceStore | SQLiteTraceStore | None,
    checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None,
) -> WorkflowExecutor:
    return WorkflowExecutor(
        trace_store=trace_store,
        checkpoint_store=checkpoint_store,
        node_handlers={
            "agent": agent_node_handler(run_agent),
            "tool": tool_node_handler(call_tool),
            "human_approval": human_approval_node_handler(request_approval),
        },
        condition_handlers={
            "tests_failed": _tests_failed,
            "review_requested_changes": _review_requested_changes,
        },
    )


def _tests_failed(state: WorkflowState, _edge: Any) -> bool:
    if "tests_failed" in state.data:
        return bool(state.data["tests_failed"])
    if "tests_passed" in state.data:
        return not bool(state.data["tests_passed"])
    return False


def _review_requested_changes(state: WorkflowState, _edge: Any) -> bool:
    return bool(state.data.get("review_requested_changes", False))

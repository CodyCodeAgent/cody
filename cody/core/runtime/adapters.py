"""Workflow node adapter factories.

Adapters keep `WorkflowExecutor` generic while giving applications standard ways
to delegate nodes to agents, tools, and human approval systems.
"""

from __future__ import annotations

from typing import Any, Callable

from .approval import ApprovalRequestRecord, InMemoryApprovalStore, SQLiteApprovalStore
from .control import WorkflowWaiting
from .executor import NodeHandler, WorkflowExecutionError
from .workflow import WorkflowNode, WorkflowState

AgentCallable = Callable[[str, WorkflowState, WorkflowNode], dict[str, Any] | str | None]
ToolCallable = Callable[[str, dict[str, Any], WorkflowState, WorkflowNode], dict[str, Any] | str | None]
ApprovalCallable = Callable[[dict[str, Any], WorkflowState, WorkflowNode], bool | dict[str, Any]]


def agent_node_handler(run_agent: AgentCallable) -> NodeHandler:
    """Create a node handler that delegates an agent node to ``run_agent``.

    The prompt is read from node metadata key ``prompt`` first, then from the
    workflow state's ``task`` field. String agent outputs are normalized into
    ``{"agent_output": ...}`` so workflow state remains dict-shaped.
    """

    def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        prompt = str(node.metadata.get("prompt") or state.data.get("task") or "")
        result = run_agent(prompt, state, node)
        return _normalize_result(result, default_key="agent_output")

    return handler


def tool_node_handler(call_tool: ToolCallable) -> NodeHandler:
    """Create a node handler that delegates a tool node to ``call_tool``.

    The tool name is read from ``node.tool_name`` or ``metadata['tool_name']``.
    Tool arguments come from ``metadata['args']`` and must be a dictionary.
    """

    def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        tool_name = node.tool_name or node.metadata.get("tool_name")
        if not tool_name:
            raise WorkflowExecutionError(f"Tool workflow node missing tool_name: {node.node_id}")
        args = node.metadata.get("args") or {}
        if not isinstance(args, dict):
            raise WorkflowExecutionError(f"Tool workflow node args must be a dict: {node.node_id}")
        result = call_tool(str(tool_name), args, state, node)
        return _normalize_result(result, default_key="tool_output")

    return handler


def human_approval_node_handler(request_approval: ApprovalCallable) -> NodeHandler:
    """Create a node handler for human approval nodes.

    Approval request metadata comes from ``metadata['request']``. A boolean
    callback result is normalized to ``{"approved": bool}``; dictionary results
    are merged into workflow state unchanged.
    """

    def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        request = node.metadata.get("request") or {"node_id": node.node_id}
        if not isinstance(request, dict):
            raise WorkflowExecutionError(
                f"Human approval workflow node request must be a dict: {node.node_id}"
            )
        result = request_approval(request, state, node)
        if isinstance(result, bool):
            return {"approved": result}
        return _normalize_result(result, default_key="approval")

    return handler


def _normalize_result(result: dict[str, Any] | str | None, *, default_key: str) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    return {default_key: str(result)}


def queued_human_approval_node_handler(
    approval_store: InMemoryApprovalStore | SQLiteApprovalStore,
) -> NodeHandler:
    """Create a human approval handler that stores a pending request and waits."""

    def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        request = node.metadata.get("request") or {"node_id": node.node_id}
        if not isinstance(request, dict):
            raise WorkflowExecutionError(
                f"Human approval workflow node request must be a dict: {node.node_id}"
            )
        existing = [
            approval
            for approval in approval_store.list(run_id=state.run_id)
            if approval.node_id == node.node_id
        ]
        if existing:
            latest = existing[-1]
            if latest.status.value == "approved":
                return {"approval_id": latest.approval_id, **latest.response}
            if latest.status.value == "rejected":
                return {"approval_id": latest.approval_id, "approved": False, **latest.response}
            if latest.status.value == "expired":
                return {"approval_id": latest.approval_id, "approved": False, "approval_expired": True, **latest.response}
            raise WorkflowWaiting(f"Workflow waiting for approval: {latest.approval_id}")

        approval = approval_store.save(ApprovalRequestRecord(
            run_id=state.run_id,
            node_id=node.node_id,
            request=request,
            requested_by=node.agent_name,
            metadata={"workflow_id": state.workflow_id},
        ))
        raise WorkflowWaiting(f"Workflow waiting for approval: {approval.approval_id}")

    return handler

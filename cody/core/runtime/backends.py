"""Cody-native backend builders for runtime workflows."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .adapters import AgentCallable, ApprovalCallable, ToolCallable
from .bridge import stream_event_to_run_event
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import WorkflowNode, WorkflowState

ToolBackend = Callable[[dict[str, Any], WorkflowState, WorkflowNode], dict[str, Any] | str | None]


def agent_runner_backend(runner: Any) -> AgentCallable:
    """Create an agent backend backed by ``AgentRunner.run_sync``.

    This intentionally targets the synchronous runner path first so workflow APIs
    can be used from scripts/tests without introducing an async executor contract.
    """

    def run_agent(prompt: str, _state: WorkflowState, _node: WorkflowNode) -> dict[str, Any]:
        result = runner.run_sync(prompt)
        return {"agent_output": getattr(result, "output", str(result))}

    return run_agent


def tool_mapping_backend(tools: Mapping[str, ToolBackend]) -> ToolCallable:
    """Create a tool backend from a mapping of tool names to callables."""

    def call_tool(
        tool_name: str,
        args: dict[str, Any],
        state: WorkflowState,
        node: WorkflowNode,
    ) -> dict[str, Any] | str | None:
        if tool_name not in tools:
            raise KeyError(f"No workflow tool backend registered: {tool_name}")
        return tools[tool_name](args, state, node)

    return call_tool


def static_approval_backend(*, approved: bool = True) -> ApprovalCallable:
    """Create a deterministic approval backend for trusted/local workflows."""

    def approve(request: dict[str, Any], _state: WorkflowState, _node: WorkflowNode) -> dict[str, Any]:
        return {"approved": approved, "approval_request": request}

    return approve


def agent_runner_streaming_backend(
    runner: Any,
    *,
    trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
) -> AgentCallable:
    """Create an async agent backend backed by ``AgentRunner.run_stream``.

    The returned callable is intended for ``AsyncWorkflowExecutor``. It consumes
    runner stream events, optionally mirrors them into the workflow trace store,
    and returns a compact dict containing streamed event metadata and final text.
    """

    async def run_agent(prompt: str, state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        stream_events: list[dict[str, Any]] = []
        text_parts: list[str] = []
        final_output: str | None = None
        index = 0

        async for event in runner.run_stream(
            prompt,
            run_id=state.run_id,
            event_scope="step",
            step_id_prefix=f"node_{node.node_id}_model",
        ):
            index += 1
            event_type = getattr(event, "event_type", event.__class__.__name__)
            event_data: dict[str, Any] = {"event_type": event_type}
            content = getattr(event, "content", None)
            if content is not None:
                event_data["content"] = content
                if event_type == "text_delta":
                    text_parts.append(str(content))
            result = getattr(event, "result", None)
            if result is not None:
                final_output = getattr(result, "output", str(result))
                event_data["output"] = final_output
            stream_events.append(event_data)
            runner_trace_store = getattr(runner, "trace_store", None)
            if trace_store is not None and runner_trace_store is not trace_store:
                trace_store.append(stream_event_to_run_event(
                    event,
                    run_id=state.run_id,
                    step_id=f"{node.node_id}_stream_{index:06d}",
                    event_scope="step",
                ))

        return {
            "agent_output": final_output if final_output is not None else "".join(text_parts),
            "agent_stream_events": stream_events,
        }

    return run_agent

"""Tool registry and policy primitives for runtime workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from hashlib import sha256
import inspect
import json
from typing import Any, Awaitable, Callable

from .artifact import ArtifactRecord, ArtifactType, InMemoryArtifactStore, SQLiteArtifactStore
from .events import RunEvent, RunEventType
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import WorkflowNode, WorkflowState

ToolOutput = dict[str, Any] | str | None
ToolHandler = Callable[
    [dict[str, Any], WorkflowState, WorkflowNode],
    Awaitable[ToolOutput] | ToolOutput,
]


class ToolExecutionDenied(RuntimeError):
    """Raised when runtime policy denies tool execution."""


@dataclass(frozen=True)
class ToolSpec:
    """Registered runtime tool with minimal schema and policy metadata."""

    name: str
    handler: ToolHandler
    description: str | None = None
    required_args: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    artifact_type: ArtifactType = ArtifactType.TOOL_OUTPUT
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate_args(self, args: dict[str, Any]) -> None:
        missing = [arg for arg in self.required_args if arg not in args]
        if missing:
            raise ValueError(f"Tool {self.name} missing required args: {', '.join(missing)}")


@dataclass(frozen=True)
class ToolPolicy:
    """Simple allow/deny/capability policy for tool execution."""

    allowed_tools: frozenset[str] | None = None
    denied_tools: frozenset[str] = frozenset()
    allowed_capabilities: frozenset[str] | None = None

    def check(self, spec: ToolSpec) -> None:
        if spec.name in self.denied_tools:
            raise ToolExecutionDenied(f"Tool denied by policy: {spec.name}")
        if self.allowed_tools is not None and spec.name not in self.allowed_tools:
            raise ToolExecutionDenied(f"Tool not in allowlist: {spec.name}")
        if self.allowed_capabilities is not None:
            missing = [
                capability
                for capability in spec.capabilities
                if capability not in self.allowed_capabilities
            ]
            if missing:
                raise ToolExecutionDenied(
                    f"Tool {spec.name} requires disallowed capabilities: {', '.join(missing)}"
                )


@dataclass
class ToolRegistry:
    """In-memory runtime tool registry."""

    _tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Duplicate runtime tool: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def require(self, name: str) -> ToolSpec:
        spec = self.get(name)
        if spec is None:
            raise KeyError(f"Runtime tool not registered: {name}")
        return spec

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())


def registry_tool_backend(
    registry: ToolRegistry,
    *,
    policy: ToolPolicy | None = None,
    artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | None = None,
):
    """Create a ToolCallable backed by a registry, policy, and optional artifacts."""

    def call_tool(
        tool_name: str,
        args: dict[str, Any],
        state: WorkflowState,
        node: WorkflowNode,
    ) -> dict[str, Any] | str | None:
        spec = registry.require(tool_name)
        if policy is not None:
            policy.check(spec)
        spec.validate_args(args)
        output = spec.handler(args, state, node)
        if artifact_store is not None:
            artifact = artifact_store.save(ArtifactRecord(
                run_id=state.run_id,
                step_id=f"node_{node.node_id}",
                artifact_type=spec.artifact_type,
                name=f"tool:{tool_name}",
                content=output if output is not None else {},
                metadata={"tool_name": tool_name, "node_id": node.node_id},
            ))
            if isinstance(output, dict):
                return {**output, "artifact_id": artifact.artifact_id}
            return {"tool_output": output, "artifact_id": artifact.artifact_id}
        return output

    return call_tool


def idempotent_registry_tool_node_handler(
    registry: ToolRegistry,
    *,
    policy: ToolPolicy | None = None,
    artifact_store: InMemoryArtifactStore | SQLiteArtifactStore,
    trace_store: InMemoryTraceStore | SQLiteTraceStore,
):
    """Build an async workflow tool handler with durable result receipts.

    A completed receipt prevents a retry or checkpoint resume from executing the
    same tool node twice in one run. Tools that call external APIs can opt into
    receiving the key by setting ``metadata['idempotency_arg']`` on ToolSpec.
    """

    locks: dict[str, asyncio.Lock] = {}

    async def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        tool_name = node.tool_name or node.metadata.get("tool_name")
        if not tool_name:
            raise ValueError(f"Tool workflow node missing tool_name: {node.node_id}")
        args = dict(node.metadata.get("args") or {})
        spec = registry.require(str(tool_name))
        if policy is not None:
            policy.check(spec)
        spec.validate_args(args)
        key = _tool_idempotency_key(state, node, spec.name, args)
        receipt_id = f"artifact_tool_receipt_{sha256(key.encode()).hexdigest()}"
        lock = locks.setdefault(receipt_id, asyncio.Lock())

        async with lock:
            receipt = artifact_store.get(receipt_id)
            if receipt is not None:
                output = _receipt_output(receipt)
                _append_tool_event(
                    trace_store,
                    RunEventType.TOOL_CALL_COMPLETED,
                    state,
                    node,
                    spec.name,
                    {
                        "idempotency_key": key,
                        "receipt_artifact_id": receipt_id,
                        "replayed": True,
                    },
                )
                return _tool_result(output, receipt_id, replayed=True)

            idempotency_arg = spec.metadata.get("idempotency_arg")
            if idempotency_arg:
                args.setdefault(str(idempotency_arg), key)
            _append_tool_event(
                trace_store,
                RunEventType.TOOL_CALL_STARTED,
                state,
                node,
                spec.name,
                {"args": args, "idempotency_key": key},
            )
            try:
                output = spec.handler(args, state, node)
                if inspect.isawaitable(output):
                    output = await output
            except Exception as exc:
                _append_tool_event(
                    trace_store,
                    RunEventType.TOOL_CALL_COMPLETED,
                    state,
                    node,
                    spec.name,
                    {"idempotency_key": key, "ok": False, "error": str(exc)},
                )
                raise

            receipt = artifact_store.save(
                ArtifactRecord(
                    artifact_id=receipt_id,
                    run_id=state.run_id,
                    step_id=f"node_{node.node_id}",
                    artifact_type=spec.artifact_type,
                    name=f"tool-receipt:{spec.name}",
                    content={"output": output, "idempotency_key": key},
                    metadata={
                        "kind": "tool_execution_receipt",
                        "tool_name": spec.name,
                        "node_id": node.node_id,
                    },
                )
            )
            _append_tool_event(
                trace_store,
                RunEventType.TOOL_CALL_COMPLETED,
                state,
                node,
                spec.name,
                {
                    "idempotency_key": key,
                    "receipt_artifact_id": receipt.artifact_id,
                    "replayed": False,
                    "ok": True,
                },
            )
            return _tool_result(output, receipt.artifact_id, replayed=False)

    return handler


def _tool_idempotency_key(
    state: WorkflowState,
    node: WorkflowNode,
    tool_name: str,
    args: dict[str, Any],
) -> str:
    explicit = node.metadata.get("idempotency_key")
    if explicit:
        return str(explicit)
    material = json.dumps(
        {
            "run_id": state.run_id,
            "node_id": node.node_id,
            "tool_name": tool_name,
            "args": args,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"runtime-tool:{sha256(material.encode()).hexdigest()}"


def _receipt_output(receipt: ArtifactRecord) -> ToolOutput:
    if not isinstance(receipt.content, dict):
        raise ValueError(f"Invalid tool receipt content: {receipt.artifact_id}")
    return receipt.content.get("output")


def _tool_result(output: ToolOutput, artifact_id: str, *, replayed: bool) -> dict[str, Any]:
    metadata = {"artifact_id": artifact_id, "idempotency_replayed": replayed}
    if isinstance(output, dict):
        return {**output, **metadata}
    return {"tool_output": output, **metadata}


def _append_tool_event(
    trace_store: InMemoryTraceStore | SQLiteTraceStore,
    event_type: RunEventType,
    state: WorkflowState,
    node: WorkflowNode,
    tool_name: str,
    payload: dict[str, Any],
) -> None:
    trace_store.append(
        RunEvent(
            event_type,
            run_id=state.run_id,
            step_id=f"node_{node.node_id}",
            payload={"tool_name": tool_name, "node_id": node.node_id, **payload},
        )
    )

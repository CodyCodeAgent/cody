"""Tool registry and policy primitives for runtime workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .artifact import ArtifactRecord, ArtifactType, InMemoryArtifactStore, SQLiteArtifactStore
from .workflow import WorkflowNode, WorkflowState

ToolHandler = Callable[[dict[str, Any], WorkflowState, WorkflowNode], dict[str, Any] | str | None]


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
            missing = [capability for capability in spec.capabilities if capability not in self.allowed_capabilities]
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

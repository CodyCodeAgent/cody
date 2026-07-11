"""Workflow graph primitives for Cody's runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class WorkflowNodeType(str, Enum):
    """Kinds of nodes supported by the runtime workflow graph."""

    AGENT = "agent"
    TOOL = "tool"
    HUMAN_APPROVAL = "human_approval"
    FUNCTION = "function"
    CHECKPOINT = "checkpoint"
    NESTED_WORKFLOW = "nested_workflow"


class WorkflowEdgeType(str, Enum):
    """Kinds of edges supported by the runtime workflow graph."""

    SEQUENTIAL = "sequential"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    JOIN = "join"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class WorkflowNode:
    """A node in a workflow graph."""

    node_id: str
    node_type: WorkflowNodeType
    name: str | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "name": self.name,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class WorkflowEdge:
    """A directed edge between workflow nodes."""

    source: str
    target: str
    edge_type: WorkflowEdgeType = WorkflowEdgeType.SEQUENTIAL
    condition: str | None = None
    label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "condition": self.condition,
            "label": self.label,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class WorkflowState:
    """Mutable-at-runtime state envelope for a workflow run."""

    workflow_id: str
    run_id: str
    current_node_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    completed_node_ids: list[str] = field(default_factory=list)
    failed_node_ids: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "current_node_id": self.current_node_id,
            "data": self.data,
            "completed_node_ids": self.completed_node_ids,
            "failed_node_ids": self.failed_node_ids,
            "artifact_refs": self.artifact_refs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        return cls(
            workflow_id=data["workflow_id"],
            run_id=data["run_id"],
            current_node_id=data.get("current_node_id"),
            data=dict(data.get("data") or {}),
            completed_node_ids=list(data.get("completed_node_ids") or []),
            failed_node_ids=list(data.get("failed_node_ids") or []),
            artifact_refs=list(data.get("artifact_refs") or []),
        )


@dataclass(frozen=True)
class CompiledWorkflow:
    """Validated immutable workflow graph."""

    workflow_id: str
    name: str
    nodes: dict[str, WorkflowNode]
    edges: list[WorkflowEdge]
    entry_node_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def outgoing(self, node_id: str) -> list[WorkflowEdge]:
        return [edge for edge in self.edges if edge.source == node_id]

    def incoming(self, node_id: str) -> list[WorkflowEdge]:
        return [edge for edge in self.edges if edge.target == node_id]

    def initial_state(self, run_id: str, data: dict[str, Any] | None = None) -> WorkflowState:
        return WorkflowState(
            workflow_id=self.workflow_id,
            run_id=run_id,
            current_node_id=self.entry_node_id,
            data=data or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "entry_node_id": self.entry_node_id,
            "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": self.metadata,
        }


@dataclass
class Workflow:
    """Builder for validated runtime workflows."""

    name: str
    workflow_id: str = field(default_factory=lambda: f"workflow_{uuid4().hex}")
    metadata: dict[str, Any] = field(default_factory=dict)
    _nodes: dict[str, WorkflowNode] = field(default_factory=dict, init=False, repr=False)
    _edges: list[WorkflowEdge] = field(default_factory=list, init=False, repr=False)
    _entry_node_id: str | None = field(default=None, init=False, repr=False)

    def node(
        self,
        node_id: str,
        node_type: WorkflowNodeType,
        *,
        name: str | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Workflow":
        if node_id in self._nodes:
            raise ValueError(f"Duplicate workflow node: {node_id}")
        self._nodes[node_id] = WorkflowNode(
            node_id=node_id,
            node_type=node_type,
            name=name,
            agent_name=agent_name,
            tool_name=tool_name,
            input_schema=input_schema,
            output_schema=output_schema,
            metadata=metadata or {},
        )
        if self._entry_node_id is None:
            self._entry_node_id = node_id
        return self

    def edge(
        self,
        source: str,
        target: str,
        *,
        edge_type: WorkflowEdgeType = WorkflowEdgeType.SEQUENTIAL,
        condition: str | None = None,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Workflow":
        self._edges.append(WorkflowEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            condition=condition,
            label=label,
            metadata=metadata or {},
        ))
        return self

    def conditional_edge(
        self,
        source: str,
        target: str,
        *,
        condition: str,
        label: str | None = None,
    ) -> "Workflow":
        return self.edge(
            source,
            target,
            edge_type=WorkflowEdgeType.CONDITIONAL,
            condition=condition,
            label=label,
        )

    def entrypoint(self, node_id: str) -> "Workflow":
        self._entry_node_id = node_id
        return self

    def compile(self) -> CompiledWorkflow:
        if not self._nodes:
            raise ValueError("Workflow must define at least one node")
        if self._entry_node_id not in self._nodes:
            raise ValueError(f"Workflow entrypoint does not exist: {self._entry_node_id}")
        for edge in self._edges:
            if edge.source not in self._nodes:
                raise ValueError(f"Workflow edge source does not exist: {edge.source}")
            if edge.target not in self._nodes:
                raise ValueError(f"Workflow edge target does not exist: {edge.target}")
            if edge.edge_type == WorkflowEdgeType.CONDITIONAL and not edge.condition:
                raise ValueError("Conditional workflow edges must define a condition")
        return CompiledWorkflow(
            workflow_id=self.workflow_id,
            name=self.name,
            nodes=dict(self._nodes),
            edges=list(self._edges),
            entry_node_id=self._entry_node_id,
            metadata=dict(self.metadata),
        )

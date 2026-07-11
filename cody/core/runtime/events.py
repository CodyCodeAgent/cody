"""Canonical runtime event model for Cody.

This module is the foundation for the long-term Agent Runtime: every shell
(CLI/TUI/Web/SDK), workflow node, tool call, checkpoint, and human approval
should eventually emit the same append-only RunEvent shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = "2026-07-03.v1"


class RunEventType(str, Enum):
    """Stable event names emitted by the runtime event bus."""

    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    SESSION_STARTED = "session.started"

    MODEL_THINKING_DELTA = "model.thinking.delta"
    MODEL_TEXT_DELTA = "model.text.delta"
    MODEL_RETRYING = "model.retrying"

    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_COMPLETED = "tool.call.completed"

    CONTEXT_PRUNED = "context.pruned"
    CONTEXT_COMPACTED = "context.compacted"

    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker.triggered"
    HUMAN_INPUT_REQUESTED = "human.input.requested"
    USER_INPUT_RECEIVED = "user.input.received"

    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_RESUMED = "workflow.resumed"
    WORKFLOW_PAUSED = "workflow.paused"
    WORKFLOW_CANCELLED = "workflow.cancelled"
    WORKFLOW_WAITING = "workflow.waiting"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_NODE_STARTED = "workflow.node.started"
    WORKFLOW_NODE_COMPLETED = "workflow.node.completed"
    WORKFLOW_EDGE_SELECTED = "workflow.edge.selected"


@dataclass(frozen=True)
class ActorRef:
    """Identity of the actor that produced an event."""

    kind: str = "runtime"
    id: str = "cody"

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id}


@dataclass(frozen=True)
class RunEvent:
    """Append-only runtime event.

    The payload intentionally stays as a dict so existing stream events, future
    workflow graph nodes, approval decisions, and tool-specific metadata can be
    represented without schema churn. The outer envelope is stable and suitable
    for persistence, replay, UI timelines, and telemetry export.
    """

    event_type: RunEventType
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    step_id: str | None = None
    parent_event_id: str | None = None
    actor: ActorRef = field(default_factory=ActorRef)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "parent_event_id": self.parent_event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor.to_dict(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunEvent":
        """Rehydrate an event previously produced by ``to_dict()``."""

        actor_data = data.get("actor") or {}
        return cls(
            event_type=RunEventType(data["event_type"]),
            payload=dict(data.get("payload") or {}),
            run_id=data.get("run_id"),
            step_id=data.get("step_id"),
            parent_event_id=data.get("parent_event_id"),
            actor=ActorRef(
                kind=actor_data.get("kind", "runtime"),
                id=actor_data.get("id", "cody"),
            ),
            event_id=data.get("event_id") or uuid4().hex,
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(timezone.utc),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
        )

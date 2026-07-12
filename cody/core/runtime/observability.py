"""Derived per-run metrics over the canonical event and artifact stores."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .events import RunEventType


class RuntimeObservability:
    def __init__(self, trace_store: Any, checkpoint_store: Any = None, artifact_store: Any = None):
        self.trace_store = trace_store
        self.checkpoint_store = checkpoint_store
        self.artifact_store = artifact_store

    def snapshot(self, run_id: str) -> dict[str, Any]:
        events = self.trace_store.list_events(run_id)
        counts = Counter(event.event_type.value for event in events)
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        estimated_cost_usd = 0.0
        for event in events:
            if event.event_type == RunEventType.RUN_COMPLETED:
                terminal_usage = event.payload.get("usage") or {}
                for key in usage:
                    usage[key] = int(terminal_usage.get(key) or usage[key])
            if event.event_type == RunEventType.CIRCUIT_BREAKER_TRIGGERED:
                estimated_cost_usd = max(
                    estimated_cost_usd, float(event.payload.get("cost_usd") or 0)
                )
        duration_ms = 0
        if len(events) >= 2:
            duration_ms = max(
                0, int((events[-1].timestamp - events[0].timestamp).total_seconds() * 1000)
            )
        checkpoints = (
            len(self.checkpoint_store.list_checkpoints(run_id))
            if self.checkpoint_store is not None else 0
        )
        artifacts = (
            len(self.artifact_store.list(run_id=run_id))
            if self.artifact_store is not None else 0
        )
        return {
            "run_id": run_id,
            "duration_ms": duration_ms,
            "event_count": len(events),
            "step_count": counts[RunEventType.WORKFLOW_NODE_STARTED.value],
            "model_calls": counts[RunEventType.MODEL_COMPLETED.value],
            "tool_calls": counts[RunEventType.TOOL_CALL_STARTED.value],
            "model_retries": counts[RunEventType.MODEL_RETRYING.value],
            "node_retries": counts[RunEventType.WORKFLOW_NODE_RETRYING.value],
            "quality_gate_failures": counts[RunEventType.QUALITY_GATE_FAILED.value],
            "checkpoints": checkpoints,
            "artifacts": artifacts,
            "usage": usage,
            "estimated_cost_usd": estimated_cost_usd,
            "event_types": dict(sorted(counts.items())),
        }

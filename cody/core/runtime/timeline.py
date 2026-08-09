"""Replay, debugger, and timeline APIs for runtime runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .artifact import ArtifactRecord, InMemoryArtifactStore, SQLiteArtifactStore
from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .events import RunEvent
from .trace import InMemoryTraceStore, SQLiteTraceStore


@dataclass(frozen=True)
class TimelineItem:
    """One inspectable point on a run timeline."""

    index: int
    event: RunEvent
    checkpoint: CheckpointRecord | None = None
    artifacts: tuple[ArtifactRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "event": self.event.to_dict(),
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


@dataclass(frozen=True)
class RunTimeline:
    """Chronological run timeline assembled from trace/checkpoint/artifact stores."""

    run_id: str
    items: tuple[TimelineItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "items": [item.to_dict() for item in self.items]}

    def filter(self, *, event_type: str | None = None, step_id: str | None = None) -> "RunTimeline":
        items = self.items
        if event_type is not None:
            items = tuple(item for item in items if item.event.event_type.value == event_type)
        if step_id is not None:
            items = tuple(item for item in items if item.event.step_id == step_id)
        return RunTimeline(run_id=self.run_id, items=items)


@dataclass(frozen=True)
class DebugFrame:
    """Debugger-friendly view of one timeline item."""

    run_id: str
    index: int
    event_id: str
    step_id: str | None
    event_type: str
    payload: dict[str, Any]
    workflow_state: dict[str, Any] = field(default_factory=dict)
    artifact_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "index": self.index,
            "event_id": self.event_id,
            "step_id": self.step_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "workflow_state": self.workflow_state,
            "artifact_ids": list(self.artifact_ids),
        }


class TimelineAPI:
    """Read-only API for replaying and debugging runtime traces."""

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | None = None,
    ):
        self.trace_store = trace_store
        self.checkpoint_store = checkpoint_store
        self.artifact_store = artifact_store

    def timeline(self, run_id: str) -> RunTimeline:
        events = self.trace_store.list_events(run_id=run_id)
        checkpoints = self._checkpoints_by_id(run_id)
        artifacts_by_step = self._artifacts_by_step(run_id)
        items: list[TimelineItem] = []
        for index, event in enumerate(events):
            checkpoint_id = event.payload.get("checkpoint_id")
            checkpoint = checkpoints.get(checkpoint_id) if checkpoint_id else None
            artifacts = artifacts_by_step.get(event.step_id or "", ())
            if checkpoint:
                artifacts = (*artifacts, *self._artifacts_for_refs(checkpoint.artifact_refs))
            items.append(TimelineItem(index=index, event=event, checkpoint=checkpoint, artifacts=artifacts))
        return RunTimeline(run_id=run_id, items=tuple(items))

    def frame(self, run_id: str, index: int) -> DebugFrame:
        timeline = self.timeline(run_id)
        try:
            item = timeline.items[index]
        except IndexError as exc:
            raise IndexError(f"Timeline index out of range: {index}") from exc
        checkpoint_state = item.checkpoint.workflow_state if item.checkpoint else {}
        artifact_ids = tuple(artifact.artifact_id for artifact in item.artifacts)
        return DebugFrame(
            run_id=run_id,
            index=item.index,
            event_id=item.event.event_id,
            step_id=item.event.step_id,
            event_type=item.event.event_type.value,
            payload=item.event.payload,
            workflow_state=checkpoint_state,
            artifact_ids=artifact_ids,
        )

    def replay(self, run_id: str, *, until_index: int | None = None) -> list[dict[str, Any]]:
        timeline = self.timeline(run_id)
        items = timeline.items if until_index is None else timeline.items[: until_index + 1]
        return [item.event.to_dict() for item in items]

    def export(self, run_id: str) -> dict[str, Any]:
        return self.timeline(run_id).to_dict()

    def _checkpoints_by_id(self, run_id: str) -> dict[str, CheckpointRecord]:
        if self.checkpoint_store is None:
            return {}
        return {checkpoint.checkpoint_id: checkpoint for checkpoint in self.checkpoint_store.list_checkpoints(run_id)}

    def _artifacts_by_step(self, run_id: str) -> dict[str, tuple[ArtifactRecord, ...]]:
        if self.artifact_store is None:
            return {}
        artifacts = self.artifact_store.list(run_id=run_id)
        by_step: dict[str, list[ArtifactRecord]] = {}
        for artifact in artifacts:
            if artifact.step_id:
                by_step.setdefault(artifact.step_id, []).append(artifact)
        return {step_id: tuple(items) for step_id, items in by_step.items()}

    def _artifacts_for_refs(self, artifact_refs: list[str]) -> tuple[ArtifactRecord, ...]:
        if self.artifact_store is None:
            return ()
        artifacts = []
        for artifact_id in artifact_refs:
            artifact = self.artifact_store.get(artifact_id)
            if artifact is not None:
                artifacts.append(artifact)
        return tuple(artifacts)

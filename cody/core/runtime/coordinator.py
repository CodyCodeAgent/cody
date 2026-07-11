"""Multi-agent coordination primitives for Cody runtime workflows."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from .artifact import ArtifactRecord, ArtifactType, InMemoryArtifactStore, SQLiteArtifactStore
from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .events import RunEvent, RunEventType
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import WorkflowState

AgentBackend = Callable[["AgentTask", WorkflowState], dict[str, Any] | None]
Reducer = Callable[[list["AgentTaskRecord"], WorkflowState], dict[str, Any] | None]


class AgentTaskStatus(str, Enum):
    """Lifecycle states for coordinated multi-agent work."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class AgentRole:
    """Registered agent capability profile."""

    agent_id: str
    name: str | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "capabilities": sorted(self.capabilities),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AgentTask:
    """A unit of work that can be assigned to one specialist agent."""

    task_id: str
    prompt: str
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    depends_on: tuple[str, ...] = ()
    preferred_agent_id: str | None = None
    fallback_agent_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        prompt: str,
        *,
        task_id: str | None = None,
        required_capabilities: set[str] | frozenset[str] | None = None,
        depends_on: tuple[str, ...] | list[str] = (),
        preferred_agent_id: str | None = None,
        fallback_agent_ids: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "AgentTask":
        return cls(
            task_id=task_id or f"agent_task_{uuid4().hex}",
            prompt=prompt,
            required_capabilities=frozenset(required_capabilities or ()),
            depends_on=tuple(depends_on),
            preferred_agent_id=preferred_agent_id,
            fallback_agent_ids=tuple(fallback_agent_ids),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "required_capabilities": sorted(self.required_capabilities),
            "depends_on": list(self.depends_on),
            "preferred_agent_id": self.preferred_agent_id,
            "fallback_agent_ids": list(self.fallback_agent_ids),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AgentTaskRecord:
    """Execution record for one coordinated agent task."""

    task: AgentTask
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    assigned_agent_id: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    attempts: int = 0

    def start(self, agent_id: str) -> "AgentTaskRecord":
        return replace(self, status=AgentTaskStatus.RUNNING, assigned_agent_id=agent_id, attempts=self.attempts + 1)

    def complete(self, output: dict[str, Any] | None = None) -> "AgentTaskRecord":
        return replace(self, status=AgentTaskStatus.COMPLETED, output=output or {}, error=None)

    def fail(self, error: str) -> "AgentTaskRecord":
        return replace(self, status=AgentTaskStatus.FAILED, error=error)

    def skip(self, error: str) -> "AgentTaskRecord":
        return replace(self, status=AgentTaskStatus.SKIPPED, error=error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "status": self.status.value,
            "assigned_agent_id": self.assigned_agent_id,
            "output": self.output,
            "error": self.error,
            "attempts": self.attempts,
        }


class MultiAgentCoordinator:
    """Coordinate specialist agent backends with dependencies and reduction.

    The coordinator is intentionally runtime-native: every task emits trace
    events, checkpoints are saved after state transitions, and optional artifact
    storage can persist final task outputs for UI/debug/replay surfaces.
    """

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | None = None,
        reducer: Reducer | None = None,
    ):
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.artifact_store = artifact_store
        self.reducer = reducer
        self._roles: dict[str, AgentRole] = {}
        self._backends: dict[str, AgentBackend] = {}

    def register_agent(self, role: AgentRole, backend: AgentBackend) -> None:
        self._roles[role.agent_id] = role
        self._backends[role.agent_id] = backend

    def run(
        self,
        tasks: list[AgentTask],
        *,
        state: WorkflowState,
        max_rounds: int = 100,
    ) -> tuple[WorkflowState, list[AgentTaskRecord]]:
        records = {task.task_id: AgentTaskRecord(task=task) for task in tasks}
        completed: set[str] = set()
        failed_or_skipped: set[str] = set()
        rounds = 0
        self._record(RunEventType.WORKFLOW_STARTED, state.run_id, "multi_agent_started", {"task_count": len(tasks)}, state)

        while len(completed) + len(failed_or_skipped) < len(tasks):
            rounds += 1
            if rounds > max_rounds:
                raise RuntimeError(f"Multi-agent coordination exceeded max_rounds={max_rounds}")
            progress = False
            for task in tasks:
                record = records[task.task_id]
                if record.status != AgentTaskStatus.PENDING:
                    continue
                blocked = [dep for dep in task.depends_on if dep not in completed]
                if blocked:
                    if any(dep in failed_or_skipped for dep in blocked):
                        records[task.task_id] = record.skip(f"Dependency failed or skipped: {blocked}")
                        failed_or_skipped.add(task.task_id)
                        progress = True
                    continue
                records[task.task_id] = self._run_task(task, records[task.task_id], state)
                if records[task.task_id].status == AgentTaskStatus.COMPLETED:
                    completed.add(task.task_id)
                    state = self._merge_output(state, records[task.task_id])
                else:
                    failed_or_skipped.add(task.task_id)
                progress = True
            if not progress:
                raise RuntimeError("Multi-agent coordination deadlocked on task dependencies")

        ordered_records = [records[task.task_id] for task in tasks]
        if self.reducer is not None:
            reduced = self.reducer(ordered_records, state) or {}
            state = replace(state, data={**state.data, **reduced})
        self._record(
            RunEventType.WORKFLOW_COMPLETED,
            state.run_id,
            "multi_agent_completed",
            {"tasks": [record.to_dict() for record in ordered_records]},
            state,
        )
        return state, ordered_records

    def _run_task(self, task: AgentTask, record: AgentTaskRecord, state: WorkflowState) -> AgentTaskRecord:
        candidates = self._candidate_agent_ids(task)
        if not candidates:
            return record.skip("No registered agent satisfies task requirements")
        last_error: str | None = None
        for agent_id in candidates:
            running = record.start(agent_id)
            self._record(
                RunEventType.WORKFLOW_NODE_STARTED,
                state.run_id,
                f"agent_task_{task.task_id}_started",
                {"task": task.to_dict(), "agent": self._roles[agent_id].to_dict()},
                state,
            )
            try:
                output = self._backends[agent_id](task, state) or {}
            except Exception as exc:
                last_error = str(exc)
                record = running.fail(last_error)
                continue
            completed = running.complete(output)
            self._save_artifact(completed, state)
            self._record(
                RunEventType.WORKFLOW_NODE_COMPLETED,
                state.run_id,
                f"agent_task_{task.task_id}_completed",
                completed.to_dict(),
                state,
            )
            return completed
        return record.fail(last_error or "All candidate agents failed")

    def _candidate_agent_ids(self, task: AgentTask) -> list[str]:
        preferred = [task.preferred_agent_id] if task.preferred_agent_id else []
        fallbacks = list(task.fallback_agent_ids)
        capable = [
            agent_id
            for agent_id, role in self._roles.items()
            if task.required_capabilities.issubset(role.capabilities)
        ]
        ordered = [agent_id for agent_id in [*preferred, *fallbacks, *capable] if agent_id]
        seen: set[str] = set()
        return [agent_id for agent_id in ordered if agent_id in self._backends and not (agent_id in seen or seen.add(agent_id))]

    def _merge_output(self, state: WorkflowState, record: AgentTaskRecord) -> WorkflowState:
        data = dict(state.data)
        agent_outputs = dict(data.get("agent_outputs") or {})
        agent_outputs[record.task.task_id] = record.output
        data["agent_outputs"] = agent_outputs
        return replace(state, data=data)

    def _save_artifact(self, record: AgentTaskRecord, state: WorkflowState) -> None:
        if self.artifact_store is None:
            return
        self.artifact_store.save(
            ArtifactRecord(
                run_id=state.run_id,
                step_id=f"agent_task_{record.task.task_id}",
                artifact_type=ArtifactType.GENERIC,
                name=f"{record.task.task_id}.json",
                content=record.output,
                metadata={"agent_id": record.assigned_agent_id, "task": record.task.to_dict()},
            )
        )

    def _record(self, event_type: RunEventType, run_id: str, step_id: str, payload: dict[str, Any], state: WorkflowState) -> RunEvent:
        event = RunEvent(event_type=event_type, run_id=run_id, step_id=step_id, payload=payload)
        checkpoint = self.checkpoint_store.save(
            CheckpointRecord(
                run_id=run_id,
                step_id=step_id,
                workflow_state=state.to_dict(),
                metadata={"runtime_event_id": event.event_id, "runtime_event_type": event.event_type.value},
            )
        )
        event.payload.setdefault("checkpoint_id", checkpoint.checkpoint_id)
        self.trace_store.append(event)
        return event

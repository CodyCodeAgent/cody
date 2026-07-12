"""Concurrent multi-agent coordination for runtime workflow teams."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import inspect
from typing import Any, Awaitable, Callable

from .artifact import ArtifactRecord, ArtifactType, InMemoryArtifactStore, SQLiteArtifactStore
from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .control import WorkflowCancelled
from .coordinator import AgentRole, AgentTask, AgentTaskRecord, AgentTaskStatus
from .events import RunEvent, RunEventType
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import WorkflowNode, WorkflowState

AsyncAgentBackend = Callable[
    [AgentTask, WorkflowState],
    Awaitable[dict[str, Any] | None] | dict[str, Any] | None,
]
AsyncReducer = Callable[
    [list[AgentTaskRecord], WorkflowState],
    Awaitable[dict[str, Any] | None] | dict[str, Any] | None,
]


class AsyncMultiAgentCoordinator:
    """Run dependency-ready specialist tasks concurrently."""

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | None = None,
        reducer: AsyncReducer | None = None,
        cancel_event: asyncio.Event | None = None,
        max_concurrency: int = 8,
        default_timeout: float | None = None,
    ):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.artifact_store = artifact_store
        self.reducer = reducer
        self.cancel_event = cancel_event
        self.max_concurrency = max_concurrency
        self.default_timeout = default_timeout
        self._roles: dict[str, AgentRole] = {}
        self._backends: dict[str, AsyncAgentBackend] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def register_agent(self, role: AgentRole, backend: AsyncAgentBackend) -> None:
        self._roles[role.agent_id] = role
        self._backends[role.agent_id] = backend

    def clone(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore,
        artifact_store: InMemoryArtifactStore | SQLiteArtifactStore,
        cancel_event: asyncio.Event | None,
        max_concurrency: int | None = None,
    ) -> "AsyncMultiAgentCoordinator":
        """Create a per-Run coordinator with shared registrations and stores."""

        cloned = AsyncMultiAgentCoordinator(
            trace_store=trace_store,
            checkpoint_store=checkpoint_store,
            artifact_store=artifact_store,
            reducer=self.reducer,
            cancel_event=cancel_event,
            max_concurrency=max_concurrency or self.max_concurrency,
            default_timeout=self.default_timeout,
        )
        cloned._roles = dict(self._roles)
        cloned._backends = dict(self._backends)
        return cloned

    async def run(
        self,
        tasks: list[AgentTask],
        *,
        state: WorkflowState,
        max_rounds: int = 100,
    ) -> tuple[WorkflowState, list[AgentTaskRecord]]:
        self._validate_tasks(tasks)
        records = {task.task_id: AgentTaskRecord(task=task) for task in tasks}
        completed: set[str] = set()
        failed: set[str] = set()
        rounds = 0
        self._checkpoint(
            RunEventType.WORKFLOW_NODE_STARTED,
            state,
            "multi_agent_started",
            {"task_count": len(tasks), "pending_task_ids": [task.task_id for task in tasks]},
        )

        while len(completed) + len(failed) < len(tasks):
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise WorkflowCancelled("Multi-agent coordination cancelled")
            rounds += 1
            if rounds > max_rounds:
                raise RuntimeError(
                    f"Multi-agent coordination exceeded max_rounds={max_rounds}"
                )
            self._skip_blocked_dependencies(tasks, records, completed, failed)
            failed.update(
                task_id
                for task_id, record in records.items()
                if record.status == AgentTaskStatus.SKIPPED
            )
            ready = [
                task
                for task in tasks
                if records[task.task_id].status == AgentTaskStatus.PENDING
                and all(dependency in completed for dependency in task.depends_on)
            ]
            if not ready:
                if len(completed) + len(failed) == len(tasks):
                    break
                raise RuntimeError("Multi-agent coordination deadlocked on dependencies")

            outcomes = await self._run_ready_tasks(ready, records, state)
            for task_id in sorted(outcomes):
                record = outcomes[task_id]
                records[task_id] = record
                if record.status == AgentTaskStatus.COMPLETED:
                    completed.add(task_id)
                    state = self._merge_output(state, record)
                    self._save_artifact(record, state)
                else:
                    failed.add(task_id)
            self._checkpoint(
                RunEventType.WORKFLOW_BATCH_COMPLETED,
                state,
                f"multi_agent_round_{rounds:06d}",
                {
                    "completed_task_ids": sorted(completed),
                    "failed_task_ids": sorted(failed),
                    "pending_task_ids": sorted(
                        task.task_id
                        for task in tasks
                        if records[task.task_id].status == AgentTaskStatus.PENDING
                    ),
                },
            )

        ordered = [records[task.task_id] for task in tasks]
        if self.reducer is not None:
            reduced = self.reducer(ordered, state)
            if inspect.isawaitable(reduced):
                reduced = await reduced
            state = replace(state, data={**state.data, **(reduced or {})})
        self._checkpoint(
            RunEventType.WORKFLOW_NODE_COMPLETED,
            state,
            "multi_agent_completed",
            {"tasks": [record.to_dict() for record in ordered]},
        )
        return state, ordered

    async def _run_ready_tasks(
        self,
        tasks: list[AgentTask],
        records: dict[str, AgentTaskRecord],
        state: WorkflowState,
    ) -> dict[str, AgentTaskRecord]:
        running = {
            task.task_id: asyncio.create_task(
                self._run_task(task, records[task.task_id], state),
                name=f"agent-task-{state.run_id}-{task.task_id}",
            )
            for task in tasks
        }
        gather = asyncio.gather(*running.values())
        if self.cancel_event is None:
            results = await gather
        else:
            cancel_wait = asyncio.create_task(self.cancel_event.wait())
            done, _ = await asyncio.wait(
                {gather, cancel_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_wait in done and self.cancel_event.is_set():
                gather.cancel()
                await asyncio.gather(gather, return_exceptions=True)
                raise WorkflowCancelled("Multi-agent tasks cancelled")
            cancel_wait.cancel()
            await asyncio.gather(cancel_wait, return_exceptions=True)
            results = await gather
        return {
            task.task_id: result
            for task, result in zip(tasks, results, strict=True)
        }

    async def _run_task(
        self,
        task: AgentTask,
        record: AgentTaskRecord,
        state: WorkflowState,
    ) -> AgentTaskRecord:
        candidates = self._candidate_agent_ids(task)
        if not candidates:
            return record.skip("No registered agent satisfies task requirements")
        max_attempts = max(
            1,
            int(task.metadata.get("max_attempts", len(candidates))),
        )
        timeout_value = task.metadata.get("timeout_seconds", self.default_timeout)
        timeout = float(timeout_value) if timeout_value is not None else None
        backoff = max(0.0, float(task.metadata.get("retry_backoff_seconds", 0.0)))
        last_error = "All candidate agents failed"
        current = record
        for attempt in range(max_attempts):
            agent_id = candidates[attempt % len(candidates)]
            current = current.start(agent_id)
            self._append_event(
                RunEventType.WORKFLOW_NODE_STARTED,
                state.run_id,
                f"agent_task_{task.task_id}_attempt_{attempt + 1}",
                {
                    "task": task.to_dict(),
                    "agent": self._roles[agent_id].to_dict(),
                    "attempt": attempt + 1,
                },
            )
            try:
                async with self._semaphore:
                    value = self._backends[agent_id](task, state)
                    awaitable = value if inspect.isawaitable(value) else _immediate(value)
                    if timeout is not None and timeout > 0:
                        output = await asyncio.wait_for(awaitable, timeout=timeout)
                    else:
                        output = await awaitable
            except Exception as exc:
                last_error = str(exc)
                current = current.fail(last_error)
                self._append_event(
                    RunEventType.WORKFLOW_NODE_RETRYING,
                    state.run_id,
                    f"agent_task_{task.task_id}_failed_{attempt + 1}",
                    {
                        "task_id": task.task_id,
                        "agent_id": agent_id,
                        "attempt": attempt + 1,
                        "error": last_error,
                    },
                )
                if backoff and attempt + 1 < max_attempts:
                    await asyncio.sleep(backoff * (attempt + 1))
                continue
            completed = current.complete(output or {})
            self._append_event(
                RunEventType.WORKFLOW_NODE_COMPLETED,
                state.run_id,
                f"agent_task_{task.task_id}_completed",
                completed.to_dict(),
            )
            return completed
        return current.fail(last_error)

    def _candidate_agent_ids(self, task: AgentTask) -> list[str]:
        ordered = [
            *([task.preferred_agent_id] if task.preferred_agent_id else []),
            *task.fallback_agent_ids,
            *[
                agent_id
                for agent_id, role in self._roles.items()
                if task.required_capabilities.issubset(role.capabilities)
            ],
        ]
        seen: set[str] = set()
        return [
            agent_id
            for agent_id in ordered
            if agent_id in self._backends
            and not (agent_id in seen or seen.add(agent_id))
        ]

    def _skip_blocked_dependencies(
        self,
        tasks: list[AgentTask],
        records: dict[str, AgentTaskRecord],
        completed: set[str],
        failed: set[str],
    ) -> None:
        for task in tasks:
            record = records[task.task_id]
            if record.status != AgentTaskStatus.PENDING:
                continue
            blocked = [dependency for dependency in task.depends_on if dependency not in completed]
            if any(dependency in failed for dependency in blocked):
                records[task.task_id] = record.skip(
                    f"Dependency failed or skipped: {blocked}"
                )

    def _validate_tasks(self, tasks: list[AgentTask]) -> None:
        task_ids = [task.task_id for task in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Multi-agent task ids must be unique")
        known = set(task_ids)
        for task in tasks:
            missing = [dependency for dependency in task.depends_on if dependency not in known]
            if missing:
                raise ValueError(
                    f"Agent task {task.task_id} has unknown dependencies: {missing}"
                )

    def _merge_output(
        self,
        state: WorkflowState,
        record: AgentTaskRecord,
    ) -> WorkflowState:
        data = dict(state.data)
        outputs = dict(data.get("agent_outputs") or {})
        outputs[record.task.task_id] = record.output
        data["agent_outputs"] = outputs
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
                metadata={
                    "agent_id": record.assigned_agent_id,
                    "task": record.task.to_dict(),
                },
            )
        )

    def _append_event(
        self,
        event_type: RunEventType,
        run_id: str,
        step_id: str,
        payload: dict[str, Any],
    ) -> None:
        self.trace_store.append(
            RunEvent(event_type, run_id=run_id, step_id=step_id, payload=payload)
        )

    def _checkpoint(
        self,
        event_type: RunEventType,
        state: WorkflowState,
        step_id: str,
        payload: dict[str, Any],
    ) -> None:
        event = RunEvent(
            event_type,
            run_id=state.run_id,
            step_id=step_id,
            payload=payload,
        )
        checkpoint = self.checkpoint_store.save(
            CheckpointRecord(
                run_id=state.run_id,
                step_id=step_id,
                workflow_state=state.to_dict(),
                child_run_ids=list(state.data.get("child_run_ids", [])),
                metadata={
                    "runtime_event_id": event.event_id,
                    "runtime_event_type": event.event_type.value,
                    "multi_agent_safe_boundary": True,
                },
            )
        )
        event.payload.setdefault("checkpoint_id", checkpoint.checkpoint_id)
        self.trace_store.append(event)


def async_multi_agent_node_handler(coordinator: AsyncMultiAgentCoordinator):
    """Create a workflow handler for declarative ``agent_team`` nodes."""

    async def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        raw_tasks = node.metadata.get("agent_tasks") or []
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise ValueError(f"Agent team node has no agent_tasks: {node.node_id}")
        tasks = [_agent_task_from_dict(task) for task in raw_tasks]
        next_state, records = await coordinator.run(
            tasks,
            state=state,
            max_rounds=int(node.metadata.get("max_rounds", 100)),
        )
        return {
            "agent_outputs": next_state.data.get("agent_outputs", {}),
            "agent_task_records": [record.to_dict() for record in records],
        }

    return handler


def _agent_task_from_dict(data: dict[str, Any]) -> AgentTask:
    return AgentTask.create(
        str(data["prompt"]),
        task_id=data.get("task_id"),
        required_capabilities=set(data.get("required_capabilities") or []),
        depends_on=tuple(data.get("depends_on") or ()),
        preferred_agent_id=data.get("preferred_agent_id"),
        fallback_agent_ids=tuple(data.get("fallback_agent_ids") or ()),
        metadata=dict(data.get("metadata") or {}),
    )


async def _immediate(value: Any) -> Any:
    return value

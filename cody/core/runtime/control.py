"""Workflow control signals for pause/cancel orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock


class WorkflowPaused(RuntimeError):
    """Raised internally when a workflow pauses at a node boundary."""


class WorkflowCancelled(RuntimeError):
    """Raised internally when a workflow is cancelled at a node boundary."""


class WorkflowWaiting(RuntimeError):
    """Raised internally when a workflow waits for an external result."""


@dataclass
class WorkflowControlState:
    """Thread-safe control flags checked by workflow executors at node boundaries."""

    _paused_runs: set[str] = field(default_factory=set)
    _cancelled_runs: set[str] = field(default_factory=set)
    _pause_before_nodes: dict[str, set[str]] = field(default_factory=dict)
    _cancel_before_nodes: dict[str, set[str]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def request_pause(self, run_id: str, *, before_node_id: str | None = None) -> None:
        with self._lock:
            if before_node_id is None:
                self._paused_runs.add(run_id)
            else:
                self._pause_before_nodes.setdefault(run_id, set()).add(before_node_id)

    def clear_pause(self, run_id: str) -> None:
        with self._lock:
            self._paused_runs.discard(run_id)
            self._pause_before_nodes.pop(run_id, None)

    def request_cancel(self, run_id: str, *, before_node_id: str | None = None) -> None:
        with self._lock:
            if before_node_id is None:
                self._cancelled_runs.add(run_id)
            else:
                self._cancel_before_nodes.setdefault(run_id, set()).add(before_node_id)

    def clear_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled_runs.discard(run_id)
            self._cancel_before_nodes.pop(run_id, None)

    def should_pause(self, run_id: str, node_id: str | None = None) -> bool:
        with self._lock:
            if run_id in self._paused_runs:
                return True
            return node_id is not None and node_id in self._pause_before_nodes.get(run_id, set())

    def should_cancel(self, run_id: str, node_id: str | None = None) -> bool:
        with self._lock:
            if run_id in self._cancelled_runs:
                return True
            return node_id is not None and node_id in self._cancel_before_nodes.get(run_id, set())

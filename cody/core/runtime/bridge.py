"""Adapters from legacy runner stream events to canonical RunEvent objects."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast

from .events import RunEvent, RunEventType


_LEGACY_EVENT_MAP = {
    "session_start": RunEventType.SESSION_STARTED,
    "thinking": RunEventType.MODEL_THINKING_DELTA,
    "text_delta": RunEventType.MODEL_TEXT_DELTA,
    "tool_call": RunEventType.TOOL_CALL_STARTED,
    "tool_result": RunEventType.TOOL_CALL_COMPLETED,
    "prune": RunEventType.CONTEXT_PRUNED,
    "compact": RunEventType.CONTEXT_COMPACTED,
    "done": RunEventType.RUN_COMPLETED,
    "cancelled": RunEventType.RUN_CANCELLED,
    "circuit_breaker": RunEventType.CIRCUIT_BREAKER_TRIGGERED,
    "retry": RunEventType.MODEL_RETRYING,
    "interaction_request": RunEventType.HUMAN_INPUT_REQUESTED,
    "user_input_received": RunEventType.USER_INPUT_RECEIVED,
}


def stream_event_to_run_event(
    event: Any,
    *,
    run_id: str | None = None,
    step_id: str | None = None,
    parent_event_id: str | None = None,
    event_scope: str = "run",
) -> RunEvent:
    """Convert a legacy ``runner.StreamEvent`` to the canonical event envelope.

    ``event_scope="step"`` is used when an AgentRunner is embedded in a
    workflow node.  In that mode the legacy terminal events describe the model
    step, not the owning runtime run.
    """

    if event_scope not in {"run", "step"}:
        raise ValueError(f"Unsupported runtime event scope: {event_scope}")

    legacy_type = getattr(event, "event_type", type(event).__name__)
    event_type = _LEGACY_EVENT_MAP.get(legacy_type, RunEventType.RUN_FAILED)
    if event_scope == "step":
        if event_type == RunEventType.RUN_COMPLETED:
            event_type = RunEventType.MODEL_COMPLETED
        elif event_type in {RunEventType.RUN_CANCELLED, RunEventType.RUN_FAILED}:
            event_type = RunEventType.MODEL_FAILED
    payload = _payload_for_event(event)
    payload.setdefault("legacy_event_type", legacy_type)
    if event_scope != "run":
        payload.setdefault("event_scope", event_scope)

    return RunEvent(
        event_type=event_type,
        payload=payload,
        run_id=run_id,
        step_id=step_id,
        parent_event_id=parent_event_id,
        source_event=event,
    )


def run_event_to_stream_event(event: RunEvent) -> Any:
    """Return the transient legacy event carried by a live canonical event."""

    if event.source_event is None:
        raise ValueError(
            "Persisted RunEvent has no live StreamEvent compatibility object"
        )
    return event.source_event


def _payload_for_event(event: Any) -> dict[str, Any]:
    if is_dataclass(event):
        raw = asdict(cast(Any, event))
    elif hasattr(event, "__dict__"):
        raw = dict(vars(event))
    else:
        raw = {"value": str(event)}

    return _json_safe(raw)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if is_dataclass(value):
        return _json_safe(asdict(cast(Any, value)))
    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict())
        except TypeError:
            pass
    return str(value)

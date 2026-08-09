# Runtime Core Iteration 002 — AgentRunner TraceStore Integration

## Goal

Move canonical runtime events from a passive bridge into the actual `AgentRunner` execution path.

## Implemented

- Added optional `trace_store` injection to `AgentRunner`.
- Added `AgentRunner.trace_store` for consumers that need the canonical runtime timeline.
- Added `_record_stream_event()` so legacy `StreamEvent` objects are converted and appended as `RunEvent` objects.
- Added canonical runtime run ids for `run_stream()` and stable session-scoped run ids for `run_stream_with_session()`.
- Added monotonic step ids for recorded stream events.
- Recorded `SessionStartEvent` and session pre-compaction events outside the inner `run_stream()` path.
- Added tests for direct AgentRunner TraceStore recording and property exposure.

## Reflection

The previous iteration only proved the canonical event model existed. This iteration makes `AgentRunner` own a TraceStore and record stream events without changing the public stream API. That keeps current CLI/Web/SDK behavior intact while moving the internals toward durable trace/replay infrastructure.

## Next Point

Promote run/step identity into first-class runtime data models, then persist trace events beyond memory.

# Runtime Core Iteration 003 — Durable Run/Step Models and SQLite TraceStore

## Goal

Turn runtime traces from process-local telemetry into durable data that can be inspected after the process exits.

## Implemented

- Added first-class `RunRecord` with lifecycle status, session/workflow/project metadata, timestamps, and immutable transition helpers.
- Added first-class `StepRecord` with step type, lifecycle status, parent/node/agent references, artifact refs, checkpoint refs, and immutable start/complete/fail helpers.
- Added `RunEvent.from_dict()` for durable event rehydration.
- Added `SQLiteTraceStore` with an append-only `runtime_events` table and indexes for run timelines and event type queries.
- Updated runtime exports and `cody.core` lazy exports for the new durable runtime primitives.
- Updated `AgentRunner` typing so it can accept either in-memory or SQLite trace stores.
- Added tests for event round-trip, SQLite persistence across store instances, and immutable run/step transitions.

## Reflection

This moves the runtime from "we can observe events while the process is alive" to "we can keep a canonical timeline and re-open it later." It is still not full checkpoint/replay, but persistent trace storage is a necessary prerequisite for both.

## Next Point

Introduce a checkpoint store that records workflow state, message state, and file/artifact references per step.

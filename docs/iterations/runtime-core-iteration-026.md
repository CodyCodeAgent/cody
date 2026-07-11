# Runtime Core Iteration 026: Replay, Debugger, and Timeline API

## Implemented

- Added `TimelineAPI` as a read-only inspection layer over trace, checkpoint, and artifact stores.
- Added `TimelineItem`, `RunTimeline`, and `DebugFrame` records for UI/debugger-friendly views of runtime execution.
- Implemented chronological run timeline assembly from `RunEvent`s, with checkpoint lookup through event `checkpoint_id` payloads.
- Linked step artifacts and checkpoint artifact refs into timeline items so quality reports, tool outputs, and agent outputs can be inspected next to events.
- Added debugger frame lookup by timeline index, event replay export up to a specific index, and full timeline export.

## Reflection

The runtime can now explain what happened: a UI, CLI, or debugger can render events, checkpoint state, artifacts, and replay slices without coupling to a specific executor. The next gap is a user-facing CLI/TUI/Web API layer that exposes these primitives as commands/endpoints instead of Python-only APIs.

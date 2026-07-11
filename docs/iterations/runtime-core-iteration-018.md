# Runtime Core Iteration 018 — Workflow Pause and Cancel Signals

## Goal

Add explicit workflow control signals so intentional pause/cancel operations are not represented as workflow failures.

## Implemented

- Added `WorkflowControlState` with run-level and node-boundary pause/cancel requests.
- Added `WorkflowPaused` and `WorkflowCancelled` control exceptions.
- Added canonical `workflow.paused` and `workflow.cancelled` runtime event types.
- Wired `WorkflowExecutor` and `AsyncWorkflowExecutor` to check control signals before executing each node.
- Pause/cancel now records control events instead of `workflow.failed` events.
- Wired `WorkflowRunManager` to expose `request_pause()`, `clear_pause()`, `request_cancel()`, and `clear_cancel()` helpers.
- Manager transitions runs to `PAUSED` or `CANCELLED` rather than `FAILED` when control signals fire.
- Added tests for sync pause/resume, sync cancel, and async pause.

## Reflection

Pause/cancel are now explicit lifecycle controls rather than accidental max-step failures. This unlocks durable human-in-the-loop and long-running workflows because products can pause at node boundaries, inspect state, then resume from the latest checkpoint. The remaining gap is durable approval queues that use `WAITING` state and external approval results instead of direct callbacks.

## Next Point

Implement a durable approval request/store system and wire human approval nodes into `WAITING` state plus resume-after-approval semantics.

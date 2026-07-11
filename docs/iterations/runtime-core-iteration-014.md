# Runtime Core Iteration 014 — Workflow Resume from Checkpoints

## Goal

Turn checkpoint persistence into an actual recovery primitive by allowing workflow executors to resume from saved workflow state.

## Implemented

- Added `workflow.resumed` to the canonical runtime event types.
- Added `WorkflowState.from_dict()` so persisted checkpoint state can be rehydrated safely.
- Added `WorkflowExecutor.resume()` to continue a compiled workflow from a `CheckpointRecord`.
- Added `AsyncWorkflowExecutor.resume()` with the same checkpoint validation and continuation behavior for async handlers.
- Resume records a `workflow.resumed` event linked to the source checkpoint before continuing execution.
- Added validation for empty checkpoint state, workflow id mismatches, and invalid current nodes.
- Added tests covering sync resume, async resume, and invalid checkpoint protection.

## Reflection

This changes checkpoints from passive audit artifacts into active recovery boundaries. A node-completed checkpoint can now resume at the next node without replaying completed work. The remaining gap is a higher-level run manager that chooses the latest checkpoint by run id and exposes pause/resume/fork operations as product APIs.

## Next Point

Build a `WorkflowRunManager` that owns stores, resolves latest checkpoints, and exposes start/resume/fork helpers around sync and async executors.

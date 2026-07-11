# Runtime Core Iteration 004 — Checkpoint Store

## Goal

Add durable state snapshots so runtime traces can become recoverable executions rather than only observable timelines.

## Implemented

- Added `CheckpointRecord` for step-boundary snapshots containing workflow state, message state, artifact/file refs, child run ids, pending approvals, budget state, metadata, and parent checkpoint links.
- Added `InMemoryCheckpointStore` for ephemeral runs and tests.
- Added `SQLiteCheckpointStore` with a `runtime_checkpoints` table and run/step indexes.
- Exported checkpoint primitives from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests for checkpoint round-trip, in-memory latest/get/list behavior, and SQLite persistence across store instances.

## Reflection

Trace events explain what happened. Checkpoints preserve enough state to resume or fork execution later. This is still not wired into `AgentRunner` step boundaries, but the durable storage contract now exists.

## Next Point

Wire checkpoint saving into `AgentRunner.run_stream()` at safe step boundaries and link checkpoint ids back onto runtime step metadata.

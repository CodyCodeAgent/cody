# Runtime Core Iteration 016 — Run and Step Registry

## Goal

Add a queryable registry for current run and step status so product/API layers do not have to infer lifecycle state by scanning traces and checkpoints.

## Implemented

- Added `RunRecord.from_dict()` and `StepRecord.from_dict()` for registry persistence.
- Added `InMemoryRunStore` for local/test run and step status tracking.
- Added `SQLiteRunStore` with durable `runtime_runs` and `runtime_steps` tables and status/run indexes.
- Added run and step save/get/list APIs for both stores.
- Wired `WorkflowRunManager` to own a run store and update run status around start/resume success and failure.
- `fork_from_checkpoint()` now records forked run lineage in the run store.
- Exported run store implementations from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests for in-memory registry behavior, SQLite persistence, manager run status transitions, and forked run records.

## Reflection

The runtime now has a current-state index in addition to append-only traces and recovery checkpoints. This is still run-level integration: executor-emitted workflow nodes are not yet mirrored into `StepRecord`s automatically. The next step is step lifecycle instrumentation so every workflow node has a durable step status row.

## Next Point

Wire `WorkflowExecutor` and `AsyncWorkflowExecutor` to write `StepRecord`s for workflow node start/completion/failure, including checkpoint ids and node ids.

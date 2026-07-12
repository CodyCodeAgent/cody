# Runtime Core Iteration 034: Durable Retry, Fork, and Tool Idempotency

## Implemented

- Added `CodyRuntime.retry()` for failed/cancelled runs using the latest or an
  explicitly selected checkpoint.
- Added `CodyRuntime.fork()` for starting a child Run from any historical
  checkpoint.
- Preserved source Run metadata, workflow definition, workdir, project/session,
  branch, and parent Run/checkpoint lineage on forks.
- Added canonical `run.retrying` and `run.forked` lifecycle events.
- Added Runtime Tool Registry integration to `CodyRuntime`.
- Added durable deterministic tool execution receipts to prevent duplicate side
  effects after retry or checkpoint rollback.
- Added in-process per-key locking so concurrent callers in one Runtime cannot
  race the same idempotency key.
- Added optional idempotency-key injection for external APIs through
  `ToolSpec.metadata['idempotency_arg']`.
- Added canonical tool started/completed events with receipt and replay metadata.

## Recovery Semantics

- Default tool keys include `run_id`, workflow `node_id`, tool name, and canonical
  JSON arguments.
- An explicit workflow-node `idempotency_key` can intentionally deduplicate
  across Runs.
- A receipt is written only after successful tool completion. External systems
  requiring crash-safe exactly-once behavior should accept the injected key and
  enforce idempotency on their side.

## Verification

- Verified failed Run retry in a separate Runtime instance backed by reopened
  SQLite stores.
- Verified historical checkpoint fork executes only the remaining workflow node
  and preserves parent lineage.
- Verified rollback to a checkpoint before a completed side-effect tool replays
  the durable receipt and does not call the handler twice.
- Full core and Web suite: 1134 passed.

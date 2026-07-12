# Runtime Core Iteration 035: Concurrent Workflows and Agent Teams

## Implemented

- Added `AsyncWorkflowScheduler` for true concurrent ready-batch execution.
- Added deterministic fan-out/fan-in JOIN semantics.
- Added async fallback and nested-workflow execution.
- Added per-node timeout, bounded retries, retry backoff, global max steps, and
  max concurrency.
- Added cancellation propagation that cancels active branch tasks.
- Added safe batch-boundary checkpoints with resumable ready-node state.
- Added deterministic output merging with conflict detection and explicit
  `last_write_wins` / `namespace` alternatives.
- Integrated graph auto-routing into `WorkflowRunManager` and `CodyRuntime`.
- Added `AsyncMultiAgentCoordinator` for concurrent dependency-aware agent tasks.
- Added preferred/fallback agent routing, per-task timeout/attempt limits,
  partial-failure propagation, async reducer support, and task artifacts.
- Added declarative `agent_team` workflow nodes.

## Verification

- Proved branch concurrency using a synchronization barrier that cannot pass
  under sequential execution.
- Verified JOIN receives both branch outputs in deterministic order.
- Verified timeout/retry bounds, fallback routing, nested workflows with
  `max_concurrency=1`, active-task cancellation, merge conflict rejection, and
  resume from the last safe batch checkpoint.
- Proved independent agent tasks run concurrently before dependent review work.
- Verified fallback agent selection, partial failure and dependent skip,
  cancellation propagation, per-task artifacts, and `CodyRuntime` agent-team
  integration.
- Full core and Web suite: 1146 passed before the final nested-workflow test;
  the added nested test also passes.

## Reflection

The scheduler now implements actual concurrency rather than only graph
semantics. Checkpoints are intentionally committed at batch boundaries: a crash
inside a batch replays that batch, while tool idempotency receipts protect
completed side effects. Model/agent steps remain at-least-once unless their
backends implement resumable or idempotent execution.

# Runtime Core Iteration 023: Graph Scheduler

## Implemented

- Added `WorkflowScheduler` for non-linear workflow graphs that need deterministic fan-out/fan-in semantics beyond the single-cursor executor.
- Supported `PARALLEL` edges by queueing all selected branch targets, and `JOIN` edges by holding join targets until all join-source nodes complete.
- Supported `FALLBACK` edges by routing handler failures to fallback targets while recording the failed node id in workflow state.
- Supported `NESTED_WORKFLOW` nodes through inline compiled workflows or registered child workflows, with child run ids persisted in state/checkpoints.
- Kept the scheduler on the same runtime primitives as the executor: `RunEvent`, `CheckpointRecord`, optional run-store step records, and control-state pause/cancel checks.

## Reflection

This closes the biggest orchestration gap left by the linear executor: a workflow can now model branch fan-out, explicit joins, failure recovery paths, and child workflow composition. The implementation stays deterministic and single-process first; the next hardening step is to map the ready queue to a real concurrent worker pool with per-node timeouts and cancellation propagation.

# Runtime Core Iteration 011 — High-level Workflow APIs

## Goal

Expose product-level workflow entrypoints so callers can run built-in templates without manually wiring templates, adapters, executor, stores, and conditions.

## Implemented

- Added `run_coding_workflow()`.
- Added `run_refactor_workflow()`.
- High-level APIs accept backend callbacks for agent execution, tool calls, and human approval.
- APIs support injected trace and checkpoint stores.
- Added default condition handlers for `tests_failed` and `review_requested_changes` based on workflow state.
- Exported high-level APIs from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests for happy-path coding workflow execution, coding fix loop execution, and refactor workflow execution.

## Reflection

The runtime is now usable from a single API call for built-in workflows, while still staying backend-neutral. The next step is to provide concrete backends for Cody's own AgentRunner, tool registry, and approval mechanisms.

## Next Point

Implement Cody-native backend adapters that connect these high-level workflow APIs to `AgentRunner`, registered tools, and interaction/approval queues.

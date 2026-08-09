# Runtime Core Iteration 019 — Durable Approval Queue and WAITING State

## Goal

Move human approval nodes from direct callback decisions to durable approval requests that put workflow runs into an explicit `WAITING` lifecycle state.

## Implemented

- Added `ApprovalRequestRecord` and `ApprovalStatus` for pending/approved/rejected/expired approvals.
- Added `InMemoryApprovalStore` and `SQLiteApprovalStore` with save/get/list operations.
- Added `WorkflowWaiting` and canonical `workflow.waiting` runtime event type.
- Added `StepStatus.WAITING` and a `StepRecord.wait()` transition.
- Added `queued_human_approval_node_handler()` that persists a pending approval request and raises `WorkflowWaiting`.
- Wired sync and async executors to record waiting events and waiting step status without marking the run as failed.
- Wired `WorkflowRunManager` to transition runs into `RunStatus.WAITING` when approval waits occur.
- Exported approval primitives and queued approval handler from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests for in-memory approval state, SQLite approval persistence, and workflow WAITING behavior.

## Reflection

Human approval is now a durable queue primitive rather than a synchronous callback only. This is the foundation for approval APIs/UI: a workflow can stop at an approval node, persist a pending approval request, expose it externally, and later resume after a decision. The remaining gap is resume-after-approval wiring that consumes approved/rejected records and continues or routes fallback paths.

## Next Point

Implement an artifact store for plans, diffs, test reports, reviews, and approval/context artifacts, then link artifacts to run events, checkpoints, and step records.

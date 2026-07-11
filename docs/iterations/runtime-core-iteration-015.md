# Runtime Core Iteration 015 — Workflow Run Manager

## Goal

Lift workflow execution from low-level executor calls into a reusable run-management service that owns trace/checkpoint stores and exposes start/resume/fork helpers.

## Implemented

- Added `WorkflowRunManager` as the orchestration facade for compiled workflows.
- Added sync `start()`, `resume_latest()`, and `resume_from_checkpoint()` helpers.
- Added async `start_async()`, `resume_latest_async()`, and `resume_from_checkpoint_async()` helpers.
- Added `fork_from_checkpoint()` to create a new run lineage from an existing checkpoint.
- Added convenience accessors for run events, all checkpoints, latest checkpoint lookup, and checkpoint id lookup.
- Exported `WorkflowRunManager` and `WorkflowRunManagerError` from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests covering sync manager start/resume, async manager resume, checkpoint lookup errors, and fork metadata/lineage.

## Reflection

The runtime now has a service-level entry point instead of requiring callers to manually assemble stores, executors, and latest-checkpoint resolution. This is still not a full production run registry: current run status, pause/cancel signals, ownership, and step indexes need first-class storage next.

## Next Point

Implement a durable run/step registry that records current run status, active checkpoint ids, step statuses, failures, ownership metadata, and timestamps.

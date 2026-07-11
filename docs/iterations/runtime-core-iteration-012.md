# Runtime Core Iteration 012 — Cody-native Workflow Backends

## Goal

Provide reusable backend builders so high-level runtime workflows can connect to Cody execution concepts without each caller writing glue code.

## Implemented

- Added `agent_runner_backend()` backed by `AgentRunner.run_sync()`.
- Added `tool_mapping_backend()` for mapping workflow tool nodes to concrete callable tool backends.
- Added `static_approval_backend()` for deterministic trusted/local approval flows.
- Exported backend builders from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests running `run_coding_workflow()` with a fake AgentRunner backend, tool mapping backend, and static approval backend.
- Added missing tool validation coverage.

## Reflection

This is the first concrete bridge from high-level workflows to Cody runtime execution. It is still synchronous and deliberately simple. The next step is an async/streaming AgentRunner backend that preserves streamed model/tool events inside workflow execution.

## Next Point

Implement async workflow execution and an AgentRunner streaming backend that forwards `run_stream()` events into workflow traces.

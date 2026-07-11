# Runtime Core Iteration 013 — Async Workflow Execution and Streaming Agent Backend

## Goal

Move beyond synchronous workflow glue by adding an async execution path and a streaming AgentRunner backend that can preserve stream-level telemetry inside runtime traces.

## Implemented

- Added `AsyncWorkflowExecutor` with async-aware node handlers and async-aware condition handlers.
- Added `AsyncWorkflowExecutionError` mirroring the synchronous executor's control-flow failures.
- Added `agent_runner_streaming_backend()` backed by `AgentRunner.run_stream()`.
- The streaming backend collects streamed event summaries, returns final agent output, and can mirror converted stream events into a provided runtime `TraceStore`.
- Exported async executor and streaming backend from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests for async workflow execution, async conditional edge selection, and streaming AgentRunner backend trace mirroring.

## Reflection

This gives workflows a mature runtime direction: long-lived orchestration can now wait on asynchronous model/tool/human systems instead of forcing everything through blocking sync calls. The streaming backend also starts joining the workflow timeline with underlying agent stream events. The next step is resumable workflow execution from checkpoints so async runs can pause, recover, and continue after process failure.

## Next Point

Implement checkpoint-based workflow resume APIs for both synchronous and asynchronous executors.

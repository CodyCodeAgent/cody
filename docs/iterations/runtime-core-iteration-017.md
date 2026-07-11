# Runtime Core Iteration 017 — Workflow Step Registry Instrumentation

## Goal

Connect workflow node execution to the run/step registry so each workflow node has durable current-state metadata in addition to trace events and checkpoints.

## Implemented

- Added optional run-store injection to `WorkflowExecutor` and `AsyncWorkflowExecutor`.
- Workflow node execution now writes `StepRecord` rows when a node starts.
- Successful node completion updates the same step to completed and attaches the node-completed checkpoint id.
- Handler/condition failures update the step to failed with an error reference before propagating the exception.
- Added node-type to step-type mapping for agent, tool, human approval, checkpoint, and system nodes.
- Wired `WorkflowRunManager` executor factories to pass its run store into sync and async executors.
- Added tests for sync completed steps, failed steps, and async completed steps.

## Reflection

Run status and step status are now first-class current-state indexes. This complements append-only traces: traces explain what happened, checkpoints enable recovery, and run/step registry tells products what is happening now. The next gap is explicit pause/cancel/waiting signals rather than overloading max-step failure as a control mechanism.

## Next Point

Implement workflow control signals: pause, cancel, and waiting states that update `RunRecord`/`StepRecord` without treating intentional pauses as failures.

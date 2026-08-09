# Runtime Core Iteration 007 — Workflow Graph Primitives

## Goal

Introduce explicit workflow graph models so Cody can move beyond linear runner execution toward durable orchestration.

## Implemented

- Added `WorkflowNodeType` and `WorkflowEdgeType` enums.
- Added `WorkflowNode` and `WorkflowEdge` records with JSON-shaped `to_dict()` output.
- Added `WorkflowState` for per-run workflow execution state.
- Added `Workflow` builder with node, edge, conditional edge, entrypoint, and compile methods.
- Added `CompiledWorkflow` for validated immutable graphs with incoming/outgoing edge queries and initial state creation.
- Added graph validation for duplicate nodes, missing edge endpoints, missing entrypoints, and conditional edges without conditions.
- Exported workflow primitives from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added dedicated workflow graph tests.

## Reflection

The runtime now has the static graph shape needed for orchestration, but it does not execute nodes yet. This is the right boundary: execution should use the existing trace/checkpoint stores rather than bypass them.

## Next Point

Implement a workflow executor that traverses `CompiledWorkflow`, emits `RunEvent`s, saves checkpoints, and delegates node execution to agents/tools/human approvals.

# Runtime Core Iteration 010 — Built-in Coding Workflow Templates

## Goal

Provide reusable software-engineering workflow templates so runtime users do not need to hand-build common coding/refactor graphs.

## Implemented

- Added `coding_workflow_template()` for plan → implement → test → fix loop → review → approval.
- Added `refactor_workflow_template()` for analyze → safety tests → refactor → test/fix loop → review.
- Templates are backend-neutral and designed to be executed with workflow node adapters.
- Exported template helpers from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests showing the coding template executes via adapters on the happy path.
- Added tests showing the coding template routes through the fix loop when tests fail.
- Added tests validating the refactor template shape.

## Reflection

This moves the runtime toward product-level workflows rather than only low-level primitives. Templates still need concrete AgentRunner/tool/approval backends, but the orchestration shape is now reusable and testable.

## Next Point

Add concrete AgentRunner-backed workflow adapters and expose a high-level API to run built-in templates against a repository.

# Runtime Core Iteration 022 — Tool Registry, Policy, and Output Artifacts

## Goal

Move workflow tool execution from ad-hoc callbacks toward registered tools with policy checks, argument validation, and artifact-backed outputs.

## Implemented

- Added `ToolSpec` with handler, required args, capabilities, artifact type, and metadata.
- Added `ToolPolicy` with allowlist, denylist, and capability checks.
- Added `ToolExecutionDenied` for policy failures.
- Added `ToolRegistry` for registering and resolving tools.
- Added `registry_tool_backend()` that validates args, enforces policy, invokes tools, and optionally stores tool output as an artifact.
- Exported tool registry primitives from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests for registry execution, artifact output creation, denied tools, missing args, and missing tools.

## Reflection

Tool execution now has a runtime boundary: tools are named, registered, policy-checked, schema-lite validated, and can emit artifacts. This is still not an OS sandbox; the next step is to add stronger sandbox profiles, approval-required tools, timeouts, retries, and command/file-system policy enforcement.

## Next Point

Implement parallel/join/fallback/nested workflow scheduling so richer tool and agent graphs can execute as DAGs instead of a single linear cursor.

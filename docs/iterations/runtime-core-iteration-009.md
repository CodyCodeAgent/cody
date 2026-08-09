# Runtime Core Iteration 009 — Workflow Node Adapters

## Goal

Standardize how workflow nodes delegate to agents, tools, and human approval systems without hard-coding those execution details into `WorkflowExecutor`.

## Implemented

- Added `agent_node_handler()` adapter factory.
- Added `tool_node_handler()` adapter factory.
- Added `human_approval_node_handler()` adapter factory.
- Agent adapter reads prompts from node metadata or workflow state and normalizes string outputs into dict state updates.
- Tool adapter reads tool name and args from node configuration and validates args are dictionaries.
- Human approval adapter reads request metadata and normalizes boolean approvals into workflow state.
- Exported adapter factories from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests showing adapters plugged into `WorkflowExecutor` for agent -> tool -> approval flows.
- Added validation tests for malformed tool and approval nodes.

## Reflection

The executor stays generic, while adapters define stable integration seams for AgentRunner, tool registry calls, and approval queues. This keeps graph traversal independent from concrete execution backends.

## Next Point

Add concrete async adapters for `AgentRunner.run_stream()`, registered tools, and approval queues, then add a built-in coding workflow template.

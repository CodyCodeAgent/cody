# Runtime Core Iteration 006 — Richer AgentRunner Checkpoint Payloads

## Goal

Make AgentRunner checkpoints useful for future recovery by storing more than a checkpoint id and event type.

## Implemented

- Extended `_record_stream_event()` to accept message state, workflow state, artifact refs, file refs, child run ids, and pending approval ids.
- Checkpoints now include the last runtime event payload in workflow state.
- Added lightweight circuit-breaker budget state to each checkpoint.
- Added `_checkpoint_message_state()` to serialize recent message history into JSON-safe checkpoint state.
- Added `_checkpoint_refs_for_event()` to infer tool-call/tool-result artifact refs, file refs for file tools, child-run hints for sub-agent spawning, and pending approval ids for interaction events.
- Updated stream tracing paths to pass message state and inferred refs into checkpoint recording.
- Added tests for rich checkpoint payload capture.

## Reflection

The runtime now has a real path from stream event -> trace event -> checkpoint snapshot with useful recovery hints. The payload is still intentionally conservative; full replay will require exact model/tool state, file snapshots, and child-agent state contracts.

## Next Point

Introduce a workflow graph abstraction with node/edge/state models, then use the runtime stores as the execution substrate.

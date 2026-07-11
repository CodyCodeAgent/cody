# Runtime Core Iteration 005 — AgentRunner Checkpoint Wiring

## Goal

Connect checkpoint storage to the actual AgentRunner stream path so traces can point at recoverable state snapshots.

## Implemented

- Added optional `checkpoint_store` injection to `AgentRunner`.
- Added `AgentRunner.checkpoint_store` property.
- Created a default `InMemoryCheckpointStore` alongside the default `InMemoryTraceStore`.
- Updated `_record_stream_event()` to save a `CheckpointRecord` for each traced stream step when a run id and step id are available.
- Linked the saved checkpoint back into the canonical `RunEvent` payload via `checkpoint_id`.
- Added tests asserting AgentRunner trace events and checkpoints are linked by event id, step id, and checkpoint id.

## Reflection

This is the first real trace-to-recovery link. The checkpoint currently captures event-level workflow metadata rather than full model/tool/message/file state, but every traced step now has a checkpoint handle that future richer snapshots can reuse.

## Next Point

Expand checkpoint payloads with message history, compacted context, tool outputs, file history refs, and child agent state at safe runtime boundaries.

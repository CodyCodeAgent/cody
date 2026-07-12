# Runtime Core Iteration 033: Canonical Runtime Service

## Implemented

- Added `CodyRuntime`, `RuntimeRun`, and `RuntimeRunResult` as the high-level,
  embeddable runtime API.
- Wired Run, Trace, Checkpoint, Artifact, and Approval stores through one
  canonical execution path.
- Added `AgentRunner.run_events()` as the canonical live event stream; retained
  `run_stream()` as a compatibility adapter derived from live `RunEvent` values.
- Added model-step event scoping so embedded AgentRunner completion emits
  `model.completed` instead of prematurely emitting `run.completed`.
- Added cooperative cancellation across model and workflow boundaries.
- Added async lifecycle management for runner-owned MCP/LSP resources.
- Persisted compiled workflow definitions in RunRecord metadata.
- Added durable waiting approval and resume support across separate Runtime
  instances using SQLite checkpoints and stores.
- Exported the new API through `cody`, `cody.sdk`, `cody.core`, and
  `cody.core.runtime`.

## Compatibility

- Existing `StreamEvent`, `AsyncCodyClient`, CLI, TUI, and Web consumers remain
  compatible.
- The transient legacy event carried by a live `RunEvent` is intentionally not
  persisted. Timeline and replay consumers use canonical `RunEvent` data.

## Verification

- Full core and Web test suite: 1128 passed before the canonical direction
  refactor; targeted runtime/runner/SDK regression: 218 passed afterward.
- Real DeepSeek smoke tests validated the complete path from `CodyRuntime`
  through AgentRunner to canonical events and result artifacts.
- Verified that an embedded Agent emits `model.completed` and the owning
  Runtime emits exactly one `run.completed`.
- Verified SQLite approval waiting and checkpoint resume in a new Runtime
  instance.

## Reflection

This iteration establishes the first authoritative vertical runtime path. The
remaining migration work is to move all SDK, CLI, TUI, and Web entrypoints onto
`CodyRuntime`, then extend this same path with concurrent scheduling, quality
repair loops, and production storage backends.

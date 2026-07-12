# Runtime Core Iteration 037: Shared Product Surfaces

## Implemented

- Added stable per-project Runtime storage roots under
  `~/.cody/runtime/<project-id>` with `CODY_RUNTIME_HOME` override support.
- Expanded `RuntimeInterface` with Run detail, Steps, Checkpoints, Artifacts,
  Audit, pagination, and control actions.
- Added CLI groups for Runs, Approvals, Artifacts, Timeline, retry/resume/fork,
  orphan recovery, pause, cancel, and watch.
- Added FastAPI `/runtime/*` endpoints for asynchronous Run start and lifecycle
  control plus shared inspection APIs.
- Added Textual slash commands for shared Runs, Timeline, Approvals, and cancel.
- Added `AsyncCodyClient.get_runtime()` so SDK builder configuration, custom
  tools, hooks, and its AgentRunner can enter the canonical Runtime directly.
- Added SQLite-backed workflow control state for cross-process pause/cancel.
- Added active-batch polling so a CLI cancel can terminate a Run owned by Web.
- Added `CodyRuntime.recover()` for Runs orphaned in `running` after process
  termination.

## Verification

- Verified CLI and Web read the same Run, Step, Timeline, Checkpoint, Artifact,
  and Approval records for one workdir.
- Verified a Web approval decision is visible after reopening stores.
- Verified a control request from a separately opened SQLite bundle cancels an
  active handler and transitions the owning Run to `cancelled`.
- Simulated abrupt process task termination, reopened stores in a new Runtime,
  and recovered from the last scheduler-safe checkpoint.
- Verified TUI `/runs` reads shared durable state.
- Verified SDK `get_runtime()` reuses the configured runner and closes its
  resources exactly once.
- Verified a real DeepSeek Run started through Web reaches `completed` and is
  then read through the CLI from the same project stores.
- Full core and Web suite: 1160 passed.

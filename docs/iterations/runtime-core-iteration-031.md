# Runtime Core Iteration 031: Runtime Audit Trail

## Implemented

- Added `RuntimeAuditRecord` for append-only audit entries over user-facing runtime actions.
- Added `InMemoryRuntimeAuditStore` and `SQLiteRuntimeAuditStore` with actor/action filtering.
- Integrated optional audit writing into `RuntimeInterface.handle()` for successful actions, denied actions, and unknown actions.
- Captured action, actor id, read/write effect, run id, success flag, error, timestamp, and redacted action params.
- Exported audit primitives through `cody.core.runtime` and top-level lazy imports.

## Reflection

Authentication and authorization now leave an auditable trail. This closes the immediate safety gap for CLI/TUI/Web surfaces: product integrations can inspect who attempted which runtime action, whether it succeeded, and which run it targeted without leaking sensitive payload content.

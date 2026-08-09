# Runtime Core Iteration 032: Runtime Store Bundle

## Implemented

- Added `RuntimeStoreBundle` to wire the canonical runtime stores as one cohesive deployment unit.
- Added `RuntimeStoreBundle.in_memory()` for tests, demos, and ephemeral local sessions.
- Added `RuntimeStoreBundle.sqlite(root)` for durable local deployments with trace, checkpoint, artifact, approval, run, and audit SQLite stores.
- Added `RuntimeStoreBundle.interface()` to create a fully wired `RuntimeInterface` with optional action policy.
- Exported the bundle through `cody.core.runtime` and top-level lazy imports.

## Reflection

The runtime no longer requires callers to manually instantiate and thread every store into every service. This improves real product adoption: tests can use one in-memory bundle, while local durable surfaces can point at one directory and get consistent storage for traces, checkpoints, artifacts, approvals, runs, and audits.

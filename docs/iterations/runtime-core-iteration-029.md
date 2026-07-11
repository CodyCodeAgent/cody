# Runtime Core Iteration 029: Runtime Action Authorization

## Implemented

- Added `RuntimeActionPolicy` for authorizing CLI/TUI/Web runtime actions before dispatch.
- Added `RuntimeActionDecision` and `RuntimeActionEffect` so callers can reason about allow/deny decisions and read/write effects.
- Integrated optional action policy checks into `RuntimeInterface.handle()`.
- Updated CLI and Web adapters to pass `actor_id` into the shared runtime interface.
- Added defaults that treat approval decisions and artifact writes as mutating actions requiring an actor id.
- Supported action allowlists, explicit deny lists, and per-actor action allowlists.

## Reflection

The presentation adapters now have a security seam instead of exposing mutating runtime operations blindly. This is still not full authn/authz infrastructure, but it gives product surfaces a deterministic place to enforce least privilege before wiring real identity providers or token validation.

# Runtime Core Iteration 027: CLI/TUI/Web Runtime Interface

## Implemented

- Added `RuntimeInterface` as a dependency-light application service for CLI, TUI, and Web adapters.
- Added `RuntimeAPIResponse` as a stable response envelope with `ok`, `data`, and `error` fields.
- Exposed run listing, timeline export, debugger frame lookup, replay slices, approval listing/approve/reject, artifact listing, and artifact saving through one shared API.
- Added `handle(action, **kwargs)` dispatch so command routers and HTTP handlers can map external actions to the same runtime service methods.
- Kept transport concerns outside the runtime package: no terminal renderer or web framework dependency is required.

## Reflection

This is the thin product-facing seam the runtime needed. The same store-backed interface can now power CLI commands, TUI panels, or Web endpoints consistently. The next hardening pass should add concrete command modules and authentication/authorization around mutating actions such as approval decisions and artifact writes.

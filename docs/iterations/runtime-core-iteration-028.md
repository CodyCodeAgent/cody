# Runtime Core Iteration 028: CLI/TUI/Web Adapters

## Implemented

- Added transport-light adapters on top of `RuntimeInterface` so products can connect concrete surfaces without duplicating runtime plumbing.
- Added `RuntimeCommandRouter` for CLI-style `action key=value` dispatch with JSON-aware argument parsing.
- Added `RuntimeWebRouter` and `RuntimeActionRequest` for framework-agnostic request handling that returns plain dictionaries suitable for HTTP JSON responses.
- Added `RuntimeTUIView` to build dashboard and run-detail view models from the same runtime interface.
- Kept the adapters dependency-free: no terminal framework or HTTP framework is required in core runtime.

## Reflection

The runtime now has concrete seams for CLI, TUI, and Web without committing to a specific presentation framework. The next hardening step is security: mutating actions such as approval decisions and artifact writes need explicit authorization policies before these adapters are exposed to real users.

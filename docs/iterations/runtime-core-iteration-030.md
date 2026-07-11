# Runtime Core Iteration 030: Runtime Token Authentication

## Implemented

- Added `RuntimePrincipal` as the authenticated actor model for runtime surfaces.
- Added `RuntimeTokenAuthority`, a small HMAC token issuer/verifier for local CLI/TUI/Web integration tests and lightweight deployments.
- Added `RuntimeAuthError` for invalid format, invalid signature, invalid payload, and expired token failures.
- Extended `RuntimeActionRequest` and `RuntimeWebRouter` so Web-style requests can provide a token; verified tokens are converted into actor ids before authorization.
- Kept the token layer dependency-free and explicit so production deployments can replace it with an external identity provider later.

## Reflection

The runtime now has both authorization and a minimal authentication seam. This is enough for local and embedded product surfaces, while still leaving room to swap in enterprise identity providers without rewriting runtime actions or stores.

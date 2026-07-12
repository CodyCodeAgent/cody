# Runtime Core Iteration 038 — Canonical Product Surfaces

## Outcome

The default SDK and Web execution paths now create a canonical `CodyRuntime`
Run. CLI and TUI inherit the same behavior through `AsyncCodyClient`.

## Changes

- `AsyncCodyClient.run()` and `stream()` execute through `CodyRuntime.start()`.
- SDK results and stream chunks expose the canonical `run_id`.
- session history, multimodal prompts, tool filters, cancellation, usage, and
  legacy SDK events remain compatible.
- multimodal prompt payloads are stored as recoverable Runtime artifacts.
- Web `/run`, `/run/stream`, project chat WebSocket, and task chat WebSocket
  derive their existing response formats from persisted `RunEvent` records.
- Web-created runs share the same durable per-workdir stores used by CLI/TUI.
- a narrow adapter remains for injected pre-Runtime runner implementations;
  the built-in `AgentRunner` always uses `run_events()` as a workflow step.
- artifact metadata can remain in SQLite while payloads are stored through a
  filesystem or S3-compatible `ObjectStorage` backend.
- `RuntimeStoreBundle.postgres()` provides shared JSONB-backed run, step,
  event, checkpoint, approval, artifact metadata, audit, and control stores for
  multi-process deployments; object payload storage remains independently
  configurable.
- canonical events now produce a shared observability snapshot covering
  duration, event/step/model/tool counts, retries, quality failures,
  checkpoints, artifacts, token usage, and estimated cost. It is exposed by
  the Runtime interface, CLI, and Web API.
- a versioned `RuntimeExtensionRegistry` formalizes tool, skill, model,
  agent backend, workflow node, evaluator, store, auth, and presentation
  extension kinds, including package entry-point discovery.
- all canonical event payloads and audit parameters pass through recursive
  secret redaction before storage, including nested credentials, bearer
  headers, API keys, tokens, passwords, cookies, and common `sk-` values.
- agent questions and CONFIRM-level model tools use deterministic durable
  Approval records: waiting releases the worker, and a new Runtime instance
  resumes after approval. Run records also capture actor/service-account,
  project, model, permission, and budget context; step count, duration, token,
  and cost budgets are enforced at their execution boundaries.

## Verification

- full Python test suite passes.
- Web route and WebSocket suites pass.
- a real DeepSeek streaming SDK run produced a durable run ID, session ID,
  canonical terminal event, usage, and the expected model response.
- a fault-injection test terminates a separate Python process with `os._exit`
  during the second workflow node; a new Runtime process recovers the orphaned
  Run from the last committed SQLite batch and executes only the unfinished node.
- the React Web reference product includes a Runtime console for project-scoped
  Run creation/listing, lifecycle controls, live polling, approvals, metrics,
  timeline, and artifact inspection.

# Runtime Core Iteration 036: Quality Gates and Repair Loops

## Implemented

- Added `AsyncQualityGateRunner` with concurrent sync/async metric evaluation.
- Added first-class `quality_gate` workflow nodes.
- Persisted every decision as canonical events, checkpoints, and REVIEW
  artifacts.
- Added bounded repair-loop routing through fallback and explicit
  `allow_revisit` edges.
- Added `max_repairs` exhaustion that blocks the owning Run.
- Retained global workflow `max_steps` as a second loop guard.
- Added no-shell command evaluators suitable for tests, lint, type checking,
  security scans, and coverage.
- Added a structured diff-risk evaluator.
- Added deterministic workflow state fields for attempts, latest decisions, and
  pass/fail status.

## Verification

- Verified fail → repair → re-evaluate → pass before downstream delivery.
- Verified repair exhaustion produces a failed Run and two decision artifacts.
- Proved independent metrics evaluate concurrently with a synchronization
  barrier.
- Verified command exit status and output capture without shell execution.
- Verified structured diff-risk scoring distinguishes low- and high-risk
  changes.
- Full core and Web suite: 1152 passed.

## Reflection

Quality is now part of workflow control rather than an optional post-processing
helper. Agent-team output, tool artifacts, or ordinary workflow state can feed
the same gate, and a failed decision can trigger a bounded repair path without
special logic in CLI, Web, or SDK consumers.

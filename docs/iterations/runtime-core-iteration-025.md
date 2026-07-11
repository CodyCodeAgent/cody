# Runtime Core Iteration 025: Evaluation and Quality Gates

## Implemented

- Added `QualityGateRunner` for evaluating workflow state before outputs advance to later stages.
- Added `EvaluationMetric`, `EvaluationResult`, `QualityGate`, `QualityGateDecision`, and `QualityGateStatus` as stable quality-gate records.
- Supported named evaluator callbacks that can return booleans, numeric scores, or detailed score dictionaries.
- Implemented weighted aggregate scoring, per-metric thresholds, required metric blocking, warning status for non-blocking metric failures, and `assert_passed()` for hard gates.
- Persisted quality decisions through `RunEvent`, `CheckpointRecord`, and optional review artifacts.

## Reflection

Quality gates make the runtime safer: multi-agent or workflow outputs can now be measured and blocked before they mutate the repo or progress to deployment-like stages. The next gap is replay/debugger/timeline APIs so these decisions, checkpoints, and artifacts can be inspected and replayed in chronological order.

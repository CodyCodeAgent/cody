# Runtime Core Iteration 020 — Resume After Approval

## Goal

Allow workflows that are waiting on durable approval requests to resume after an external approval or rejection is recorded.

## Implemented

- Added `approve()` and `reject()` convenience methods to in-memory and SQLite approval stores.
- Updated `queued_human_approval_node_handler()` to reuse existing approval requests for the same run/node on resume.
- Pending approval records continue to raise `WorkflowWaiting` without creating duplicates.
- Approved records return approval response data so the approval node can complete on resume.
- Rejected/expired records return negative approval state so workflows can route through conditions or fallback paths later.
- Added tests for waiting, approving, and resuming the same workflow without duplicate approval requests.

## Reflection

Approval is now a full wait/resume boundary: a workflow can pause at a human approval node, expose a durable approval id, receive an external decision, and continue from the original checkpoint. Rejection routing still needs richer fallback scheduler semantics, but the data path is now present.

## Next Point

Implement an artifact store for plans, diffs, test reports, reviews, and approval/context artifacts, then link artifacts to run events, checkpoints, and step records.

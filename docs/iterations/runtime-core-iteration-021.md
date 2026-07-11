# Runtime Core Iteration 021 — Artifact Store

## Goal

Add a durable artifact store for workflow outputs such as plans, diffs, test reports, reviews, approvals, context packs, and tool outputs.

## Implemented

- Added `ArtifactType` for common workflow artifact categories.
- Added `ArtifactRecord` linked to run, step, checkpoint, event, and optional parent artifact lineage.
- Added `InMemoryArtifactStore` with save/get/list filtering by run, step, and artifact type.
- Added `SQLiteArtifactStore` with durable `runtime_artifacts` table and run/type plus step indexes.
- Exported artifact primitives from `cody.core.runtime` and top-level `cody.core` lazy imports.
- Added tests for artifact record round-trip, in-memory filtering, and SQLite persistence.

## Reflection

Artifacts now provide a durable home for workflow outputs instead of burying plans, diffs, test reports, and reviews inside opaque state dictionaries. This is the substrate for quality gates, timeline/debugger views, and multi-agent handoff. The next step is to wire tool outputs and workflow node outputs into artifacts automatically.

## Next Point

Implement Tool Registry + Policy/Sandbox, then connect tool execution outputs to `ArtifactStore` records.

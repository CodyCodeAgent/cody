# Runtime Core Iteration 001 — Canonical Events and Trace Foundation

## Goal

Start the final-target rewrite by creating a canonical runtime event envelope that can outlive the current `AgentRunner` stream event classes.

## Implemented

- Added `cody.core.runtime.events.RunEvent` as the stable append-only event envelope.
- Added `RunEventType` with namespaced event names for run, model, tool, context, circuit breaker, and human/user input events.
- Added `InMemoryTraceStore` as the first TraceStore implementation.
- Added `stream_event_to_run_event()` bridge so existing `AgentRunner` stream events can be converted without breaking current CLI/Web/SDK behavior.
- Added tests for envelope stability, trace filtering/export, and stream-event conversion.

## Reflection

This is intentionally not a cosmetic wrapper. It is the first hard boundary of the future runtime: old stream events remain usable, but all future workflow/checkpoint/approval/trace work can target `RunEvent`. The bridge also reduces migration risk because the old runner does not need to be rewritten in one dangerous step.

## Next Point

Introduce durable run/step identity and start emitting canonical `RunEvent` objects from `AgentRunner.run_stream()` into an injectable TraceStore.

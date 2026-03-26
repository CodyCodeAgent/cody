"""Metrics endpoint — GET /metrics.

Exposes aggregated runtime metrics (token usage, cost, run counts)
for monitoring dashboards and the web UI.

Note: metrics are accumulated in-process and reset on restart.
For multi-worker deployments, each worker maintains independent counters.
"""

import time
import logging

from fastapi import APIRouter

logger = logging.getLogger("cody.web.metrics")

router = APIRouter(tags=["metrics"])

# In-process metrics accumulator.  Safe for single-worker async
# (uvicorn default) because all updates happen in the event loop.
_metrics = {
    "total_runs": 0,
    "total_tokens": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cost_usd": 0.0,
    "start_time": time.time(),
}


def record_run(
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Record metrics from a completed run."""
    _metrics["total_runs"] += 1
    _metrics["total_tokens"] += total_tokens
    _metrics["total_input_tokens"] += input_tokens
    _metrics["total_output_tokens"] += output_tokens
    _metrics["total_cost_usd"] += cost_usd


@router.get("/metrics")
async def get_metrics():
    """Return aggregated runtime metrics."""
    uptime = time.time() - _metrics["start_time"]
    return {
        "total_runs": _metrics["total_runs"],
        "total_tokens": _metrics["total_tokens"],
        "total_input_tokens": _metrics["total_input_tokens"],
        "total_output_tokens": _metrics["total_output_tokens"],
        "total_cost_usd": round(_metrics["total_cost_usd"], 6),
        "uptime_seconds": round(uptime, 1),
    }

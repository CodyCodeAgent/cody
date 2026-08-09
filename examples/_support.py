"""Shared deterministic helpers for offline Runtime demos."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cody.core.runner import DoneEvent, TextDeltaEvent


@dataclass(slots=True)
class StaticResult:
    """Small Agent result accepted by CodyRuntime's compatibility adapter."""

    output: str


class StaticRunner:
    """Deterministic runner used when a Demo should not call a model provider."""

    def __init__(self, output: str, *, workdir: str | Path = ".") -> None:
        self.output = output
        self.workdir = Path(workdir).resolve()

    async def run_stream(self, prompt: Any, **_kwargs: Any):
        yield TextDeltaEvent(content="deterministic demo output: ")
        await asyncio.sleep(0)
        yield DoneEvent(result=StaticResult(f"{self.output} | task={prompt}"))


class UnusedRunner:
    """Placeholder for workflows that contain no Agent node."""

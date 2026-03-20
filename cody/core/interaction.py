"""Unified human-in-the-loop interaction layer.

Provides a standard request/response mechanism for all scenarios where
the runner needs to pause and wait for human input:

- ``question``: AI asks the user a clarifying question
- ``confirm``: a CONFIRM-level tool needs approval before execution
- ``feedback``: AI requests structured feedback (approve/reject/revise)

Each request carries a unique ``id`` so that responses can be matched
back to the correct pending request, even in concurrent scenarios.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class InteractionRequest:
    """A request for human input."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: Literal["question", "confirm", "feedback"] = "question"
    prompt: str = ""
    options: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None


@dataclass
class InteractionResponse:
    """A human response to an InteractionRequest."""
    request_id: str = ""
    action: Literal["approve", "reject", "revise", "answer"] = "answer"
    content: str = ""

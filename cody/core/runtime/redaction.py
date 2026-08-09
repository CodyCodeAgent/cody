"""Central secret redaction for persisted Runtime telemetry."""

from __future__ import annotations

import re
from typing import Any

_SECRET_KEYS = re.compile(
    r"(^|_)(api_?key|token|secret|password|authorization|cookie|credential)(_|$)",
    re.IGNORECASE,
)
_SECRET_VALUES = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|\bsk-[A-Za-z0-9_-]{12,}\b"
)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if _SECRET_KEYS.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return _SECRET_VALUES.sub(
            lambda match: f"{match.group(1)}<redacted>" if match.group(1) else "<redacted>",
            value,
        )
    return value

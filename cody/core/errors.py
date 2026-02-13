"""Structured error responses for Cody API"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standard error codes for all Cody API responses."""
    INVALID_PARAMS = "INVALID_PARAMS"
    AUTH_FAILED = "AUTH_FAILED"
    MODEL_ERROR = "MODEL_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    AGENT_ERROR = "AGENT_ERROR"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_LIMIT_REACHED = "AGENT_LIMIT_REACHED"
    RATE_LIMITED = "RATE_LIMITED"
    MCP_ERROR = "MCP_ERROR"
    SERVER_ERROR = "SERVER_ERROR"


class ErrorDetail(BaseModel):
    """Structured error detail returned in API responses."""
    code: ErrorCode
    message: str
    details: Optional[dict[str, Any]] = None


class CodyAPIError(Exception):
    """Raise in server handlers to produce a structured error response."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: Optional[dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

    def to_detail(self) -> dict:
        body: dict[str, Any] = {
            "error": {
                "code": self.code.value,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        return body

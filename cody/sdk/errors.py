"""Cody SDK - Enhanced error types.

Provides fine-grained error classes for better error handling.
"""

from typing import Optional


class CodyError(Exception):
    """Base error for Cody SDK."""
    
    def __init__(
        self, 
        message: str, 
        status_code: int = 0, 
        code: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(message)
    
    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class CodyNotFoundError(CodyError):
    """Resource not found (session, tool, skill, file, etc.)."""

    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        *,
        code: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=404,
            code=code or "NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class CodyModelError(CodyError):
    """Model API call failed."""
    
    def __init__(
        self, 
        message: str, 
        model: Optional[str] = None,
        provider: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            status_code=500,
            code="MODEL_ERROR",
            details={"model": model, "provider": provider},
        )
        self.original_error = original_error


class CodyToolError(CodyError):
    """Tool execution failed."""
    
    def __init__(
        self, 
        message: str, 
        tool_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            status_code=500,
            code="TOOL_ERROR",
            details={"tool_name": tool_name},
        )
        self.original_error = original_error


class CodyPermissionError(CodyError):
    """Permission denied for tool or action."""
    
    def __init__(
        self, 
        message: str, 
        tool_name: Optional[str] = None,
        required_level: Optional[str] = None,
        current_level: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=403,
            code="PERMISSION_DENIED",
            details={
                "tool_name": tool_name,
                "required_level": required_level,
                "current_level": current_level,
            },
        )


class CodySessionError(CodyError):
    """Session-related error (not found, expired, etc.)."""
    
    def __init__(
        self, 
        message: str, 
        session_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            code="SESSION_ERROR",
            details={"session_id": session_id, "reason": reason},
        )


class CodyRateLimitError(CodyError):
    """Rate limit exceeded."""
    
    def __init__(
        self, 
        message: str, 
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        remaining: Optional[int] = None,
    ):
        super().__init__(
            message=message,
            status_code=429,
            code="RATE_LIMIT_EXCEEDED",
            details={"retry_after": retry_after, "limit": limit, "remaining": remaining},
        )
        self.retry_after = retry_after


class CodyConfigError(CodyError):
    """Configuration error (missing API key, invalid config, etc.)."""
    
    def __init__(
        self, 
        message: str, 
        config_key: Optional[str] = None,
        expected_value: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            code="CONFIG_ERROR",
            details={"config_key": config_key, "expected_value": expected_value},
        )


class CodyTimeoutError(CodyError):
    """Operation timed out."""
    
    def __init__(
        self, 
        message: str, 
        operation: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        super().__init__(
            message=message,
            status_code=408,
            code="TIMEOUT",
            details={"operation": operation, "timeout": timeout},
        )


class CodyConnectionError(CodyError):
    """Connection failed (MCP server, LSP server, etc.)."""
    
    def __init__(
        self, 
        message: str, 
        service: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message=message,
            status_code=503,
            code="CONNECTION_ERROR",
            details={"service": service},
        )
        self.original_error = original_error

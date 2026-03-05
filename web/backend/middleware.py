"""HTTP middleware — auth, rate limiting, audit logging.

Migrated from cody/server.py. These are registered in app.py.
"""

import logging
import time
from typing import Set

from fastapi import Request
from fastapi.responses import JSONResponse

from cody.core.audit import AuditEvent
from cody.core.auth import AuthError
from cody.core.errors import ErrorCode

from .state import get_audit_logger, get_auth_manager, get_rate_limiter

logger = logging.getLogger("cody.web.middleware")


# Endpoints that do not require authentication
PUBLIC_PATHS: Set[str] = {"/health", "/api/health", "/docs", "/openapi.json", "/redoc"}


def validate_credential(credential: str) -> bool:
    """Validate a credential string (token or API key).

    Returns True if auth is not configured or credential is valid.
    Raises AuthError if credential is invalid.
    """
    try:
        auth_mgr = get_auth_manager()
    except Exception:
        return True

    if auth_mgr is None or not auth_mgr.is_configured:
        return True

    if not credential:
        raise AuthError("Missing credential", code="AUTH_FAILED")

    auth_mgr.validate(credential)
    return True


async def auth_middleware(request: Request, call_next):
    """Authenticate requests using Bearer token or API key."""
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/docs"):
        return await call_next(request)

    try:
        auth_mgr = get_auth_manager()
    except Exception:
        return await call_next(request)

    if auth_mgr is None or not auth_mgr.is_configured:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        logger.warning("Auth failed: missing header, path=%s", path)
        try:
            get_audit_logger().log(
                event=AuditEvent.AUTH_FAILURE,
                args_summary=f"path={path}",
                result_summary="Missing Authorization header",
                success=False,
            )
        except Exception:
            pass
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "AUTH_FAILED",
                               "message": "Missing Authorization header"}},
        )

    credential = auth_header
    if auth_header.startswith("Bearer "):
        credential = auth_header[7:]

    try:
        auth_mgr.validate(credential)
    except AuthError as e:
        logger.warning("Auth failed: %s, path=%s", e, path)
        try:
            get_audit_logger().log(
                event=AuditEvent.AUTH_FAILURE,
                args_summary=f"path={path}",
                result_summary=str(e),
                success=False,
            )
        except Exception:
            pass
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "AUTH_FAILED", "message": str(e)}},
        )

    return await call_next(request)


async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting based on client IP."""
    try:
        limiter = get_rate_limiter()
    except Exception:
        return await call_next(request)

    if limiter is None:
        return await call_next(request)

    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    result = limiter.hit(client_ip)

    if not result.allowed:
        logger.warning("Rate limited: ip=%s path=%s", client_ip, path)
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": ErrorCode.RATE_LIMITED.value,
                    "message": "Rate limit exceeded",
                }
            },
            headers={
                "Retry-After": str(int(result.retry_after or 1)),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    return response


async def audit_middleware(request: Request, call_next):
    """Log all API requests to the audit log."""
    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)

    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
    logger.log(
        log_level,
        "%s %s → %d (%dms)",
        request.method, path, response.status_code, elapsed_ms,
    )

    try:
        get_audit_logger().log(
            event=AuditEvent.API_REQUEST,
            tool_name=f"{request.method} {path}",
            args_summary=f"client={request.client.host if request.client else 'unknown'}",
            result_summary=f"status={response.status_code} elapsed={elapsed_ms}ms",
            success=response.status_code < 400,
        )
    except Exception:
        pass

    return response

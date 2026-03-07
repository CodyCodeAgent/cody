"""Audit endpoint — GET /audit.

Migrated from cody/server.py.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from cody.core.audit import AuditLogger

from ..state import audit_logger_dep

router = APIRouter(tags=["audit"])


@router.get("/audit")
async def query_audit(
    event: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
    audit_logger: AuditLogger = Depends(audit_logger_dep),
):
    """Query audit log entries."""
    entries = audit_logger.query(event=event, since=since, limit=limit)
    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "event": e.event,
                "tool_name": e.tool_name,
                "args_summary": e.args_summary,
                "result_summary": e.result_summary,
                "session_id": e.session_id,
                "workdir": e.workdir,
                "success": e.success,
            }
            for e in entries
        ],
        "total": audit_logger.count(event=event),
    }

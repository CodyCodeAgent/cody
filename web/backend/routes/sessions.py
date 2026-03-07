"""Session endpoints — CRUD for cody sessions.

Migrated from cody/server.py.
"""

import asyncio

from fastapi import APIRouter, Depends

from cody.core import SessionStore
from cody.core.errors import ErrorCode

from ..helpers import raise_structured
from ..models import SessionResponse, SessionDetailResponse
from ..state import session_store_dep

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    title: str = "New session",
    model: str = "",
    workdir: str = "",
    store: SessionStore = Depends(session_store_dep),
):
    """Create a new session."""
    session = await asyncio.to_thread(
        store.create_session, title=title, model=model, workdir=workdir,
    )
    return SessionResponse(
        id=session.id,
        title=session.title,
        model=session.model,
        workdir=session.workdir,
        message_count=0,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    store: SessionStore = Depends(session_store_dep),
):
    """List recent sessions."""
    sessions = await asyncio.to_thread(store.list_sessions, limit=limit)
    result = []
    for s in sessions:
        count = await asyncio.to_thread(store.get_message_count, s.id)
        result.append({
            "id": s.id,
            "title": s.title,
            "model": s.model,
            "workdir": s.workdir,
            "message_count": count,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })
    return {"sessions": result}


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    store: SessionStore = Depends(session_store_dep),
):
    """Get session with messages."""
    session = await asyncio.to_thread(store.get_session, session_id)
    if not session:
        raise_structured(
            ErrorCode.SESSION_NOT_FOUND,
            f"Session not found: {session_id}",
            status_code=404,
        )

    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        model=session.model,
        workdir=session.workdir,
        message_count=len(session.messages),
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                "images": [img.to_dict() for img in m.images] if m.images else None,
            }
            for m in session.messages
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    store: SessionStore = Depends(session_store_dep),
):
    """Delete a session."""
    deleted = await asyncio.to_thread(store.delete_session, session_id)
    if not deleted:
        raise_structured(
            ErrorCode.SESSION_NOT_FOUND,
            f"Session not found: {session_id}",
            status_code=404,
        )
    return {"status": "deleted", "id": session_id}

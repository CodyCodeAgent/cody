"""Directory browsing endpoint."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..models import DirectoryEntry, DirectoryListResponse

router = APIRouter(tags=["directories"])


@router.get("/api/directories", response_model=DirectoryListResponse)
async def list_directories(path: Optional[str] = Query(default=None)):
    """List directories and files under the given path."""
    target = Path(path) if path else Path.home()
    if not target.is_dir():
        raise HTTPException(
            status_code=404, detail=f"Directory not found: {target}"
        )

    entries: list[DirectoryEntry] = []
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith("."):
                continue
            entries.append(DirectoryEntry(name=item.name, is_dir=item.is_dir()))
    except PermissionError:
        raise HTTPException(
            status_code=403, detail=f"Permission denied: {target}"
        )

    return DirectoryListResponse(path=str(target), entries=entries)

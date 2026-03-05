"""Directory browsing endpoint."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from cody.core.errors import ErrorCode

from ..helpers import raise_structured
from ..models import DirectoryEntry, DirectoryListResponse

router = APIRouter(tags=["directories"])


@router.get("/api/directories", response_model=DirectoryListResponse)
async def list_directories(path: Optional[str] = Query(default=None)):
    """List directories and files under the given path."""
    target = Path(path) if path else Path.home()
    if not target.is_dir():
        raise_structured(
            ErrorCode.NOT_FOUND,
            f"Directory not found: {target}",
            status_code=404,
        )

    entries: list[DirectoryEntry] = []
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith("."):
                continue
            # Skip symlinks to prevent directory traversal
            if item.is_symlink():
                continue
            entries.append(DirectoryEntry(name=item.name, is_dir=item.is_dir()))
    except PermissionError:
        raise_structured(
            ErrorCode.PERMISSION_DENIED,
            f"Permission denied: {target}",
            status_code=403,
        )

    return DirectoryListResponse(path=str(target), entries=entries)

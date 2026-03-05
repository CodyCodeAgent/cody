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
    home = Path.home()
    if path is not None:
        target = Path(path).resolve()
        # Prevent traversal outside the home directory
        if target != home and not str(target).startswith(str(home) + "/"):
            raise_structured(
                ErrorCode.PERMISSION_DENIED,
                f"Access denied: path is outside home directory: {target}",
                status_code=403,
            )
    else:
        target = home
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

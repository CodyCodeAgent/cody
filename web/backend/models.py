"""Pydantic models for the web backend API."""

from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    workdir: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    workdir: str
    session_id: Optional[str] = None
    created_at: str
    updated_at: str


class DirectoryEntry(BaseModel):
    name: str
    is_dir: bool


class DirectoryListResponse(BaseModel):
    path: str
    entries: list[DirectoryEntry]


class WebHealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.3.0"
    core_server: str = "unavailable"
    core_version: Optional[str] = None

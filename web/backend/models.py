"""Pydantic models for the web backend API.

Includes both web-specific models (projects) and RPC models (run, tool,
sessions, etc.) migrated from cody/server.py.
"""

from typing import Optional

from pydantic import BaseModel

from cody import __version__
from cody.core.errors import ErrorDetail


# ── Web-specific models ─────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    workdir: str
    code_paths: list[str] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    code_paths: Optional[list[str]] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    workdir: str
    code_paths: list[str] = []
    session_id: Optional[str] = None
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    name: str
    branch_name: str


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class TaskResponse(BaseModel):
    id: str
    project_id: str
    name: str
    branch_name: str
    session_id: Optional[str] = None
    status: str
    created_at: str
    updated_at: str


class DirectoryEntry(BaseModel):
    name: str
    is_dir: bool


class DirectoryListResponse(BaseModel):
    path: str
    entries: list[DirectoryEntry]


# ── RPC models (migrated from server.py) ────────────────────────────────────


class ImagePayload(BaseModel):
    """An image attached to a user message."""
    data: str  # base64-encoded
    media_type: str  # "image/png", "image/jpeg", etc.
    filename: Optional[str] = None


class RunRequest(BaseModel):
    prompt: str
    images: Optional[list[ImagePayload]] = None
    workdir: Optional[str] = None
    allowed_roots: Optional[list[str]] = None
    model: Optional[str] = None
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    enable_thinking: Optional[bool] = None
    thinking_budget: Optional[int] = None
    skills: Optional[list[str]] = None
    session_id: Optional[str] = None
    # Circuit breaker overrides
    max_tokens: Optional[int] = None
    max_cost_usd: Optional[float] = None
    max_steps: Optional[int] = None
    # Tool filtering
    include_tools: Optional[list[str]] = None
    exclude_tools: Optional[list[str]] = None


class ToolTraceResponse(BaseModel):
    tool_name: str
    args: dict
    result: str


class RunResponse(BaseModel):
    status: str = "success"
    output: str
    thinking: Optional[str] = None
    tool_traces: Optional[list[ToolTraceResponse]] = None
    session_id: Optional[str] = None
    usage: Optional[dict] = None


class ToolRequest(BaseModel):
    tool: str
    params: dict
    workdir: Optional[str] = None


class ToolResponse(BaseModel):
    status: str = "success"
    result: str


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = __version__


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SessionResponse(BaseModel):
    id: str
    title: str
    model: str
    workdir: str
    message_count: int
    created_at: str
    updated_at: str


class SessionDetailResponse(SessionResponse):
    messages: list[dict]


class SpawnRequest(BaseModel):
    task: str
    type: str = "generic"
    timeout: Optional[float] = None
    workdir: Optional[str] = None

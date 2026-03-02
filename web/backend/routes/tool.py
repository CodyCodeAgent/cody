"""Tool endpoint — POST /tool.

Migrated from cody/server.py. Direct tool invocation without Agent.
"""

from pathlib import Path

from fastapi import APIRouter

from cody.core.errors import (
    CodyAPIError, ErrorCode,
    ToolError, ToolPermissionDenied, ToolPathDenied, ToolInvalidParams,
)

from ..helpers import raise_structured
from ..models import ToolRequest, ToolResponse
from ..state import get_config, create_full_deps

router = APIRouter(tags=["tool"])


@router.post("/tool", response_model=ToolResponse)
async def call_tool(request: ToolRequest):
    """Call a tool directly."""
    from cody.core import tools

    tool_func = getattr(tools, request.tool, None)
    if not tool_func:
        raise_structured(
            ErrorCode.TOOL_NOT_FOUND,
            f"Tool not found: {request.tool}",
            status_code=404,
        )

    try:
        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        config = get_config(workdir)
        deps = create_full_deps(config, workdir)

        class ToolContext:
            def __init__(self, deps):
                self.deps = deps

        ctx = ToolContext(deps)
        result = await tool_func(ctx, **request.params)

        return ToolResponse(result=result)

    except (ToolPermissionDenied, ToolPathDenied) as e:
        raise_structured(e.code, e.message, status_code=403)
    except ToolInvalidParams as e:
        raise_structured(e.code, e.message, status_code=400)
    except ToolError as e:
        raise_structured(e.code, e.message, status_code=500)
    except CodyAPIError:
        raise
    except Exception as e:
        raise_structured(
            ErrorCode.TOOL_ERROR, str(e), status_code=500,
            details={"tool": request.tool},
        )

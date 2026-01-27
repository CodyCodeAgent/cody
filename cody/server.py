"""RPC Server for Cody"""

import asyncio
from pathlib import Path
from typing import AsyncIterator
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from .core import Config, AgentRunner


# Request/Response models
class RunRequest(BaseModel):
    prompt: str
    workdir: str | None = None
    model: str | None = None
    skills: list[str] | None = None
    stream: bool = False


class RunResponse(BaseModel):
    status: str = "success"
    output: str
    usage: dict | None = None
    duration_ms: int | None = None


class ToolRequest(BaseModel):
    tool: str
    params: dict
    workdir: str | None = None


class ToolResponse(BaseModel):
    status: str = "success"
    result: str


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


# Create FastAPI app
app = FastAPI(
    title="Cody RPC Server",
    description="AI Coding Assistant RPC API",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse()


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest):
    """Run agent with prompt"""
    try:
        # Load config
        config = Config.load()
        if request.model:
            config.model = request.model
        
        # Override skills if specified
        if request.skills is not None:
            config.skills.enabled = request.skills
        
        # Create runner
        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        runner = AgentRunner(config=config, workdir=workdir)
        
        # Run agent
        result = await runner.run(request.prompt, stream=False)
        
        return RunResponse(
            output=result.output,
            usage={
                "input_tokens": result.usage().input_tokens,
                "output_tokens": result.usage().output_tokens,
                "total_tokens": result.usage().total_tokens,
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run/stream")
async def run_agent_stream(request: RunRequest):
    """Run agent with streaming response"""
    
    async def generate() -> AsyncIterator[str]:
        try:
            config = Config.load()
            if request.model:
                config.model = request.model
            
            workdir = Path(request.workdir) if request.workdir else Path.cwd()
            runner = AgentRunner(config=config, workdir=workdir)
            
            async for text in runner.run(request.prompt, stream=True):
                # SSE format
                yield f"data: {text}\n\n"
            
            yield "data: [DONE]\n\n"
        
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/tool", response_model=ToolResponse)
async def call_tool(request: ToolRequest):
    """Call a tool directly"""
    try:
        # Import tools
        from .core import tools
        
        # Get tool function
        tool_func = getattr(tools, request.tool, None)
        if not tool_func:
            raise HTTPException(status_code=404, detail=f"Tool not found: {request.tool}")
        
        # Create minimal context
        config = Config.load()
        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        runner = AgentRunner(config=config, workdir=workdir)
        
        # Create deps
        from .core.runner import CodyDeps
        deps = CodyDeps(
            config=config,
            workdir=workdir,
            skill_manager=runner.skill_manager,
        )
        
        # Create mock context
        class MockContext:
            def __init__(self, deps):
                self.deps = deps
        
        ctx = MockContext(deps)
        
        # Call tool
        result = await tool_func(ctx, **request.params)
        
        return ToolResponse(result=result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills")
async def list_skills():
    """List all available skills"""
    try:
        config = Config.load()
        runner = AgentRunner(config=config)
        
        skills = runner.skill_manager.list_skills()
        
        return {
            "skills": [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "enabled": skill.enabled,
                    "source": skill.source,
                }
                for skill in skills
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills/{skill_name}")
async def get_skill(skill_name: str):
    """Get skill documentation"""
    try:
        config = Config.load()
        runner = AgentRunner(config=config)
        
        skill = runner.skill_manager.get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
        
        return {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "source": skill.source,
            "documentation": skill.documentation,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def run(host: str = "0.0.0.0", port: int = 8000):
    """Run the server"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import click
    
    @click.command()
    @click.option('--host', default="0.0.0.0", help='Host to bind')
    @click.option('--port', default=8000, help='Port to bind')
    def main(host, port):
        """Start Cody RPC Server"""
        print(f"🚀 Starting Cody RPC Server on {host}:{port}")
        run(host, port)
    
    main()

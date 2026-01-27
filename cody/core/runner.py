"""Agent runner - core execution engine"""

from dataclasses import dataclass
from pathlib import Path
from pydantic_ai import Agent
from .config import Config
from .skill_manager import SkillManager
from . import tools


@dataclass
class CodyDeps:
    """Dependencies for Cody Agent"""
    config: Config
    workdir: Path
    skill_manager: SkillManager


class AgentRunner:
    """Run Cody Agent with full context"""
    
    def __init__(self, config: Config | None = None, workdir: Path | str | None = None):
        self.config = config or Config.load()
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.skill_manager = SkillManager(self.config)
        
        # Create agent
        self.agent = self._create_agent()
    
    def _create_agent(self) -> Agent:
        """Create Pydantic AI Agent with tools"""
        agent = Agent(
            self.config.model,
            deps_type=CodyDeps,
            system_prompt=(
                "You are Cody, an AI coding assistant. "
                "You have access to file operations, shell commands, and skills. "
                "When you need to use a skill, first call list_skills() to see what's available, "
                "then call read_skill(skill_name) to learn how to use it. "
                "Always execute commands and file operations as needed to complete tasks."
            ),
        )
        
        # Register tools
        agent.tool(tools.read_file)
        agent.tool(tools.write_file)
        agent.tool(tools.edit_file)
        agent.tool(tools.list_directory)
        agent.tool(tools.exec_command)
        agent.tool(tools.list_skills)
        agent.tool(tools.read_skill)
        
        return agent
    
    def _create_deps(self) -> CodyDeps:
        """Create dependencies"""
        return CodyDeps(
            config=self.config,
            workdir=self.workdir,
            skill_manager=self.skill_manager,
        )
    
    async def run(self, prompt: str, stream: bool = False):
        """Run agent with prompt"""
        deps = self._create_deps()
        
        if stream:
            async with self.agent.run_stream(prompt, deps=deps) as result:
                async for text in result.stream_text():
                    yield text
                
                # Get final result
                final_output = result.output if hasattr(result, 'output') else None
                return final_output
        else:
            result = await self.agent.run(prompt, deps=deps)
            return result
    
    def run_sync(self, prompt: str):
        """Run agent synchronously"""
        deps = self._create_deps()
        result = self.agent.run_sync(prompt, deps=deps)
        return result

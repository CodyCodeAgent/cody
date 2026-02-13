"""Skill management system"""

from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .config import Config


@dataclass
class Skill:
    """Skill metadata"""
    name: str
    description: str
    source: Literal['project', 'global', 'builtin']
    path: Path
    enabled: bool = True
    
    @property
    def documentation(self) -> str:
        """Read skill documentation"""
        skill_md = self.path / "SKILL.md"
        if skill_md.exists():
            return skill_md.read_text()
        return f"# {self.name}\n\nNo documentation available."


class SkillManager:
    """Manage and load skills"""
    
    def __init__(self, config: "Config"):
        self.config = config
        self.skills: dict[str, Skill] = {}
        self._load_skills()
    
    def _load_skills(self):
        """Load skills from all sources"""
        # Priority: project > global > builtin
        search_paths = [
            (Path.cwd() / ".cody" / "skills", "project"),
            (Path.home() / ".cody" / "skills", "global"),
            (Path(__file__).parent.parent / "skills", "builtin"),
        ]
        
        for base_path, source in search_paths:
            if not base_path.exists():
                continue
            
            for skill_dir in base_path.iterdir():
                if not skill_dir.is_dir():
                    continue
                
                skill_name = skill_dir.name
                
                # Skip if already loaded from higher priority source
                if skill_name in self.skills:
                    continue
                
                # Check if skill has SKILL.md
                if not (skill_dir / "SKILL.md").exists():
                    continue
                
                # Determine if enabled
                enabled = self._is_enabled(skill_name)
                
                # Load description from first line of SKILL.md
                skill_md = skill_dir / "SKILL.md"
                first_line = skill_md.read_text().split('\n')[0]
                description = first_line.strip('# ').strip()
                
                self.skills[skill_name] = Skill(
                    name=skill_name,
                    description=description,
                    source=source,
                    path=skill_dir,
                    enabled=enabled,
                )
    
    def _is_enabled(self, skill_name: str) -> bool:
        """Check if skill is enabled"""
        if skill_name in self.config.skills.disabled:
            return False
        
        if self.config.skills.enabled:
            return skill_name in self.config.skills.enabled
        
        # Default: all skills enabled
        return True
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get skill by name"""
        return self.skills.get(name)
    
    def list_skills(self) -> list[Skill]:
        """List all skills"""
        return list(self.skills.values())
    
    def enable_skill(self, name: str):
        """Enable a skill"""
        if name in self.skills:
            self.skills[name].enabled = True
            if name not in self.config.skills.enabled:
                self.config.skills.enabled.append(name)
            if name in self.config.skills.disabled:
                self.config.skills.disabled.remove(name)
    
    def disable_skill(self, name: str):
        """Disable a skill"""
        if name in self.skills:
            self.skills[name].enabled = False
            if name not in self.config.skills.disabled:
                self.config.skills.disabled.append(name)
            if name in self.config.skills.enabled:
                self.config.skills.enabled.remove(name)

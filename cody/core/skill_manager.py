"""Skill management system — Agent Skills open standard (agentskills.io)"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .config import Config

# ── YAML frontmatter parser (no external deps) ──────────────────────────────

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n", re.DOTALL)

_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from SKILL.md content.

    Returns (metadata_dict, body_markdown).
    Raises ValueError if frontmatter is missing or invalid.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("SKILL.md must contain YAML frontmatter (---)")

    raw_yaml = match.group(1)
    body = text[match.end():]

    metadata: dict[str, str] = {}
    current_key: Optional[str] = None
    current_value_lines: list[str] = []

    for line in raw_yaml.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Check for top-level key: value
        kv_match = re.match(r"^([a-z][a-z0-9_-]*)\s*:\s*(.*)", line)
        if kv_match and not line[0].isspace():
            # Save previous key if any
            if current_key:
                metadata[current_key] = "\n".join(current_value_lines).strip()

            current_key = kv_match.group(1)
            value = kv_match.group(2).strip()

            # Handle multi-line mapping (metadata:, allowed-tools list, etc.)
            if value:
                current_value_lines = [value]
            else:
                current_value_lines = []
        elif current_key and line[0].isspace():
            # Continuation line for current key
            current_value_lines.append(stripped)
        # else: skip malformed lines

    # Save last key
    if current_key:
        metadata[current_key] = "\n".join(current_value_lines).strip()

    return metadata, body


def _validate_name(name: str, dir_name: str) -> None:
    """Validate skill name per Agent Skills spec."""
    if not name:
        raise ValueError("Skill 'name' field is required")
    if len(name) > 64:
        raise ValueError(f"Skill name must be ≤64 chars, got {len(name)}")
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Skill name '{name}' invalid: must be lowercase alphanumeric + hyphens, "
            "no leading/trailing/consecutive hyphens"
        )
    if name != dir_name:
        raise ValueError(
            f"Skill name '{name}' must match directory name '{dir_name}'"
        )


# ── Skill dataclass ─────────────────────────────────────────────────────────


@dataclass
class Skill:
    """Skill following Agent Skills open standard (agentskills.io)"""
    name: str
    description: str
    source: Literal['project', 'global', 'builtin']
    path: Path
    enabled: bool = True
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: Optional[str] = None
    _cached_instructions: Optional[str] = field(default=None, repr=False)
    _cached_documentation: Optional[str] = field(default=None, repr=False)

    @property
    def instructions(self) -> str:
        """Read full SKILL.md body (activated on demand — progressive disclosure)."""
        if self._cached_instructions is not None:
            return self._cached_instructions
        skill_md = self.path / "SKILL.md"
        if skill_md.exists():
            text = skill_md.read_text()
            _, body = _parse_frontmatter(text)
            self._cached_instructions = body.strip()
        else:
            self._cached_instructions = ""
        return self._cached_instructions

    @property
    def documentation(self) -> str:
        """Read full SKILL.md content (frontmatter + body)."""
        if self._cached_documentation is not None:
            return self._cached_documentation
        skill_md = self.path / "SKILL.md"
        if skill_md.exists():
            self._cached_documentation = skill_md.read_text()
        else:
            self._cached_documentation = f"# {self.name}\n\nNo documentation available."
        return self._cached_documentation


# ── SkillManager ─────────────────────────────────────────────────────────────


class SkillManager:
    """Manage and load skills per Agent Skills open standard."""

    def __init__(self, config: "Config"):
        self.config = config
        self.skills: dict[str, Skill] = {}
        self._load_skills()

    def _load_skills(self):
        """Discover and load skill metadata from all sources.

        Only parses YAML frontmatter (name + description) at startup.
        Full SKILL.md body is loaded on demand (progressive disclosure).
        """
        # Priority: project > global > builtin
        search_paths = [
            (Path.cwd() / ".cody" / "skills", "project"),
            (Path.home() / ".cody" / "skills", "global"),
            (Path(__file__).parent.parent / "skills", "builtin"),
        ]

        for base_path, source in search_paths:
            if not base_path.exists():
                continue

            for skill_dir in sorted(base_path.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue

                dir_name = skill_dir.name

                # Skip if already loaded from higher priority source
                if dir_name in self.skills:
                    continue

                try:
                    text = skill_md.read_text()
                    fm, _ = _parse_frontmatter(text)
                except ValueError:
                    continue  # Skip skills without valid frontmatter

                name = fm.get("name", "")
                description = fm.get("description", "")

                # Validate required fields
                if not name or not description:
                    continue

                # Validate name matches directory
                try:
                    _validate_name(name, dir_name)
                except ValueError:
                    continue

                enabled = self._is_enabled(name)

                self.skills[name] = Skill(
                    name=name,
                    description=description,
                    source=source,
                    path=skill_dir,
                    enabled=enabled,
                    license=fm.get("license"),
                    compatibility=fm.get("compatibility"),
                    metadata=_parse_metadata_block(fm.get("metadata", "")),
                    allowed_tools=fm.get("allowed-tools"),
                )

    def _is_enabled(self, skill_name: str) -> bool:
        """Check if skill is enabled."""
        if skill_name in self.config.skills.disabled:
            return False

        if self.config.skills.enabled:
            return skill_name in self.config.skills.enabled

        # Default: all skills enabled
        return True

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get skill by name."""
        return self.skills.get(name)

    def list_skills(self) -> list[Skill]:
        """List all skills."""
        return list(self.skills.values())

    def enable_skill(self, name: str):
        """Enable a skill."""
        if name in self.skills:
            self.skills[name].enabled = True
            if name not in self.config.skills.enabled:
                self.config.skills.enabled.append(name)
            if name in self.config.skills.disabled:
                self.config.skills.disabled.remove(name)

    def disable_skill(self, name: str):
        """Disable a skill."""
        if name in self.skills:
            self.skills[name].enabled = False
            if name not in self.config.skills.disabled:
                self.config.skills.disabled.append(name)
            if name in self.config.skills.enabled:
                self.config.skills.enabled.remove(name)

    def to_prompt_xml(self) -> str:
        """Generate <available_skills> XML for system prompt injection.

        Per Agent Skills standard, inject this into the system prompt so the
        model knows which skills are available and can activate them by context.
        """
        enabled_skills = [s for s in self.skills.values() if s.enabled]
        if not enabled_skills:
            return ""

        lines = ["<available_skills>"]
        for skill in enabled_skills:
            lines.append("  <skill>")
            lines.append(f"    <name>{skill.name}</name>")
            lines.append(f"    <description>{skill.description}</description>")
            lines.append(f"    <location>{skill.path / 'SKILL.md'}</location>")
            lines.append("  </skill>")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def validate_skill(self, skill_dir: Path) -> list[str]:
        """Validate a skill directory against the Agent Skills spec.

        Returns a list of problems (empty = valid).
        """
        problems: list[str] = []

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            problems.append("Missing SKILL.md")
            return problems

        try:
            text = skill_md.read_text()
            fm, body = _parse_frontmatter(text)
        except ValueError as e:
            problems.append(str(e))
            return problems

        # Required fields
        name = fm.get("name", "")
        if not name:
            problems.append("Missing required field: name")
        elif len(name) > 64:
            problems.append(f"name exceeds 64 characters ({len(name)})")
        elif not _NAME_RE.match(name):
            problems.append(f"Invalid name format: '{name}'")
        elif name != skill_dir.name:
            problems.append(f"name '{name}' does not match directory '{skill_dir.name}'")

        description = fm.get("description", "")
        if not description:
            problems.append("Missing required field: description")
        elif len(description) > 1024:
            problems.append(f"description exceeds 1024 characters ({len(description)})")

        # Optional field constraints
        compat = fm.get("compatibility", "")
        if compat and len(compat) > 500:
            problems.append(f"compatibility exceeds 500 characters ({len(compat)})")

        if not body.strip():
            problems.append("SKILL.md body is empty (no instructions)")

        return problems


def _parse_metadata_block(raw: str) -> dict[str, str]:
    """Parse the metadata sub-block (key: value lines)."""
    result: dict[str, str] = {}
    if not raw:
        return result
    for line in raw.split("\n"):
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result

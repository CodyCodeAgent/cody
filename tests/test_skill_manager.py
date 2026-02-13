"""Tests for skill management system"""

from pathlib import Path

from cody.core.config import Config
from cody.core.skill_manager import Skill, SkillManager


# ── Skill dataclass ──────────────────────────────────────────────────────────


def test_skill_fields(tmp_path):
    skill_dir = tmp_path / "myskill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# My Skill\n\nDoes things.")

    skill = Skill(
        name="myskill",
        description="My Skill",
        source="project",
        path=skill_dir,
        enabled=True,
    )
    assert skill.name == "myskill"
    assert skill.source == "project"
    assert skill.enabled is True


def test_skill_documentation(tmp_path):
    skill_dir = tmp_path / "testskill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Test Skill\n\nTest documentation.")

    skill = Skill(name="testskill", description="Test", source="builtin", path=skill_dir)
    assert "Test documentation" in skill.documentation


def test_skill_documentation_missing(tmp_path):
    skill_dir = tmp_path / "noskill"
    skill_dir.mkdir()

    skill = Skill(name="noskill", description="No docs", source="builtin", path=skill_dir)
    assert "No documentation available" in skill.documentation


# ── SkillManager init ────────────────────────────────────────────────────────


def test_skill_manager_loads_builtin():
    """SkillManager loads at least the built-in git skill."""
    config = Config()
    manager = SkillManager(config)
    skills = manager.list_skills()
    names = [s.name for s in skills]
    assert "git" in names


def test_skill_manager_get_skill():
    config = Config()
    manager = SkillManager(config)
    git = manager.get_skill("git")
    assert git is not None
    assert git.name == "git"
    assert git.source == "builtin"


def test_skill_manager_get_skill_not_found():
    config = Config()
    manager = SkillManager(config)
    assert manager.get_skill("nonexistent_skill_xyz") is None


# ── Enable / Disable ─────────────────────────────────────────────────────────


def test_enable_skill():
    config = Config(skills={"enabled": [], "disabled": ["git"]})
    manager = SkillManager(config)

    git = manager.get_skill("git")
    assert git is not None
    assert git.enabled is False

    manager.enable_skill("git")
    assert manager.get_skill("git").enabled is True
    assert "git" in config.skills.enabled
    assert "git" not in config.skills.disabled


def test_disable_skill():
    config = Config()
    manager = SkillManager(config)

    git = manager.get_skill("git")
    assert git is not None
    assert git.enabled is True

    manager.disable_skill("git")
    assert manager.get_skill("git").enabled is False
    assert "git" in config.skills.disabled


def test_enable_nonexistent_skill():
    """Enabling a skill that doesn't exist is a no-op."""
    config = Config()
    manager = SkillManager(config)
    manager.enable_skill("nonexistent_skill_xyz")
    # No error raised


def test_disable_nonexistent_skill():
    config = Config()
    manager = SkillManager(config)
    manager.disable_skill("nonexistent_skill_xyz")
    # No error raised


# ── Priority loading ─────────────────────────────────────────────────────────


def test_skill_priority_project_over_builtin(tmp_path, monkeypatch):
    """Project skills take priority over builtin skills."""
    # Create a project-level git skill with custom content
    project_skills = tmp_path / ".cody" / "skills" / "git"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text("# Project Git Skill\n\nCustom project git.")

    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    config = Config()
    manager = SkillManager(config)
    git = manager.get_skill("git")
    assert git is not None
    assert git.source == "project"
    assert "Custom project git" in git.documentation


# ── Enabled filter ───────────────────────────────────────────────────────────


def test_is_enabled_default():
    """By default all skills are enabled."""
    config = Config()
    manager = SkillManager(config)
    assert manager._is_enabled("anything") is True


def test_is_enabled_whitelist():
    """When enabled list is set, only listed skills are enabled."""
    config = Config(skills={"enabled": ["git"], "disabled": []})
    manager = SkillManager(config)
    assert manager._is_enabled("git") is True
    assert manager._is_enabled("docker") is False


def test_is_enabled_blacklist():
    """Disabled list takes precedence."""
    config = Config(skills={"enabled": [], "disabled": ["git"]})
    manager = SkillManager(config)
    assert manager._is_enabled("git") is False

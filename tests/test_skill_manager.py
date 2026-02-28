"""Tests for skill management system (Agent Skills open standard)"""

from pathlib import Path

import pytest

from cody.core.config import Config
from cody.core.skill_manager import (
    Skill,
    SkillManager,
    _parse_frontmatter,
    _validate_name,
)


# ── Frontmatter parser ──────────────────────────────────────────────────────


def test_parse_frontmatter_basic():
    text = "---\nname: my-skill\ndescription: Does things.\n---\n\n# My Skill\n\nBody."
    fm, body = _parse_frontmatter(text)
    assert fm["name"] == "my-skill"
    assert fm["description"] == "Does things."
    assert "# My Skill" in body


def test_parse_frontmatter_with_metadata():
    text = (
        "---\nname: my-skill\ndescription: Does things.\n"
        "metadata:\n  author: cody\n  version: \"1.0\"\n---\n\nBody."
    )
    fm, body = _parse_frontmatter(text)
    assert fm["name"] == "my-skill"
    assert "author" in fm["metadata"]


def test_parse_frontmatter_with_optional_fields():
    text = (
        "---\nname: my-skill\ndescription: Does things.\n"
        "license: Apache-2.0\ncompatibility: Requires git\n"
        "allowed-tools: Bash(git:*) Read\n---\n\nBody."
    )
    fm, body = _parse_frontmatter(text)
    assert fm["license"] == "Apache-2.0"
    assert fm["compatibility"] == "Requires git"
    assert fm["allowed-tools"] == "Bash(git:*) Read"


def test_parse_frontmatter_missing():
    with pytest.raises(ValueError, match="YAML frontmatter"):
        _parse_frontmatter("# No frontmatter\n\nJust markdown.")


def test_parse_frontmatter_empty_body():
    text = "---\nname: my-skill\ndescription: Does things.\n---\n"
    fm, body = _parse_frontmatter(text)
    assert fm["name"] == "my-skill"
    assert body.strip() == ""


# ── Name validation ─────────────────────────────────────────────────────────


def test_validate_name_valid():
    _validate_name("git", "git")
    _validate_name("my-skill", "my-skill")
    _validate_name("a1b2", "a1b2")


def test_validate_name_empty():
    with pytest.raises(ValueError, match="required"):
        _validate_name("", "mydir")


def test_validate_name_too_long():
    with pytest.raises(ValueError, match="64"):
        _validate_name("a" * 65, "a" * 65)


def test_validate_name_uppercase():
    with pytest.raises(ValueError, match="invalid"):
        _validate_name("MySkill", "MySkill")


def test_validate_name_leading_hyphen():
    with pytest.raises(ValueError, match="invalid"):
        _validate_name("-skill", "-skill")


def test_validate_name_consecutive_hyphens():
    with pytest.raises(ValueError, match="invalid"):
        _validate_name("my--skill", "my--skill")


def test_validate_name_mismatch():
    with pytest.raises(ValueError, match="must match directory"):
        _validate_name("my-skill", "other-dir")


# ── Skill dataclass ──────────────────────────────────────────────────────────


def _make_skill_dir(tmp_path, name="myskill", description="Does things"):
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nInstructions here."
    )
    return skill_dir


def test_skill_fields(tmp_path):
    skill_dir = _make_skill_dir(tmp_path)

    skill = Skill(
        name="myskill",
        description="Does things",
        source="project",
        path=skill_dir,
        enabled=True,
    )
    assert skill.name == "myskill"
    assert skill.source == "project"
    assert skill.enabled is True


def test_skill_instructions(tmp_path):
    skill_dir = _make_skill_dir(tmp_path, "testskill", "Test skill")

    skill = Skill(name="testskill", description="Test", source="builtin", path=skill_dir)
    assert "Instructions here" in skill.instructions
    assert "---" not in skill.instructions  # frontmatter stripped


def test_skill_documentation_full(tmp_path):
    skill_dir = _make_skill_dir(tmp_path, "testskill", "Test skill")

    skill = Skill(name="testskill", description="Test", source="builtin", path=skill_dir)
    assert "---" in skill.documentation  # includes frontmatter
    assert "Instructions here" in skill.documentation


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


def test_skill_description_from_frontmatter():
    """Description comes from YAML frontmatter, not markdown heading."""
    config = Config()
    manager = SkillManager(config)
    git = manager.get_skill("git")
    assert git is not None
    # Should be the frontmatter description, not "Git Operations"
    assert "git" in git.description.lower()
    assert len(git.description) > 20  # frontmatter descriptions are longer


def test_skill_metadata_fields():
    """Skills should have metadata from frontmatter."""
    config = Config()
    manager = SkillManager(config)
    git = manager.get_skill("git")
    assert git is not None
    assert git.metadata.get("author") == "cody"
    assert git.metadata.get("version") == "1.0"


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
    project_skills = tmp_path / ".cody" / "skills" / "git"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text(
        "---\nname: git\ndescription: Custom project git skill.\n---\n\n"
        "# Project Git\n\nCustom project git."
    )

    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    config = Config()
    manager = SkillManager(config)
    git = manager.get_skill("git")
    assert git is not None
    assert git.source == "project"
    assert "Custom project git" in git.instructions


def test_skill_workdir_finds_project_skills(tmp_path):
    """SkillManager(workdir=X) discovers skills in X/.cody/skills, not cwd."""
    project_dir = tmp_path / "my-project"
    project_skills = project_dir / ".cody" / "skills" / "custom"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text(
        "---\nname: custom\ndescription: Workdir skill.\n---\n\n# Custom\n\nBody."
    )

    # No monkeypatch of cwd — workdir should be enough
    config = Config()
    manager = SkillManager(config, workdir=project_dir)
    skill = manager.get_skill("custom")
    assert skill is not None
    assert skill.source == "project"
    assert skill.description == "Workdir skill."


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


# ── to_prompt_xml ────────────────────────────────────────────────────────────


def test_to_prompt_xml():
    """Generates <available_skills> XML for system prompt."""
    config = Config()
    manager = SkillManager(config)
    xml = manager.to_prompt_xml()
    assert "<available_skills>" in xml
    assert "</available_skills>" in xml
    assert "<name>git</name>" in xml
    assert "<description>" in xml
    assert "<location>" in xml
    assert "SKILL.md</location>" in xml


def test_to_prompt_xml_empty():
    """Returns empty string when no skills enabled."""
    config = Config()
    manager = SkillManager.__new__(SkillManager)
    manager.config = config
    manager.skills = {}
    xml = manager.to_prompt_xml()
    assert xml == ""


# ── Validation ───────────────────────────────────────────────────────────────


def test_validate_skill_valid(tmp_path):
    skill_dir = _make_skill_dir(tmp_path)
    config = Config()
    manager = SkillManager(config)
    problems = manager.validate_skill(skill_dir)
    assert problems == []


def test_validate_skill_missing_skill_md(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    config = Config()
    manager = SkillManager(config)
    problems = manager.validate_skill(skill_dir)
    assert any("Missing SKILL.md" in p for p in problems)


def test_validate_skill_no_frontmatter(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# No frontmatter\n\nJust markdown.")
    config = Config()
    manager = SkillManager(config)
    problems = manager.validate_skill(skill_dir)
    assert any("frontmatter" in p.lower() for p in problems)


def test_validate_skill_missing_name(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: something\n---\n\nBody.")
    config = Config()
    manager = SkillManager(config)
    problems = manager.validate_skill(skill_dir)
    assert any("name" in p.lower() for p in problems)


def test_validate_skill_missing_description(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: bad\n---\n\nBody.")
    config = Config()
    manager = SkillManager(config)
    problems = manager.validate_skill(skill_dir)
    assert any("description" in p.lower() for p in problems)


def test_validate_skill_name_mismatch(tmp_path):
    skill_dir = tmp_path / "wrong"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: correct\ndescription: something\n---\n\nBody."
    )
    config = Config()
    manager = SkillManager(config)
    problems = manager.validate_skill(skill_dir)
    assert any("does not match" in p for p in problems)


# ── Skills without frontmatter are skipped ───────────────────────────────────


def test_plain_markdown_skill_skipped(tmp_path, monkeypatch):
    """Skills without YAML frontmatter are skipped (no backward compat)."""
    project_skills = tmp_path / ".cody" / "skills" / "legacy"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text("# Legacy Skill\n\nNo frontmatter.")

    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    config = Config()
    manager = SkillManager(config)
    assert manager.get_skill("legacy") is None


# ── Caching ─────────────────────────────────────────────────────────────────


def test_instructions_cached(tmp_path):
    """instructions property reads disk once, then returns cached value."""
    skill_dir = _make_skill_dir(tmp_path)
    skill = Skill(name="myskill", description="Does things", source="builtin", path=skill_dir)

    result1 = skill.instructions
    assert "Instructions here" in result1

    # Modify file on disk — cached value should persist
    (skill_dir / "SKILL.md").write_text(
        "---\nname: myskill\ndescription: Changed\n---\n\nNew body."
    )
    result2 = skill.instructions
    assert result2 == result1  # Still cached


def test_documentation_cached(tmp_path):
    """documentation property reads disk once, then returns cached value."""
    skill_dir = _make_skill_dir(tmp_path)
    skill = Skill(name="myskill", description="Does things", source="builtin", path=skill_dir)

    result1 = skill.documentation
    assert "---" in result1

    # Modify file on disk — cached value should persist
    (skill_dir / "SKILL.md").write_text(
        "---\nname: myskill\ndescription: Changed\n---\n\nNew body."
    )
    result2 = skill.documentation
    assert result2 == result1  # Still cached

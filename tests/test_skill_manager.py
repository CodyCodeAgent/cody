"""Tests for skill management system (Agent Skills open standard)"""

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


def _make_project_skill(tmp_path, name="git", description="Git operations for version control",
                        author="cody", version="1.0"):
    """Create a project-level skill in tmp_path/.cody/skills/ for testing."""
    skill_dir = tmp_path / ".cody" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  author: {author}\n  version: \"{version}\"\n---\n\n"
        f"# {name.title()}\n\nInstructions for {name}."
    )
    return skill_dir


def test_skill_manager_loads_project_skill(tmp_path):
    """SkillManager loads project-level skills."""
    _make_project_skill(tmp_path)
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    skills = manager.list_skills()
    names = [s.name for s in skills]
    assert "git" in names


def test_skill_manager_get_skill(tmp_path):
    _make_project_skill(tmp_path)
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    git = manager.get_skill("git")
    assert git is not None
    assert git.name == "git"
    assert git.source == "project"


def test_skill_manager_get_skill_not_found(tmp_path):
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    assert manager.get_skill("nonexistent_skill_xyz") is None


def test_skill_description_from_frontmatter(tmp_path):
    """Description comes from YAML frontmatter, not markdown heading."""
    _make_project_skill(tmp_path)
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    git = manager.get_skill("git")
    assert git is not None
    assert "git" in git.description.lower()
    assert len(git.description) > 20


def test_skill_metadata_fields(tmp_path):
    """Skills should have metadata from frontmatter."""
    _make_project_skill(tmp_path)
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    git = manager.get_skill("git")
    assert git is not None
    assert git.metadata.get("author") == "cody"
    assert git.metadata.get("version") == "1.0"


# ── Enable / Disable ─────────────────────────────────────────────────────────


def test_enable_skill(tmp_path):
    _make_project_skill(tmp_path)
    config = Config(skills={"enabled": [], "disabled": ["git"]})
    manager = SkillManager(config, workdir=tmp_path)

    git = manager.get_skill("git")
    assert git is not None
    assert git.enabled is False

    manager.enable_skill("git")
    assert manager.get_skill("git").enabled is True
    assert "git" in config.skills.enabled
    assert "git" not in config.skills.disabled


def test_disable_skill(tmp_path):
    _make_project_skill(tmp_path)
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)

    git = manager.get_skill("git")
    assert git is not None
    assert git.enabled is True

    manager.disable_skill("git")
    assert manager.get_skill("git").enabled is False
    assert "git" in config.skills.disabled


def test_enable_nonexistent_skill(tmp_path):
    """Enabling a skill that doesn't exist is a no-op."""
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    manager.enable_skill("nonexistent_skill_xyz")
    # No error raised


def test_disable_nonexistent_skill(tmp_path):
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    manager.disable_skill("nonexistent_skill_xyz")
    # No error raised


# ── Priority loading ─────────────────────────────────────────────────────────


def test_skill_priority_project_over_builtin(tmp_path):
    """Project skills take priority over builtin skills."""
    project_skills = tmp_path / ".cody" / "skills" / "git"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text(
        "---\nname: git\ndescription: Custom project git skill.\n---\n\n"
        "# Project Git\n\nCustom project git."
    )

    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
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


def test_is_enabled_default(tmp_path):
    """By default all skills are enabled."""
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    assert manager._is_enabled("anything") is True


def test_is_enabled_whitelist(tmp_path):
    """When enabled list is set, only listed skills are enabled."""
    config = Config(skills={"enabled": ["git"], "disabled": []})
    manager = SkillManager(config, workdir=tmp_path)
    assert manager._is_enabled("git") is True
    assert manager._is_enabled("docker") is False


def test_is_enabled_blacklist(tmp_path):
    """Disabled list takes precedence."""
    config = Config(skills={"enabled": [], "disabled": ["git"]})
    manager = SkillManager(config, workdir=tmp_path)
    assert manager._is_enabled("git") is False


# ── to_prompt_xml ────────────────────────────────────────────────────────────


def test_to_prompt_xml(tmp_path):
    """Generates <available_skills> XML for system prompt."""
    _make_project_skill(tmp_path)
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
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
    manager = SkillManager(config, workdir=tmp_path)
    problems = manager.validate_skill(skill_dir)
    assert problems == []


def test_validate_skill_missing_skill_md(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    problems = manager.validate_skill(skill_dir)
    assert any("Missing SKILL.md" in p for p in problems)


def test_validate_skill_no_frontmatter(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# No frontmatter\n\nJust markdown.")
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    problems = manager.validate_skill(skill_dir)
    assert any("frontmatter" in p.lower() for p in problems)


def test_validate_skill_missing_name(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: something\n---\n\nBody.")
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    problems = manager.validate_skill(skill_dir)
    assert any("name" in p.lower() for p in problems)


def test_validate_skill_missing_description(tmp_path):
    skill_dir = tmp_path / "bad"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: bad\n---\n\nBody.")
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    problems = manager.validate_skill(skill_dir)
    assert any("description" in p.lower() for p in problems)


def test_validate_skill_name_mismatch(tmp_path):
    skill_dir = tmp_path / "wrong"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: correct\ndescription: something\n---\n\nBody."
    )
    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
    problems = manager.validate_skill(skill_dir)
    assert any("does not match" in p for p in problems)


# ── Skills without frontmatter are skipped ───────────────────────────────────


def test_plain_markdown_skill_skipped(tmp_path):
    """Skills without YAML frontmatter are skipped (no backward compat)."""
    project_skills = tmp_path / ".cody" / "skills" / "legacy"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text("# Legacy Skill\n\nNo frontmatter.")

    config = Config()
    manager = SkillManager(config, workdir=tmp_path)
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


# ── Custom skill directories ─────────────────────────────────────────────────


def test_custom_skill_dirs_loaded(tmp_path):
    """Skills in custom_dirs are loaded with source='custom'."""
    custom_dir = tmp_path / "my-skills"
    skill_dir = custom_dir / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: A custom hello skill\n---\n\nHello!"
    )

    config = Config(skills={"custom_dirs": [str(custom_dir)]})
    manager = SkillManager(config, workdir=tmp_path)
    skill = manager.get_skill("hello")
    assert skill is not None
    assert skill.source == "custom"
    assert skill.description == "A custom hello skill"


def test_custom_dirs_highest_priority(tmp_path):
    """Custom dir skills override project-level skills with the same name."""
    # Create a project-level skill
    project_skills = tmp_path / ".cody" / "skills" / "myskill"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text(
        "---\nname: myskill\ndescription: Project version\n---\n\nProject."
    )

    # Create a custom dir skill with the same name
    custom_dir = tmp_path / "custom-skills"
    custom_skill = custom_dir / "myskill"
    custom_skill.mkdir(parents=True)
    (custom_skill / "SKILL.md").write_text(
        "---\nname: myskill\ndescription: Custom version\n---\n\nCustom."
    )

    config = Config(skills={"custom_dirs": [str(custom_dir)]})
    manager = SkillManager(config, workdir=tmp_path)
    skill = manager.get_skill("myskill")
    assert skill is not None
    assert skill.source == "custom"
    assert skill.description == "Custom version"


def test_custom_dirs_supplement_defaults(tmp_path):
    """Custom dirs supplement (not replace) the default search paths."""
    # Create a project-level skill
    _make_project_skill(tmp_path)

    custom_dir = tmp_path / "my-skills"
    skill_dir = custom_dir / "hello"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: hello\ndescription: A custom skill\n---\n\nHello!"
    )

    config = Config(skills={"custom_dirs": [str(custom_dir)]})
    manager = SkillManager(config, workdir=tmp_path)

    # Custom skill loaded
    assert manager.get_skill("hello") is not None
    # Project skills still available
    assert manager.get_skill("git") is not None


def test_custom_dirs_from_env(tmp_path, monkeypatch):
    """CODY_SKILL_DIRS env var populates skills.custom_dirs."""
    custom_dir = tmp_path / "env-skills"
    skill_dir = custom_dir / "envskill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: envskill\ndescription: From env\n---\n\nEnv skill."
    )

    monkeypatch.setenv("CODY_SKILL_DIRS", str(custom_dir))
    config = Config.load(workdir=tmp_path)
    assert str(custom_dir) in config.skills.custom_dirs

    manager = SkillManager(config, workdir=tmp_path)
    skill = manager.get_skill("envskill")
    assert skill is not None
    assert skill.source == "custom"


def test_apply_overrides_skill_dirs():
    """apply_overrides(skill_dirs=...) appends to custom_dirs with dedup."""
    config = Config(skills={"custom_dirs": ["/existing"]})
    config.apply_overrides(skill_dirs=["/new", "/existing", "/another"])
    assert config.skills.custom_dirs == ["/existing", "/new", "/another"]

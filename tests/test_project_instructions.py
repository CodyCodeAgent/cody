"""Tests for cody/core/project_instructions.py"""



from cody.core.project_instructions import (
    CODY_MD_FILENAME,
    CODY_MD_TEMPLATE,
    load_project_instructions,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_cody_md_filename():
    assert CODY_MD_FILENAME == "CODY.md"


def test_cody_md_template_is_non_empty():
    assert CODY_MD_TEMPLATE.strip()


def test_cody_md_template_is_string():
    assert isinstance(CODY_MD_TEMPLATE, str)


# ---------------------------------------------------------------------------
# load_project_instructions — no files present
# ---------------------------------------------------------------------------


def test_returns_none_when_no_files(tmp_path, monkeypatch):
    """Returns None when neither global nor project CODY.md exists."""
    monkeypatch.setenv("HOME", str(tmp_path))
    result = load_project_instructions(tmp_path / "project")
    assert result is None


# ---------------------------------------------------------------------------
# load_project_instructions — project-only
# ---------------------------------------------------------------------------


def test_returns_project_content_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("# My Project\nHello.", encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert result == "# My Project\nHello."


def test_strips_leading_trailing_whitespace_project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("\n\n# Project\n\n", encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert result == "# Project"


def test_empty_project_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("   \n\n   ", encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert result is None


# ---------------------------------------------------------------------------
# load_project_instructions — global-only
# ---------------------------------------------------------------------------


def test_returns_global_content_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    global_cody_dir = tmp_path / ".cody"
    global_cody_dir.mkdir()
    (global_cody_dir / CODY_MD_FILENAME).write_text("# Global Instructions", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = load_project_instructions(project_dir)
    assert result == "# Global Instructions"


def test_empty_global_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    global_cody_dir = tmp_path / ".cody"
    global_cody_dir.mkdir()
    (global_cody_dir / CODY_MD_FILENAME).write_text("", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = load_project_instructions(project_dir)
    assert result is None


# ---------------------------------------------------------------------------
# load_project_instructions — both files present
# ---------------------------------------------------------------------------


def test_merges_global_and_project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    global_cody_dir = tmp_path / ".cody"
    global_cody_dir.mkdir()
    (global_cody_dir / CODY_MD_FILENAME).write_text("# Global", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("# Project", encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert result == "# Global\n\n---\n\n# Project"


def test_global_comes_before_project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    global_cody_dir = tmp_path / ".cody"
    global_cody_dir.mkdir()
    (global_cody_dir / CODY_MD_FILENAME).write_text("GLOBAL_CONTENT", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("PROJECT_CONTENT", encoding="utf-8")

    result = load_project_instructions(project_dir)
    global_idx = result.index("GLOBAL_CONTENT")
    project_idx = result.index("PROJECT_CONTENT")
    assert global_idx < project_idx


def test_separator_present_when_both_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    global_cody_dir = tmp_path / ".cody"
    global_cody_dir.mkdir()
    (global_cody_dir / CODY_MD_FILENAME).write_text("A", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("B", encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert "---" in result


def test_no_separator_when_only_one_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("Only project", encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert "---" not in result


def test_empty_global_does_not_produce_separator(tmp_path, monkeypatch):
    """If global file is empty/whitespace, only project content returned, no separator."""
    monkeypatch.setenv("HOME", str(tmp_path))

    global_cody_dir = tmp_path / ".cody"
    global_cody_dir.mkdir()
    (global_cody_dir / CODY_MD_FILENAME).write_text("   ", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / CODY_MD_FILENAME).write_text("Project only", encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert result == "Project only"
    assert "---" not in result


# ---------------------------------------------------------------------------
# load_project_instructions — unicode / encoding
# ---------------------------------------------------------------------------


def test_handles_unicode_content(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    content = "# 项目说明\n\n这是一个 Python 项目。"
    (project_dir / CODY_MD_FILENAME).write_text(content, encoding="utf-8")

    result = load_project_instructions(project_dir)
    assert result == content

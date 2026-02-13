"""Tests for core tools"""

import pytest
from pathlib import Path
from cody.core.tools import (
    read_file, write_file, edit_file, list_directory,
    grep, glob, patch, search_files,
)
from cody.core.config import Config
from cody.core.skill_manager import SkillManager
from cody.core.runner import CodyDeps


class MockContext:
    """Mock RunContext for testing"""
    def __init__(self, workdir):
        config = Config()
        self.deps = CodyDeps(
            config=config,
            workdir=Path(workdir),
            skill_manager=SkillManager(config),
        )


# ── File operation tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_and_read_file(tmp_path):
    ctx = MockContext(tmp_path)

    result = await write_file(ctx, "test.txt", "Hello, World!")
    assert "Written" in result

    content = await read_file(ctx, "test.txt")
    assert content == "Hello, World!"


@pytest.mark.asyncio
async def test_edit_file(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "code.py").write_text("def foo():\n    return 1\n")

    result = await edit_file(ctx, "code.py", "return 1", "return 42")
    assert "Edited" in result

    content = (tmp_path / "code.py").read_text()
    assert "return 42" in content
    assert "return 1" not in content


@pytest.mark.asyncio
async def test_edit_file_text_not_found(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "code.py").write_text("def foo():\n    pass\n")

    with pytest.raises(ValueError, match="Text not found"):
        await edit_file(ctx, "code.py", "nonexistent text", "new text")


@pytest.mark.asyncio
async def test_list_directory(tmp_path):
    ctx = MockContext(tmp_path)

    (tmp_path / "file1.txt").write_text("test")
    (tmp_path / "file2.py").write_text("test")
    (tmp_path / "subdir").mkdir()

    result = await list_directory(ctx, ".")
    assert "file1.txt" in result
    assert "file2.py" in result
    assert "subdir" in result


# ── Security tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_security_check_path_traversal(tmp_path):
    ctx = MockContext(tmp_path)

    with pytest.raises(ValueError, match="outside working directory"):
        await read_file(ctx, "../../../etc/passwd")


@pytest.mark.asyncio
async def test_security_check_write_outside(tmp_path):
    ctx = MockContext(tmp_path)

    with pytest.raises(ValueError, match="outside working directory"):
        await write_file(ctx, "../../evil.txt", "bad content")


@pytest.mark.asyncio
async def test_security_check_symlink_escape(tmp_path):
    """Symlinks that escape workdir should be caught"""
    ctx = MockContext(tmp_path)

    # Create a symlink pointing outside
    link = tmp_path / "escape"
    link.symlink_to("/tmp")

    with pytest.raises(ValueError, match="outside working directory"):
        await read_file(ctx, "escape/some_file")


# ── Grep tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_grep_basic(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "hello.py").write_text("def hello():\n    print('world')\n")
    (tmp_path / "other.txt").write_text("nothing here\n")

    result = await grep(ctx, "def hello")
    assert "hello.py:1:" in result
    assert "def hello" in result


@pytest.mark.asyncio
async def test_grep_regex(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "code.py").write_text("x = 123\ny = 456\nz = abc\n")

    result = await grep(ctx, r"\d{3}")
    assert "code.py:1:" in result
    assert "code.py:2:" in result
    assert "z = abc" not in result


@pytest.mark.asyncio
async def test_grep_include_filter(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "code.py").write_text("def foo(): pass\n")
    (tmp_path / "readme.md").write_text("def foo in docs\n")

    result = await grep(ctx, "def foo", include="*.py")
    assert "code.py" in result
    assert "readme.md" not in result


@pytest.mark.asyncio
async def test_grep_no_matches(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.txt").write_text("hello world\n")

    result = await grep(ctx, "nonexistent_pattern")
    assert "No matches found" in result


@pytest.mark.asyncio
async def test_grep_invalid_regex(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.txt").write_text("test\n")

    with pytest.raises(ValueError, match="Invalid regex"):
        await grep(ctx, "[invalid")


@pytest.mark.asyncio
async def test_grep_single_file(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "target.py").write_text("line1\nmatch_me\nline3\n")

    result = await grep(ctx, "match_me", path="target.py")
    assert "target.py:2:" in result


# ── Glob tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_glob_star_py(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "main.py").write_text("")
    (tmp_path / "utils.py").write_text("")
    (tmp_path / "readme.md").write_text("")

    result = await glob(ctx, "*.py")
    assert "main.py" in result
    assert "utils.py" in result
    assert "readme.md" not in result


@pytest.mark.asyncio
async def test_glob_recursive(tmp_path):
    ctx = MockContext(tmp_path)
    sub = tmp_path / "src" / "core"
    sub.mkdir(parents=True)
    (sub / "engine.py").write_text("")
    (tmp_path / "main.py").write_text("")

    result = await glob(ctx, "**/*.py")
    assert "main.py" in result
    assert "engine.py" in result


@pytest.mark.asyncio
async def test_glob_no_matches(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.txt").write_text("")

    result = await glob(ctx, "*.rs")
    assert "No files matched" in result


# ── Patch tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_add_line(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.py").write_text("line1\nline2\nline3\n")

    diff = (
        "@@ -2,2 +2,3 @@\n"
        " line2\n"
        "+new_line\n"
        " line3\n"
    )
    result = await patch(ctx, "file.py", diff)
    assert "Patched" in result

    content = (tmp_path / "file.py").read_text()
    assert "new_line" in content
    assert content.index("line2") < content.index("new_line") < content.index("line3")


@pytest.mark.asyncio
async def test_patch_remove_line(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.py").write_text("line1\ndelete_me\nline3\n")

    diff = (
        "@@ -1,3 +1,2 @@\n"
        " line1\n"
        "-delete_me\n"
        " line3\n"
    )
    result = await patch(ctx, "file.py", diff)
    assert "Patched" in result

    content = (tmp_path / "file.py").read_text()
    assert "delete_me" not in content
    assert "line1\nline3\n" == content


@pytest.mark.asyncio
async def test_patch_replace_line(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.py").write_text("old_value = 1\n")

    diff = (
        "@@ -1,1 +1,1 @@\n"
        "-old_value = 1\n"
        "+new_value = 42\n"
    )
    result = await patch(ctx, "file.py", diff)
    assert "Patched" in result

    content = (tmp_path / "file.py").read_text()
    assert "new_value = 42" in content
    assert "old_value" not in content


@pytest.mark.asyncio
async def test_patch_file_not_found(tmp_path):
    ctx = MockContext(tmp_path)

    with pytest.raises(FileNotFoundError):
        await patch(ctx, "nonexistent.py", "@@ -1,1 +1,1 @@\n-a\n+b\n")


@pytest.mark.asyncio
async def test_patch_with_headers(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.py").write_text("aaa\nbbb\nccc\n")

    diff = (
        "--- a/file.py\n"
        "+++ b/file.py\n"
        "@@ -1,3 +1,3 @@\n"
        " aaa\n"
        "-bbb\n"
        "+BBB\n"
        " ccc\n"
    )
    result = await patch(ctx, "file.py", diff)
    assert "Patched" in result
    assert (tmp_path / "file.py").read_text() == "aaa\nBBB\nccc\n"


# ── Search files tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_files_exact_match(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "config.py").write_text("")
    (tmp_path / "config_test.py").write_text("")
    (tmp_path / "readme.md").write_text("")

    result = await search_files(ctx, "config.py")
    lines = result.strip().split("\n")
    # Exact match should come first
    assert lines[0] == "config.py"


@pytest.mark.asyncio
async def test_search_files_contains(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "my_config.py").write_text("")
    (tmp_path / "other.txt").write_text("")

    result = await search_files(ctx, "config")
    assert "my_config.py" in result
    assert "other.txt" not in result


@pytest.mark.asyncio
async def test_search_files_in_subdirectory(tmp_path):
    ctx = MockContext(tmp_path)
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "utils.py").write_text("")
    (tmp_path / "main.py").write_text("")

    result = await search_files(ctx, "utils")
    assert "utils.py" in result


@pytest.mark.asyncio
async def test_search_files_case_insensitive(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "README.md").write_text("")

    result = await search_files(ctx, "readme")
    assert "README.md" in result


@pytest.mark.asyncio
async def test_search_files_no_match(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "file.txt").write_text("")

    result = await search_files(ctx, "nonexistent")
    assert "No files found" in result


@pytest.mark.asyncio
async def test_search_files_path_contains(tmp_path):
    ctx = MockContext(tmp_path)
    sub = tmp_path / "api" / "v2"
    sub.mkdir(parents=True)
    (sub / "handler.py").write_text("")

    result = await search_files(ctx, "api")
    assert "handler.py" in result

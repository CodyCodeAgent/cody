"""Tests for core tools"""

import pytest
from pathlib import Path
from cody.core.tools import (
    read_file, write_file, edit_file, list_directory,
    grep, glob, patch, search_files,
    _is_binary, _parse_gitignore, _is_gitignored, _iter_files,
)
from cody.core.config import Config
from cody.core.skill_manager import SkillManager
from cody.core.deps import CodyDeps


class MockContext:
    """Mock RunContext for testing"""
    def __init__(self, workdir):
        workdir = Path(workdir)
        config = Config()
        self.deps = CodyDeps(
            config=config,
            workdir=workdir,
            skill_manager=SkillManager(config, workdir=workdir),
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
async def test_read_file_outside_workdir_allowed(tmp_path):
    """read_file allows reading outside workdir (read-only is safe)"""
    ctx = MockContext(tmp_path)

    # Reading outside workdir is allowed but file may not exist
    with pytest.raises(FileNotFoundError):
        await read_file(ctx, "../../../nonexistent_file.txt")


@pytest.mark.asyncio
async def test_security_check_write_outside(tmp_path):
    ctx = MockContext(tmp_path)

    with pytest.raises(ValueError, match="outside working directory"):
        await write_file(ctx, "../../evil.txt", "bad content")


@pytest.mark.asyncio
async def test_security_check_symlink_write_escape(tmp_path):
    """Write via symlinks that escape workdir should be caught"""
    ctx = MockContext(tmp_path)

    # Create a symlink pointing outside
    link = tmp_path / "escape"
    link.symlink_to("/tmp")

    with pytest.raises(ValueError, match="outside working directory"):
        await write_file(ctx, "escape/evil.txt", "bad content")


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


# ── Binary file detection tests ─────────────────────────────────────────────


def test_is_binary_with_text_file(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("Hello, World!\n")
    assert _is_binary(f) is False


def test_is_binary_with_binary_file(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"some data\x00more data")
    assert _is_binary(f) is True


def test_is_binary_empty_file(tmp_path):
    f = tmp_path / "empty"
    f.write_bytes(b"")
    assert _is_binary(f) is False


def test_is_binary_utf8(tmp_path):
    f = tmp_path / "utf8.txt"
    f.write_text("你好世界\nこんにちは\n")
    assert _is_binary(f) is False


# ── Gitignore parsing tests ─────────────────────────────────────────────────


def test_parse_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n# comment\n\n*.log\n")
    patterns = _parse_gitignore(tmp_path)
    assert patterns == ["*.pyc", "__pycache__/", "*.log"]


def test_parse_gitignore_missing(tmp_path):
    patterns = _parse_gitignore(tmp_path)
    assert patterns == []


def test_is_gitignored_simple():
    patterns = ["*.pyc", "*.log"]
    assert _is_gitignored("foo.pyc", patterns) is True
    assert _is_gitignored("foo.py", patterns) is False
    assert _is_gitignored("app.log", patterns) is True


def test_is_gitignored_dir_pattern():
    patterns = ["build/"]
    assert _is_gitignored("build", patterns, is_dir=True) is True
    # File inside build dir: the dir pattern matches parent component
    assert _is_gitignored("build/output.js", patterns) is True
    # A file named "build" is NOT matched by a dir-only pattern
    assert _is_gitignored("build", patterns, is_dir=False) is False


def test_is_gitignored_negation():
    patterns = ["*.log", "!important.log"]
    assert _is_gitignored("debug.log", patterns) is True
    assert _is_gitignored("important.log", patterns) is False


def test_is_gitignored_anchored():
    patterns = ["/dist"]
    assert _is_gitignored("dist", patterns) is True
    assert _is_gitignored("src/dist", patterns) is False


def test_is_gitignored_nested_path():
    patterns = ["docs/generated"]
    assert _is_gitignored("docs/generated", patterns, is_dir=True) is True
    assert _is_gitignored("other/generated", patterns, is_dir=True) is False


# ── Default ignore tests (grep) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_grep_skips_node_modules(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "app.js").write_text("const x = 1\n")
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("const x = 2\n")

    result = await grep(ctx, "const x")
    assert "app.js" in result
    assert "node_modules" not in result


@pytest.mark.asyncio
async def test_grep_skips_pycache(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "main.py").write_text("hello = True\n")
    pc = tmp_path / "__pycache__"
    pc.mkdir()
    (pc / "main.cpython-311.pyc").write_bytes(b"\x00\x00compiled")

    result = await grep(ctx, "hello")
    assert "main.py:1:" in result
    assert "__pycache__" not in result


@pytest.mark.asyncio
async def test_grep_skips_git_dir(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "code.py").write_text("real code\n")
    git = tmp_path / ".git" / "objects"
    git.mkdir(parents=True)
    (git / "abc123").write_text("git internal\n")

    result = await grep(ctx, "code")
    assert "code.py" in result
    assert ".git" not in result


@pytest.mark.asyncio
async def test_grep_skips_binary_files(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "readme.txt").write_text("hello world\n")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00more binary data")

    result = await grep(ctx, "hello")
    assert "readme.txt" in result
    # Binary file should be skipped, not error
    assert "image.png" not in result


@pytest.mark.asyncio
async def test_grep_respects_gitignore(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / ".gitignore").write_text("*.log\ntemp/\n")
    (tmp_path / "app.py").write_text("logging\n")
    (tmp_path / "debug.log").write_text("logging\n")
    temp = tmp_path / "temp"
    temp.mkdir()
    (temp / "scratch.py").write_text("logging\n")

    result = await grep(ctx, "logging")
    assert "app.py" in result
    assert "debug.log" not in result
    assert "temp" not in result


@pytest.mark.asyncio
async def test_grep_gitignore_negation(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / ".gitignore").write_text("*.log\n!important.log\n")
    (tmp_path / "debug.log").write_text("error line\n")
    (tmp_path / "important.log").write_text("error line\n")

    result = await grep(ctx, "error line")
    assert "debug.log" not in result
    assert "important.log" in result


# ── Default ignore tests (glob) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_glob_skips_node_modules(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "app.js").write_text("")
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("")

    result = await glob(ctx, "**/*.js")
    assert "app.js" in result
    assert "node_modules" not in result


@pytest.mark.asyncio
async def test_glob_skips_hidden_dirs(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "main.py").write_text("")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "secret.py").write_text("")

    result = await glob(ctx, "**/*.py")
    assert "main.py" in result
    assert ".hidden" not in result


@pytest.mark.asyncio
async def test_glob_respects_gitignore(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / ".gitignore").write_text("*.generated.py\n")
    (tmp_path / "app.py").write_text("")
    (tmp_path / "models.generated.py").write_text("")

    result = await glob(ctx, "**/*.py")
    assert "app.py" in result
    assert "generated" not in result


# ── Default ignore tests (search_files) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_search_files_skips_node_modules(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "utils.js").write_text("")
    nm = tmp_path / "node_modules" / "lodash"
    nm.mkdir(parents=True)
    (nm / "utils.js").write_text("")

    result = await search_files(ctx, "utils")
    lines = result.strip().split("\n")
    assert len(lines) == 1
    assert lines[0] == "utils.js"


@pytest.mark.asyncio
async def test_search_files_skips_hidden(tmp_path):
    ctx = MockContext(tmp_path)
    (tmp_path / "config.py").write_text("")
    vscode = tmp_path / ".vscode"
    vscode.mkdir()
    (vscode / "config.json").write_text("")

    result = await search_files(ctx, "config")
    assert "config.py" in result
    assert ".vscode" not in result


# ── iter_files tests ─────────────────────────────────────────────────────────


def test_iter_files_prunes_ignored_dirs(tmp_path):
    (tmp_path / "real.py").write_text("code")
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "lib.js").write_text("code")
    pc = tmp_path / "__pycache__"
    pc.mkdir()
    (pc / "mod.pyc").write_bytes(b"\x00compiled")

    files = _iter_files(tmp_path, tmp_path, [])
    names = [f.name for f in files]
    assert "real.py" in names
    assert "lib.js" not in names
    assert "mod.pyc" not in names


def test_iter_files_respects_gitignore(tmp_path):
    (tmp_path / "app.py").write_text("code")
    (tmp_path / "debug.log").write_text("log")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("log")

    files = _iter_files(tmp_path, tmp_path, ["*.log", "logs/"])
    names = [f.name for f in files]
    assert "app.py" in names
    assert "debug.log" not in names
    assert "app.log" not in names

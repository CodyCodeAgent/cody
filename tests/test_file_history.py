"""Tests for file modification history (undo/redo)"""


from cody.core.file_history import FileHistory


# ── record ───────────────────────────────────────────────────────────────────


def test_record_basic(tmp_path):
    history = FileHistory(workdir=tmp_path)
    change = history.record("hello.py", "", "print('hello')", operation="write")

    assert change.file_path == "hello.py"
    assert change.old_content == ""
    assert change.new_content == "print('hello')"
    assert change.operation == "write"
    assert len(change.id) == 12


def test_record_clears_redo(tmp_path):
    history = FileHistory(workdir=tmp_path)

    # Write a file, then undo, then record new change
    (tmp_path / "a.txt").write_text("original")
    history.record("a.txt", "", "original", operation="write")
    history.undo()
    assert history.can_redo()

    history.record("b.txt", "", "new", operation="write")
    assert not history.can_redo()


def test_record_max_history(tmp_path):
    history = FileHistory(workdir=tmp_path, max_history=3)

    for i in range(5):
        history.record(f"file_{i}.txt", "", f"content_{i}", operation="write")

    assert history.undo_count == 3


# ── undo ─────────────────────────────────────────────────────────────────────


def test_undo_restores_content(tmp_path):
    history = FileHistory(workdir=tmp_path)

    # Create file
    f = tmp_path / "hello.py"
    f.write_text("new content")
    history.record("hello.py", "old content", "new content", operation="write")

    # Undo should restore old content
    change = history.undo()
    assert change is not None
    assert change.file_path == "hello.py"
    assert f.read_text() == "old content"


def test_undo_empty_stack(tmp_path):
    history = FileHistory(workdir=tmp_path)
    assert history.undo() is None


def test_undo_multiple(tmp_path):
    history = FileHistory(workdir=tmp_path)
    f = tmp_path / "a.txt"

    f.write_text("v1")
    history.record("a.txt", "", "v1", operation="write")

    f.write_text("v2")
    history.record("a.txt", "v1", "v2", operation="edit")

    f.write_text("v3")
    history.record("a.txt", "v2", "v3", operation="edit")

    # Undo back to v2
    history.undo()
    assert f.read_text() == "v2"

    # Undo back to v1
    history.undo()
    assert f.read_text() == "v1"

    # Undo back to empty
    history.undo()
    assert f.read_text() == ""


def test_undo_creates_parent_dirs(tmp_path):
    history = FileHistory(workdir=tmp_path)
    subdir = tmp_path / "sub"
    subdir.mkdir()
    f = subdir / "deep.txt"
    f.write_text("content")
    history.record("sub/deep.txt", "old", "content", operation="write")

    history.undo()
    assert f.read_text() == "old"


# ── redo ─────────────────────────────────────────────────────────────────────


def test_redo_reapplies_content(tmp_path):
    history = FileHistory(workdir=tmp_path)
    f = tmp_path / "hello.py"

    f.write_text("new content")
    history.record("hello.py", "old content", "new content", operation="write")

    history.undo()
    assert f.read_text() == "old content"

    change = history.redo()
    assert change is not None
    assert f.read_text() == "new content"


def test_redo_empty_stack(tmp_path):
    history = FileHistory(workdir=tmp_path)
    assert history.redo() is None


def test_redo_after_new_record_cleared(tmp_path):
    history = FileHistory(workdir=tmp_path)
    f = tmp_path / "a.txt"

    f.write_text("v1")
    history.record("a.txt", "", "v1", operation="write")

    history.undo()
    # New record should clear redo
    history.record("a.txt", "", "v2", operation="write")
    assert history.redo() is None


# ── list_changes ─────────────────────────────────────────────────────────────


def test_list_changes(tmp_path):
    history = FileHistory(workdir=tmp_path)

    history.record("a.txt", "", "a", operation="write")
    history.record("b.txt", "", "b", operation="write")
    history.record("c.txt", "", "c", operation="write")

    changes = history.list_changes()
    assert len(changes) == 3
    # Most recent first
    assert changes[0].file_path == "c.txt"
    assert changes[2].file_path == "a.txt"


def test_list_changes_with_limit(tmp_path):
    history = FileHistory(workdir=tmp_path)

    for i in range(10):
        history.record(f"file_{i}.txt", "", f"content_{i}", operation="write")

    changes = history.list_changes(limit=3)
    assert len(changes) == 3


def test_list_changes_empty(tmp_path):
    history = FileHistory(workdir=tmp_path)
    assert history.list_changes() == []


# ── can_undo / can_redo ──────────────────────────────────────────────────────


def test_can_undo_redo(tmp_path):
    history = FileHistory(workdir=tmp_path)

    assert not history.can_undo()
    assert not history.can_redo()

    (tmp_path / "a.txt").write_text("content")
    history.record("a.txt", "", "content", operation="write")

    assert history.can_undo()
    assert not history.can_redo()

    history.undo()

    assert not history.can_undo()
    assert history.can_redo()


# ── counts ───────────────────────────────────────────────────────────────────


def test_undo_redo_counts(tmp_path):
    history = FileHistory(workdir=tmp_path)

    assert history.undo_count == 0
    assert history.redo_count == 0

    (tmp_path / "a.txt").write_text("v1")
    history.record("a.txt", "", "v1", operation="write")
    (tmp_path / "a.txt").write_text("v2")
    history.record("a.txt", "v1", "v2", operation="edit")

    assert history.undo_count == 2
    assert history.redo_count == 0

    history.undo()
    assert history.undo_count == 1
    assert history.redo_count == 1

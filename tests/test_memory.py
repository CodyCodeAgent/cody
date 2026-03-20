"""Tests for ProjectMemoryStore."""


import pytest

from cody.core.memory import (
    MAX_ENTRIES_PER_CATEGORY,
    MemoryEntry,
    ProjectMemoryStore,
    _project_id,
)


class TestProjectId:
    def test_deterministic(self, tmp_path):
        p1 = _project_id(tmp_path)
        p2 = _project_id(tmp_path)
        assert p1 == p2

    def test_different_paths(self, tmp_path):
        d1 = tmp_path / "project-a"
        d2 = tmp_path / "project-b"
        d1.mkdir()
        d2.mkdir()
        assert _project_id(d1) != _project_id(d2)

    def test_length(self, tmp_path):
        assert len(_project_id(tmp_path)) == 12


class TestProjectMemoryStore:
    @pytest.fixture
    def store(self, tmp_path):
        return ProjectMemoryStore("test_proj", base_dir=tmp_path)

    @pytest.fixture
    def store_from_workdir(self, tmp_path):
        workdir = tmp_path / "myproject"
        workdir.mkdir()
        base = tmp_path / "memory"
        return ProjectMemoryStore.from_workdir(workdir, base_dir=base)

    def test_from_workdir(self, store_from_workdir):
        assert store_from_workdir.store_dir.exists()

    @pytest.mark.asyncio
    async def test_add_and_get_entries(self, store):
        entries = [
            MemoryEntry(content="Use ruff for linting"),
            MemoryEntry(content="Line width is 100"),
        ]
        await store.add_entries("conventions", entries)

        all_entries = store.get_all_entries()
        assert "conventions" in all_entries
        assert len(all_entries["conventions"]) == 2
        assert all_entries["conventions"][0].content == "Use ruff for linting"

    @pytest.mark.asyncio
    async def test_invalid_category(self, store):
        with pytest.raises(ValueError, match="Unknown memory category"):
            await store.add_entries("invalid_cat", [MemoryEntry(content="x")])

    @pytest.mark.asyncio
    async def test_max_entries_enforced(self, store):
        entries = [MemoryEntry(content=f"entry-{i}") for i in range(60)]
        await store.add_entries("patterns", entries)

        all_entries = store.get_all_entries()
        assert len(all_entries["patterns"]) == MAX_ENTRIES_PER_CATEGORY
        # Should keep the most recent
        assert all_entries["patterns"][-1].content == "entry-59"

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path):
        store1 = ProjectMemoryStore("persist_test", base_dir=tmp_path)
        await store1.add_entries("issues", [MemoryEntry(content="Bug in parser")])

        store2 = ProjectMemoryStore("persist_test", base_dir=tmp_path)
        all_entries = store2.get_all_entries()
        assert len(all_entries["issues"]) == 1
        assert all_entries["issues"][0].content == "Bug in parser"

    def test_get_memory_for_prompt_empty(self, store):
        prompt = store.get_memory_for_prompt()
        assert prompt == ""

    @pytest.mark.asyncio
    async def test_get_memory_for_prompt_with_entries(self, store):
        await store.add_entries("conventions", [MemoryEntry(content="Use snake_case")])
        await store.add_entries("decisions", [MemoryEntry(content="Chose FastAPI")])

        prompt = store.get_memory_for_prompt()
        assert "Project Memory" in prompt
        assert "Use snake_case" in prompt
        assert "Chose FastAPI" in prompt

    @pytest.mark.asyncio
    async def test_cleanup_low_confidence(self, store):
        entries = [
            MemoryEntry(content="keep me", confidence=0.8),
            MemoryEntry(content="remove me", confidence=0.1),
        ]
        await store.add_entries("issues", entries)
        await store.cleanup()

        all_entries = store.get_all_entries()
        assert len(all_entries["issues"]) == 1
        assert all_entries["issues"][0].content == "keep me"

    def test_count_empty(self, store):
        counts = store.count()
        assert all(c == 0 for c in counts.values())

    @pytest.mark.asyncio
    async def test_count_with_entries(self, store):
        await store.add_entries("conventions", [MemoryEntry(content="x")])
        await store.add_entries("patterns", [
            MemoryEntry(content="a"),
            MemoryEntry(content="b"),
        ])
        counts = store.count()
        assert counts["conventions"] == 1
        assert counts["patterns"] == 2
        assert counts["issues"] == 0

    @pytest.mark.asyncio
    async def test_clear(self, store):
        await store.add_entries("conventions", [MemoryEntry(content="x")])
        await store.add_entries("patterns", [MemoryEntry(content="y")])
        store.clear()

        counts = store.count()
        assert all(c == 0 for c in counts.values())

    @pytest.mark.asyncio
    async def test_memory_entry_fields(self, store):
        entry = MemoryEntry(
            content="Always run tests before commit",
            source_task_id="task_001",
            source_task_title="Fix CI",
            confidence=0.95,
            tags=["ci", "testing"],
        )
        await store.add_entries("conventions", [entry])

        loaded = store.get_all_entries()["conventions"][0]
        assert loaded.content == "Always run tests before commit"
        assert loaded.source_task_id == "task_001"
        assert loaded.confidence == 0.95
        assert "ci" in loaded.tags

    @pytest.mark.asyncio
    async def test_low_confidence_excluded_from_prompt(self, store):
        entries = [
            MemoryEntry(content="visible", confidence=0.5),
            MemoryEntry(content="hidden", confidence=0.1),
        ]
        await store.add_entries("conventions", entries)
        prompt = store.get_memory_for_prompt()
        assert "visible" in prompt
        assert "hidden" not in prompt

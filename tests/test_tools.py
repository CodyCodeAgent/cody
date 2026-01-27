"""Tests for core tools"""

import pytest
from pathlib import Path
from cody.core.tools import read_file, write_file, list_directory
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


@pytest.mark.asyncio
async def test_write_and_read_file(tmp_path):
    """Test writing and reading files"""
    ctx = MockContext(tmp_path)
    
    # Write file
    result = await write_file(ctx, "test.txt", "Hello, World!")
    assert "Written" in result
    
    # Read file
    content = await read_file(ctx, "test.txt")
    assert content == "Hello, World!"


@pytest.mark.asyncio
async def test_list_directory(tmp_path):
    """Test listing directory contents"""
    ctx = MockContext(tmp_path)
    
    # Create some files
    (tmp_path / "file1.txt").write_text("test")
    (tmp_path / "file2.py").write_text("test")
    (tmp_path / "subdir").mkdir()
    
    # List directory
    result = await list_directory(ctx, ".")
    assert "file1.txt" in result
    assert "file2.py" in result
    assert "subdir" in result


@pytest.mark.asyncio
async def test_security_check(tmp_path):
    """Test security checks prevent accessing outside workdir"""
    ctx = MockContext(tmp_path)
    
    # Try to read outside workdir
    with pytest.raises(ValueError, match="outside working directory"):
        await read_file(ctx, "../../../etc/passwd")

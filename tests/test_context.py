"""Tests for context management module"""

from cody.core.context import (
    CompactResult,
    FileChunk,
    chunk_file,
    compact_messages,
    estimate_tokens,
    select_relevant_context,
)


# ── estimate_tokens ──────────────────────────────────────────────────────────


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 1  # min is 1


def test_estimate_tokens_short():
    # "hello" = 5 chars → 5 // 4 = 1
    assert estimate_tokens("hello") >= 1


def test_estimate_tokens_longer():
    text = "a" * 400
    tokens = estimate_tokens(text)
    assert tokens == 100  # 400 // 4


# ── compact_messages ─────────────────────────────────────────────────────────


def test_compact_no_compaction_needed():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    result_msgs, compact_result = compact_messages(msgs, max_tokens=100_000)
    assert result_msgs == msgs
    assert compact_result is None


def test_compact_under_keep_recent():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "bye"},
    ]
    result_msgs, compact_result = compact_messages(msgs, max_tokens=1, keep_recent=4)
    assert result_msgs == msgs
    assert compact_result is None


def test_compact_compaction_triggered():
    # Create many messages that exceed token limit
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"Message number {i} with some extra text " * 50})
        msgs.append({"role": "assistant", "content": f"Response {i} " * 50})

    result_msgs, compact_result = compact_messages(msgs, max_tokens=1000, keep_recent=4)

    assert compact_result is not None
    assert isinstance(compact_result, CompactResult)
    assert compact_result.original_messages == 40
    assert compact_result.compacted_messages == 5  # 1 summary + 4 recent
    assert compact_result.estimated_tokens_saved > 0
    assert len(result_msgs) == 5
    assert result_msgs[0]["role"] == "system"
    assert "Previous conversation summary" in result_msgs[0]["content"]


def test_compact_keeps_recent_messages():
    msgs = [
        {"role": "user", "content": "old question " * 100},
        {"role": "assistant", "content": "old answer " * 100},
        {"role": "user", "content": "old question 2 " * 100},
        {"role": "assistant", "content": "old answer 2 " * 100},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    result_msgs, compact_result = compact_messages(msgs, max_tokens=100, keep_recent=2)

    assert compact_result is not None
    # Last 2 messages should be intact
    assert result_msgs[-1]["content"] == "recent answer"
    assert result_msgs[-2]["content"] == "recent question"


# ── chunk_file ───────────────────────────────────────────────────────────────


def test_chunk_file_small(tmp_path):
    f = tmp_path / "small.py"
    f.write_text("line1\nline2\nline3\n")

    chunks = chunk_file(f, chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert chunks[0].chunk_index == 0
    assert chunks[0].total_chunks == 1
    assert "line1" in chunks[0].content


def test_chunk_file_large(tmp_path):
    f = tmp_path / "large.py"
    lines = [f"line {i}\n" for i in range(100)]
    f.write_text("".join(lines))

    chunks = chunk_file(f, chunk_size=30, overlap=5)
    assert len(chunks) > 1

    # First chunk starts at line 1
    assert chunks[0].start_line == 1
    assert chunks[0].chunk_index == 0

    # All chunks know total
    for c in chunks:
        assert c.total_chunks == len(chunks)
        assert c.total_lines == 100


def test_chunk_file_nonexistent(tmp_path):
    f = tmp_path / "nope.py"
    chunks = chunk_file(f)
    assert chunks == []


def test_chunk_file_overlap(tmp_path):
    f = tmp_path / "overlap.py"
    lines = [f"line {i}\n" for i in range(50)]
    f.write_text("".join(lines))

    chunks = chunk_file(f, chunk_size=20, overlap=5)
    assert len(chunks) > 1

    # Verify overlap: chunk[1] starts at line 16 (20-5+1)
    assert chunks[1].start_line == 16


# ── select_relevant_context ──────────────────────────────────────────────────


def test_select_relevant_context_basic():
    files = {
        "main.py": "def main():\n    print('hello')\n",
        "utils.py": "def helper():\n    pass\n",
        "README.md": "# Project\n\nA simple project\n",
    }

    result = select_relevant_context("main function", files, max_tokens=50_000)
    assert len(result) > 0
    # main.py should score highest due to filename match
    paths = [r[0] for r in result]
    assert "main.py" in paths


def test_select_relevant_context_token_limit():
    files = {
        f"file_{i}.py": f"content {i}\n" * 200
        for i in range(10)
    }

    result = select_relevant_context("content", files, max_tokens=500)
    # Should not include all files due to token limit
    assert len(result) < 10


def test_select_relevant_context_no_keywords():
    files = {
        "a.py": "short\n",
        "b.py": "longer content here " * 100,
    }
    result = select_relevant_context("the and for", files, max_tokens=50_000)
    # With no meaningful keywords, should still return files (sorted by size)
    assert len(result) == 2


def test_select_relevant_context_empty():
    result = select_relevant_context("anything", {}, max_tokens=50_000)
    assert result == []


# ── FileChunk dataclass ──────────────────────────────────────────────────────


def test_file_chunk_fields():
    c = FileChunk(
        path="test.py",
        start_line=1,
        end_line=50,
        content="...",
        total_lines=100,
        chunk_index=0,
        total_chunks=2,
    )
    assert c.path == "test.py"
    assert c.start_line == 1
    assert c.total_chunks == 2

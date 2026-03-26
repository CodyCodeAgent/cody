"""Tests for context management module"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cody.core.config import CompactionConfig, Config
from cody.core.context import (
    CompactResult,
    FileChunk,
    PruneResult,
    _format_messages_for_summary,
    _resolve_compaction_model,
    _split_recent,
    chunk_file,
    compact_messages,
    compact_messages_llm,
    estimate_tokens,
    prune_tool_outputs,
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


# ── CompactResult.used_llm ──────────────────────────────────────────────────


def test_compact_result_used_llm_default():
    r = CompactResult(summary="s", original_messages=10, compacted_messages=5,
                      estimated_tokens_saved=100)
    assert r.used_llm is False


def test_compact_result_used_llm_explicit():
    r = CompactResult(summary="s", original_messages=10, compacted_messages=5,
                      estimated_tokens_saved=100, used_llm=True)
    assert r.used_llm is True


# ── CompactionConfig defaults ───────────────────────────────────────────────


def test_compaction_config_defaults():
    cc = CompactionConfig()
    assert cc.use_llm is False
    assert cc.model is None
    assert cc.model_base_url is None
    assert cc.model_api_key is None
    assert cc.max_tokens == 100_000
    assert cc.keep_recent == 4
    assert cc.max_summary_tokens == 500


def test_config_has_compaction():
    c = Config()
    assert isinstance(c.compaction, CompactionConfig)
    assert c.compaction.use_llm is False


# ── _format_messages_for_summary ────────────────────────────────────────────


def test_format_messages_for_summary():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    result = _format_messages_for_summary(msgs)
    assert "[user] hello" in result
    assert "[assistant] hi there" in result


def test_format_messages_truncates_long():
    msgs = [{"role": "user", "content": "x" * 5000}]
    result = _format_messages_for_summary(msgs)
    assert "... [truncated]" in result
    assert len(result) < 5000


# ── compact_messages_llm ────────────────────────────────────────────────────


def _make_config(use_llm: bool = True) -> Config:
    return Config(
        model="test-model",
        model_base_url="http://localhost:1234",
        model_api_key="test-key",
        compaction=CompactionConfig(use_llm=use_llm),
    )


@pytest.mark.asyncio
async def test_compact_llm_no_compaction_needed():
    """Under threshold — returns original messages, no LLM call."""
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    config = _make_config()
    result_msgs, result = await compact_messages_llm(
        msgs, config, max_tokens=100_000,
    )
    assert result_msgs == msgs
    assert result is None


@pytest.mark.asyncio
async def test_compact_llm_basic():
    """LLM compaction produces structured output with used_llm=True."""
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"Question {i} " * 50})
        msgs.append({"role": "assistant", "content": f"Answer {i} " * 50})

    config = _make_config()

    mock_result = MagicMock()
    mock_result.output = "- User asked 20 questions\n- Assistant answered all"

    with patch("pydantic_ai.Agent") as MockAgent:
        mock_agent_instance = AsyncMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent_instance

        result_msgs, compact_result = await compact_messages_llm(
            msgs, config, max_tokens=1000, keep_recent=4,
        )

    assert compact_result is not None
    assert compact_result.used_llm is True
    assert compact_result.compacted_messages == 5  # 1 summary + 4 recent
    assert compact_result.original_messages == 40
    assert compact_result.estimated_tokens_saved > 0
    assert len(result_msgs) == 5
    assert result_msgs[0]["role"] == "system"
    assert "Previous conversation summary" in result_msgs[0]["content"]
    assert "User asked 20 questions" in result_msgs[0]["content"]

    # Verify max_summary_tokens is passed through to model_settings
    mock_agent_instance.run.assert_called_once()
    call_kwargs = mock_agent_instance.run.call_args
    assert call_kwargs.kwargs.get("model_settings") == {"max_tokens": 500}


@pytest.mark.asyncio
async def test_compact_llm_custom_max_summary_tokens():
    """max_summary_tokens is forwarded as model_settings max_tokens."""
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"Q{i} " * 50})
        msgs.append({"role": "assistant", "content": f"A{i} " * 50})

    config = _make_config()

    mock_result = MagicMock()
    mock_result.output = "Summary"

    with patch("pydantic_ai.Agent") as MockAgent:
        mock_agent_instance = AsyncMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent_instance

        await compact_messages_llm(
            msgs, config, max_tokens=1000, keep_recent=4,
            max_summary_tokens=800,
        )

    call_kwargs = mock_agent_instance.run.call_args
    assert call_kwargs.kwargs["model_settings"] == {"max_tokens": 800}


@pytest.mark.asyncio
async def test_compact_llm_incremental():
    """Existing summary is passed to the LLM prompt for merging."""
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"Question {i} " * 50})
        msgs.append({"role": "assistant", "content": f"Answer {i} " * 50})

    config = _make_config()
    existing = "Previous conversation summary:\n- Old context about files"

    mock_result = MagicMock()
    mock_result.output = "- Merged summary"

    with patch("pydantic_ai.Agent") as MockAgent:
        mock_agent_instance = AsyncMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent_instance

        await compact_messages_llm(
            msgs, config, existing_summary=existing,
            max_tokens=1000, keep_recent=4,
        )

        # Verify existing summary was included in the prompt
        call_args = mock_agent_instance.run.call_args
        prompt_text = call_args[0][0]
        assert "Old context about files" in prompt_text


@pytest.mark.asyncio
async def test_compact_llm_skip_when_disabled():
    """use_llm=False in config means compact_messages_llm still works
    (it's the runner that decides which to call), but we verify the function
    itself does its job independently of the flag."""
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    config = _make_config(use_llm=False)
    result_msgs, result = await compact_messages_llm(
        msgs, config, max_tokens=100_000,
    )
    assert result is None  # no compaction needed


# ── _resolve_compaction_model ───────────────────────────────────────────────


def test_resolve_compaction_model_uses_compaction_settings():
    """Compaction-specific model settings take priority."""
    config = Config(
        model="main-model",
        model_base_url="http://main:1234",
        model_api_key="main-key",
        compaction=CompactionConfig(
            model="compact-model",
            model_base_url="http://compact:5678",
            model_api_key="compact-key",
        ),
    )
    with patch(
        "pydantic_ai.models.openai.OpenAIChatModel",
    ) as MockModel, patch(
        "pydantic_ai.providers.openai.OpenAIProvider",
    ) as MockProvider:
        _resolve_compaction_model(config)
        MockProvider.assert_called_once_with(
            base_url="http://compact:5678", api_key="compact-key",
        )
        MockModel.assert_called_once_with(
            "compact-model", provider=MockProvider.return_value,
        )


def test_resolve_compaction_model_falls_back_to_main():
    """When compaction model settings are None, use main config."""
    config = Config(
        model="main-model",
        model_base_url="http://main:1234",
        model_api_key="main-key",
    )
    with patch(
        "pydantic_ai.models.openai.OpenAIChatModel",
    ) as MockModel, patch(
        "pydantic_ai.providers.openai.OpenAIProvider",
    ) as MockProvider:
        _resolve_compaction_model(config)
        MockProvider.assert_called_once_with(
            base_url="http://main:1234", api_key="main-key",
        )
        MockModel.assert_called_once_with(
            "main-model", provider=MockProvider.return_value,
        )


def test_resolve_compaction_model_missing_base_url():
    """Raises ValueError when no base_url is available."""
    config = Config(model="test")
    with pytest.raises(ValueError, match="model_base_url is required"):
        _resolve_compaction_model(config)


# ── prune_tool_outputs ──────────────────────────────────────────────────────


def test_prune_no_pruning_under_threshold():
    """Under max_tokens — no pruning needed."""
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    result_msgs, prune_result = prune_tool_outputs(msgs, max_tokens=100_000)
    assert result_msgs == msgs
    assert prune_result is None


def test_prune_replaces_old_large_outputs():
    """Old large assistant outputs are replaced with markers."""
    msgs = [
        {"role": "user", "content": "read file"},
        {"role": "assistant", "content": "x" * 5000},  # large old output
        {"role": "user", "content": "another question"},
        {"role": "assistant", "content": "y" * 5000},  # large old output
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]
    result_msgs, prune_result = prune_tool_outputs(
        msgs,
        max_tokens=500,
        protect_recent_tokens=100,
        min_saving_tokens=500,
        min_content_tokens=100,
    )
    assert prune_result is not None
    assert prune_result.messages_pruned >= 1
    assert prune_result.estimated_tokens_saved > 0
    # Recent messages should be intact
    assert result_msgs[-1]["content"] == "recent answer"
    assert result_msgs[-2]["content"] == "recent question"
    # Old large outputs should be pruned
    assert "[output pruned at" in result_msgs[1]["content"]


def test_prune_preserves_user_messages():
    """User messages are never pruned (only tool/assistant roles)."""
    msgs = [
        {"role": "user", "content": "x" * 5000},  # large user message
        {"role": "assistant", "content": "y" * 5000},  # large assistant
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent"},
    ]
    result_msgs, prune_result = prune_tool_outputs(
        msgs,
        max_tokens=500,
        protect_recent_tokens=100,
        min_saving_tokens=500,
        min_content_tokens=100,
    )
    assert prune_result is not None
    # User message content should be preserved
    assert result_msgs[0]["content"] == "x" * 5000
    # Assistant message should be pruned
    assert "[output pruned at" in result_msgs[1]["content"]


def test_prune_protects_recent_messages():
    """Messages within protect_recent_tokens window are never pruned."""
    msgs = [
        {"role": "assistant", "content": "old " * 500},
        {"role": "assistant", "content": "recent " * 500},
    ]
    # Set protect_recent_tokens high enough to protect both messages
    result_msgs, prune_result = prune_tool_outputs(
        msgs,
        max_tokens=10,
        protect_recent_tokens=999_999,
        min_saving_tokens=100,
    )
    # Nothing prunable — all protected
    assert prune_result is None


def test_prune_skips_small_messages():
    """Messages under min_content_tokens are not pruned."""
    msgs = [
        {"role": "assistant", "content": "short"},  # too small
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent"},
    ]
    result_msgs, prune_result = prune_tool_outputs(
        msgs,
        max_tokens=1,
        protect_recent_tokens=50,
        min_saving_tokens=1,
        min_content_tokens=9999,  # very high threshold
    )
    assert prune_result is None


def test_prune_stops_when_under_threshold():
    """Pruning stops as soon as total tokens drop below max_tokens."""
    msgs = [
        {"role": "assistant", "content": "a" * 4000},  # ~1000 tokens
        {"role": "assistant", "content": "b" * 4000},  # ~1000 tokens
        {"role": "assistant", "content": "c" * 4000},  # ~1000 tokens
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent"},
    ]
    # Total ~3000+ tokens; max_tokens=2100 means we need to prune ~1000
    result_msgs, prune_result = prune_tool_outputs(
        msgs,
        max_tokens=2100,
        protect_recent_tokens=50,
        min_saving_tokens=100,
        min_content_tokens=50,
    )
    assert prune_result is not None
    # Should prune only as many as needed (oldest first)
    assert prune_result.messages_pruned >= 1


def test_prune_insufficient_savings():
    """No pruning when potential savings < min_saving_tokens."""
    msgs = [
        {"role": "assistant", "content": "x" * 1000},
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent"},
    ]
    result_msgs, prune_result = prune_tool_outputs(
        msgs,
        max_tokens=10,
        protect_recent_tokens=50,
        min_saving_tokens=999_999,  # impossibly high
        min_content_tokens=50,
    )
    assert prune_result is None


def test_prune_result_fields():
    """PruneResult dataclass fields."""
    r = PruneResult(messages_pruned=3, estimated_tokens_saved=1500)
    assert r.messages_pruned == 3
    assert r.estimated_tokens_saved == 1500


def test_prune_does_not_mutate_original():
    """Original messages list is not modified."""
    original_content = "x" * 5000
    msgs = [
        {"role": "assistant", "content": original_content},
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent"},
    ]
    original_msgs = [dict(m) for m in msgs]
    prune_tool_outputs(
        msgs,
        max_tokens=100,
        protect_recent_tokens=50,
        min_saving_tokens=100,
        min_content_tokens=50,
    )
    assert msgs == original_msgs


# ── CompactionConfig prune defaults ────────────────────────────────────────


def test_compaction_config_prune_defaults():
    cc = CompactionConfig()
    assert cc.enable_pruning is True
    assert cc.prune_protect_tokens == 40_000
    assert cc.prune_min_saving_tokens == 20_000
    assert cc.prune_min_content_tokens == 200


# ── Structured summarization prompt ────────────────────────────────────────


def test_summarization_prompt_has_structured_sections():
    """The LLM summarization prompt contains structured section tags."""
    from cody.core.context import _SUMMARIZATION_USER_PROMPT

    for section in ["[Goal]", "[Instructions]", "[Discoveries]",
                     "[Progress]", "[Files]", "[Decisions]"]:
        assert section in _SUMMARIZATION_USER_PROMPT, f"Missing section: {section}"


def test_summarization_user_prompt_plan_and_directory_guidance():
    """User prompt guides LLM to preserve plans/specs and support directories."""
    from cody.core.context import _SUMMARIZATION_USER_PROMPT

    assert "plan" in _SUMMARIZATION_USER_PROMPT.lower()
    assert "directory" in _SUMMARIZATION_USER_PROMPT.lower() or \
           "directories" in _SUMMARIZATION_USER_PROMPT.lower()


def test_summarization_system_prompt_exists():
    """A separate system prompt is defined for the summarizer agent."""
    from cody.core.context import _SUMMARIZATION_SYSTEM_PROMPT

    assert "summarizer" in _SUMMARIZATION_SYSTEM_PROMPT.lower()
    assert len(_SUMMARIZATION_SYSTEM_PROMPT) > 20


def test_summarization_system_prompt_safety_instruction():
    """System prompt prevents the summarizer from answering questions."""
    from cody.core.context import _SUMMARIZATION_SYSTEM_PROMPT

    assert "do not respond" in _SUMMARIZATION_SYSTEM_PROMPT.lower()


def test_summarization_system_prompt_handoff_framing():
    """System prompt frames the summary as a handoff to another agent."""
    from cody.core.context import _SUMMARIZATION_SYSTEM_PROMPT

    assert "another agent" in _SUMMARIZATION_SYSTEM_PROMPT.lower()


# ── _split_recent (token-based) ────────────────────────────────────────────


def test_split_recent_count_based():
    """Default count-based split: last N messages."""
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
    old, recent = _split_recent(msgs, keep_recent=3)
    assert len(recent) == 3
    assert len(old) == 7
    assert recent[-1]["content"] == "msg9"


def test_split_recent_token_based():
    """Token-based split: keep messages until token budget exhausted."""
    msgs = [
        {"role": "user", "content": "old " * 100},      # ~100 tokens
        {"role": "assistant", "content": "old " * 100},  # ~100 tokens
        {"role": "user", "content": "recent"},            # ~2 tokens
        {"role": "assistant", "content": "recent"},       # ~2 tokens
    ]
    old, recent = _split_recent(msgs, keep_recent=1, keep_recent_tokens=50)
    # Should keep the last 2 small messages (< 50 tokens together)
    assert len(recent) >= 2
    assert recent[-1]["content"] == "recent"


def test_split_recent_token_based_keeps_at_least_one():
    """Token-based split always keeps at least one message."""
    msgs = [
        {"role": "user", "content": "x" * 4000},  # ~1000 tokens
    ]
    old, recent = _split_recent(msgs, keep_recent=1, keep_recent_tokens=1)
    assert len(recent) >= 1


def test_split_recent_token_zero_falls_back_to_count():
    """keep_recent_tokens=0 uses count-based keep_recent."""
    msgs = [{"role": "user", "content": f"msg{i}"} for i in range(6)]
    old, recent = _split_recent(msgs, keep_recent=2, keep_recent_tokens=0)
    assert len(recent) == 2


# ── compact_messages with keep_recent_tokens ───────────────────────────────


def test_compact_messages_token_based_keep():
    """compact_messages respects keep_recent_tokens."""
    msgs = []
    for i in range(20):
        msgs.append({"role": "user", "content": f"Question {i} " * 50})
        msgs.append({"role": "assistant", "content": f"Answer {i} " * 50})

    # keep_recent_tokens=500 should keep several recent messages
    result_msgs, compact_result = compact_messages(
        msgs, max_tokens=1000, keep_recent_tokens=500,
    )
    assert compact_result is not None
    # The last message should be preserved
    assert result_msgs[-1]["content"] == msgs[-1]["content"]


# ── trigger_ratio / effective_max_tokens ───────────────────────────────────


def test_effective_max_tokens_default():
    """Without trigger_ratio, returns max_tokens."""
    cc = CompactionConfig(max_tokens=80_000)
    assert cc.effective_max_tokens() == 80_000


def test_effective_max_tokens_with_ratio():
    """With trigger_ratio and context_window_tokens, computes product."""
    cc = CompactionConfig(
        trigger_ratio=0.75,
        context_window_tokens=200_000,
    )
    assert cc.effective_max_tokens() == 150_000


def test_effective_max_tokens_ratio_no_window():
    """trigger_ratio without context_window_tokens falls back to max_tokens."""
    cc = CompactionConfig(
        trigger_ratio=0.75,
        context_window_tokens=0,
        max_tokens=100_000,
    )
    assert cc.effective_max_tokens() == 100_000


def test_compaction_config_new_defaults():
    """New config fields have correct defaults."""
    cc = CompactionConfig()
    assert cc.trigger_ratio == 0.0
    assert cc.context_window_tokens == 0
    assert cc.keep_recent_tokens == 0

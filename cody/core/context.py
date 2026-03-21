"""Context management for Cody agent.

Handles:
- Auto-compact: compress conversation history when approaching token limits
- Large file chunking: split large files for reading
- Smart context selection: only feed relevant code to the LLM
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


# ── Token estimation ─────────────────────────────────────────────────────────

# Rough estimate: ~4 chars per token for English, ~2 for CJK
_CHARS_PER_TOKEN = 4


def estimate_tokens(text) -> int:
    """Rough token count estimate. CJK characters count as ~1.5 tokens each."""
    if not isinstance(text, str):
        # Non-string content (e.g. ImageUrl, list of parts) — use a flat estimate
        return 100
    if not text:
        return 1
    # Count CJK characters (roughly Unicode CJK Unified Ideographs range)
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    non_cjk_len = len(text) - cjk_count
    return max(1, non_cjk_len // _CHARS_PER_TOKEN + int(cjk_count * 1.5))


# ── Selective pruning ────────────────────────────────────────────────────────
#
# Inspired by OpenCode's two-phase approach: before doing expensive full
# compaction (truncation or LLM summarization), first try *selectively pruning*
# old tool outputs.  Large tool results (file reads, grep output, etc.) from
# early in the conversation are replaced with lightweight "[pruned]" markers
# while keeping the conversation structure intact.  This often frees enough
# tokens to avoid a full compaction pass entirely.


_PRUNE_MARKER = "[output pruned at {ts}]"

# Tool-call outputs whose role matches these are candidates for pruning.
_PRUNABLE_ROLES = {"tool", "assistant"}


@dataclass
class PruneResult:
    """Result of selective output pruning."""
    messages_pruned: int
    estimated_tokens_saved: int


def prune_tool_outputs(
    messages: list[dict],
    *,
    max_tokens: int = 100_000,
    protect_recent_tokens: int = 40_000,
    min_saving_tokens: int = 20_000,
    min_content_tokens: int = 200,
) -> tuple[list[dict], PruneResult | None]:
    """Selectively prune old tool outputs to reduce context size.

    Scans backward through *messages*, identifies large tool/assistant outputs
    outside the protected-recent window, and replaces their content with a
    short marker.  The conversation structure (roles, ordering) is preserved.

    Args:
        messages: Conversation messages as dicts with ``role`` and ``content``.
        max_tokens: Token threshold — pruning only runs when total exceeds this.
        protect_recent_tokens: Token budget for the most recent messages that
            are **never** pruned (similar to OpenCode's PRUNE_PROTECT = 40 000).
        min_saving_tokens: Minimum tokens that *can* be freed before pruning
            is attempted (similar to OpenCode's PRUNE_MINIMUM = 20 000).
        min_content_tokens: Only prune individual messages whose content
            exceeds this many tokens (avoids pruning tiny outputs).

    Returns:
        ``(messages, PruneResult | None)`` — *messages* is a **new** list with
        pruned entries replaced.  Returns ``None`` result when no pruning was
        performed.
    """
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

    if total_tokens <= max_tokens:
        return messages, None

    # ── Identify the protected tail ──────────────────────────────────────
    # Walk backward to find where the protected window starts.
    protected_start = len(messages)  # index: messages[protected_start:] are safe
    tail_tokens = 0
    for idx in range(len(messages) - 1, -1, -1):
        tail_tokens += estimate_tokens(messages[idx].get("content", ""))
        if tail_tokens >= protect_recent_tokens:
            protected_start = idx + 1
            break
    else:
        # All messages fit inside the protected window — nothing to prune
        protected_start = 0

    if protected_start == 0:
        return messages, None

    # ── Collect pruning candidates (old, large outputs) ──────────────────
    # Candidates are (index, token_count) tuples, scanned backward so we
    # prune the *oldest* large outputs first.
    candidates: list[tuple[int, int]] = []
    potential_savings = 0
    for idx in range(protected_start):
        msg = messages[idx]
        if msg.get("role") not in _PRUNABLE_ROLES:
            continue
        content = msg.get("content", "")
        tok = estimate_tokens(content)
        if tok >= min_content_tokens:
            marker_tokens = estimate_tokens(_PRUNE_MARKER.format(ts="x" * 19))
            saving = tok - marker_tokens
            if saving > 0:
                candidates.append((idx, saving))
                potential_savings += saving

    if potential_savings < min_saving_tokens:
        return messages, None

    # ── Apply pruning ────────────────────────────────────────────────────
    from datetime import datetime, timezone

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    marker = _PRUNE_MARKER.format(ts=now_str)

    pruned = list(messages)  # shallow copy
    tokens_saved = 0
    messages_pruned = 0

    for idx, saving in candidates:
        pruned[idx] = {**pruned[idx], "content": marker}
        tokens_saved += saving
        messages_pruned += 1

        # Stop once we're back under threshold
        if total_tokens - tokens_saved <= max_tokens:
            break

    if messages_pruned == 0:
        return messages, None

    return pruned, PruneResult(
        messages_pruned=messages_pruned,
        estimated_tokens_saved=tokens_saved,
    )


# ── Auto-compact ─────────────────────────────────────────────────────────────


@dataclass
class CompactResult:
    """Result of context compaction."""
    summary: str
    original_messages: int
    compacted_messages: int
    estimated_tokens_saved: int
    used_llm: bool = False


def _split_recent(
    messages: list[dict],
    keep_recent: int = 4,
    keep_recent_tokens: int = 0,
) -> tuple[list[dict], list[dict]]:
    """Split messages into (old, recent) based on count or token budget.

    When *keep_recent_tokens* > 0, the split is **token-based**: walk backward
    and keep messages until the cumulative token count exceeds the budget.
    Otherwise, fall back to the classic ``messages[-keep_recent:]`` split.
    """
    if keep_recent_tokens > 0:
        budget = keep_recent_tokens
        split_idx = len(messages)
        for idx in range(len(messages) - 1, -1, -1):
            tok = estimate_tokens(messages[idx].get("content", ""))
            if budget - tok < 0 and split_idx < len(messages):
                break
            budget -= tok
            split_idx = idx
        # Always keep at least one recent message
        split_idx = min(split_idx, len(messages) - 1)
        return messages[:split_idx], messages[split_idx:]

    if keep_recent >= len(messages):
        return [], messages
    return messages[:-keep_recent], messages[-keep_recent:]


def compact_messages(
    messages: list[dict],
    max_tokens: int = 100_000,
    keep_recent: int = 4,
    keep_recent_tokens: int = 0,
) -> tuple[list[dict], Optional[CompactResult]]:
    """Compact older messages into a summary when context grows too large.

    When *keep_recent_tokens* > 0, uses a **token budget** to decide how many
    recent messages to preserve (instead of fixed *keep_recent* count).

    Returns (new_messages, compact_result_or_none).
    """
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

    if total_tokens <= max_tokens:
        return messages, None

    old_messages, recent_messages = _split_recent(
        messages, keep_recent, keep_recent_tokens,
    )

    if not old_messages:
        return messages, None

    # Build summary from old messages
    summary_parts: list[str] = []
    for msg in old_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        # Truncate each message to a brief summary
        brief = _summarize_message(content)
        if brief:
            summary_parts.append(f"[{role}] {brief}")

    summary_text = "Previous conversation summary:\n" + "\n".join(summary_parts)

    old_tokens = sum(estimate_tokens(m.get("content", "")) for m in old_messages)
    summary_tokens = estimate_tokens(summary_text)

    compacted = [{"role": "system", "content": summary_text}] + recent_messages

    result = CompactResult(
        summary=summary_text,
        original_messages=len(messages),
        compacted_messages=len(compacted),
        estimated_tokens_saved=old_tokens - summary_tokens,
    )

    return compacted, result


def _summarize_message(content: str, max_len: int = 200) -> str:
    """Create a brief summary of a message."""
    if not content:
        return ""
    # Remove code blocks
    content = re.sub(r"```[\s\S]*?```", "[code block]", content)
    # Remove excessive whitespace
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) <= max_len:
        return content
    return content[:max_len] + "..."


# ── LLM-based compaction ────────────────────────────────────────────────────

_SUMMARIZATION_SYSTEM_PROMPT = """\
You are a conversation summarizer for an AI coding assistant.
Your summaries are injected as context for continuing the conversation, \
so focus on actionable information the assistant needs going forward."""

_SUMMARIZATION_USER_PROMPT = """\
Summarize the conversation into these sections. \
Omit any section that has no relevant content.

[Goal] What the user is trying to accomplish.
[Instructions] User-stated constraints, specs, or requirements.
[Discoveries] Technical findings: errors, warnings, library versions, edge cases.
[Progress] What is done, what is in progress, what remains.
[Files] Files read/edited/created — one per line: `path — note`.
[Decisions] Design or implementation decisions and their rationale.

Rules:
- Preserve exact names, paths, values, error messages, and version numbers verbatim.
- No code blocks unless they contain critical one-liners.
- Be concise — the shorter the better, as long as nothing important is lost."""


def _resolve_compaction_model(config: "Config"):
    """Build a pydantic-ai model instance for compaction summarization."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    cc = config.compaction
    model_name = cc.model or config.model
    base_url = cc.model_base_url or config.model_base_url
    api_key = cc.model_api_key or config.model_api_key

    if not base_url:
        raise ValueError(
            "model_base_url is required for LLM compaction. "
            "Set it in compaction config or main config."
        )

    provider = OpenAIProvider(base_url=base_url, api_key=api_key or "")
    return OpenAIChatModel(model_name, provider=provider)


def _format_messages_for_summary(messages: list[dict]) -> str:
    """Format message dicts into a readable transcript for the summarizer."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        # Truncate very long individual messages to avoid blowing up the prompt
        if len(content) > 2000:
            content = content[:2000] + "... [truncated]"
        parts.append(f"[{role}] {content}")
    return "\n\n".join(parts)


async def compact_messages_llm(
    messages: list[dict],
    config: "Config",
    existing_summary: str = "",
    max_tokens: int = 100_000,
    keep_recent: int = 4,
    keep_recent_tokens: int = 0,
    max_summary_tokens: int = 500,
) -> tuple[list[dict], CompactResult | None]:
    """Compact messages using an LLM agent to generate a semantic summary.

    Falls back to truncation-based ``compact_messages`` on any error.

    Args:
        messages: Conversation messages as dicts with ``role`` and ``content``.
        config: Cody Config (used to resolve the summarization model).
        existing_summary: Previous compaction summary for incremental merging.
        max_tokens: Token threshold that triggers compaction.
        keep_recent: Number of recent messages to keep intact (count-based).
        keep_recent_tokens: Token budget for recent messages (0 = use count).
        max_summary_tokens: Maximum tokens for the generated summary.

    Returns:
        ``(compacted_messages, CompactResult | None)``
    """
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

    if total_tokens <= max_tokens:
        return messages, None

    old_messages, recent_messages = _split_recent(
        messages, keep_recent, keep_recent_tokens,
    )

    if not old_messages:
        return messages, None

    # Build the user prompt with transcript and optional prior summary
    user_parts: list[str] = [_SUMMARIZATION_USER_PROMPT]
    if existing_summary:
        user_parts.append(
            "Previous summary (merge into your output, "
            "update outdated info, deduplicate):\n" + existing_summary
        )
    user_parts.append(
        "Conversation to summarize:\n"
        + _format_messages_for_summary(old_messages)
    )
    user_text = "\n\n".join(user_parts)

    # Spawn a lightweight pydantic-ai Agent (no tools, no deps)
    from pydantic_ai import Agent

    model = _resolve_compaction_model(config)
    agent = Agent(model, system_prompt=_SUMMARIZATION_SYSTEM_PROMPT)

    result = await agent.run(user_text)
    summary_text = "Previous conversation summary:\n" + result.output

    old_tokens = sum(
        estimate_tokens(m.get("content", "")) for m in old_messages
    )
    summary_tokens = estimate_tokens(summary_text)

    compacted = [{"role": "system", "content": summary_text}] + recent_messages

    compact_result = CompactResult(
        summary=summary_text,
        original_messages=len(messages),
        compacted_messages=len(compacted),
        estimated_tokens_saved=old_tokens - summary_tokens,
        used_llm=True,
    )
    return compacted, compact_result


# ── Large file chunking ─────────────────────────────────────────────────────


@dataclass
class FileChunk:
    """A chunk of a large file."""
    path: str
    start_line: int
    end_line: int
    content: str
    total_lines: int
    chunk_index: int
    total_chunks: int


def chunk_file(
    file_path: Path,
    chunk_size: int = 500,
    overlap: int = 20,
) -> list[FileChunk]:
    """Split a large file into overlapping chunks.

    Args:
        file_path: Path to the file.
        chunk_size: Lines per chunk.
        overlap: Overlapping lines between chunks for context continuity.

    Returns:
        List of FileChunk objects.
    """
    try:
        content = file_path.read_text(errors="ignore")
    except (OSError, PermissionError):
        return []

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    if total_lines <= chunk_size:
        return [FileChunk(
            path=str(file_path),
            start_line=1,
            end_line=total_lines,
            content=content,
            total_lines=total_lines,
            chunk_index=0,
            total_chunks=1,
        )]

    chunks: list[FileChunk] = []
    step = chunk_size - overlap
    starts = list(range(0, total_lines, step))
    total_chunks = len(starts)

    for idx, start in enumerate(starts):
        end = min(start + chunk_size, total_lines)
        chunk_lines = lines[start:end]
        chunks.append(FileChunk(
            path=str(file_path),
            start_line=start + 1,
            end_line=end,
            content="".join(chunk_lines),
            total_lines=total_lines,
            chunk_index=idx,
            total_chunks=total_chunks,
        ))

    return chunks


# ── Smart context selection ──────────────────────────────────────────────────


def select_relevant_context(
    query: str,
    files: dict[str, str],
    max_tokens: int = 30_000,
) -> list[tuple[str, str]]:
    """Select the most relevant files/sections for a given query.

    Scores files by keyword overlap with the query and returns
    the highest-scoring files that fit within the token budget.

    Args:
        query: The user's question or task description.
        files: Dict of {file_path: content}.
        max_tokens: Maximum total tokens to include.

    Returns:
        List of (file_path, content) sorted by relevance.
    """
    query_words = set(_extract_keywords(query))

    if not query_words:
        # No meaningful keywords — return files by size (smallest first)
        scored: list[tuple[float, str, str]] = [
            (float(len(content)), path, content)
            for path, content in files.items()
        ]
        scored.sort()
    else:
        scored = []
        for path, content in files.items():
            score = _relevance_score(query_words, path, content)
            scored.append((-score, path, content))  # negative for descending sort
        scored.sort()

    result: list[tuple[str, str]] = []
    tokens_used = 0

    for _, path, content in scored:
        content_tokens = estimate_tokens(content)
        if tokens_used + content_tokens > max_tokens:
            # Try to include a truncated version
            remaining_tokens = max_tokens - tokens_used
            if remaining_tokens > 200:
                truncated = content[: remaining_tokens * _CHARS_PER_TOKEN]
                result.append((path, truncated + "\n... [truncated]"))
            break
        result.append((path, content))
        tokens_used += content_tokens

    return result


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text."""
    # Split on non-alphanumeric, filter short words and common ones
    words = re.findall(r"[a-zA-Z_]\w{2,}", text.lower())
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was",
        "has", "have", "not", "but", "can", "all", "any", "use", "how",
        "what", "when", "where", "which", "will", "would", "should", "could",
        "into", "than", "then", "them", "they", "been", "being", "each",
        "make", "like", "just", "over", "such", "take", "more", "some",
    }
    return [w for w in words if w not in stopwords]


def _relevance_score(query_words: set, file_path: str, content: str) -> float:
    """Score a file's relevance to a query."""
    score = 0.0

    # Check filename match
    path_lower = file_path.lower()
    for word in query_words:
        if word in path_lower:
            score += 5.0

    # Check content match
    content_lower = content.lower()
    for word in query_words:
        count = content_lower.count(word)
        if count > 0:
            score += min(count, 10) * 0.5  # cap per-word contribution

    # Bonus for common important files
    basename = Path(file_path).name.lower()
    if basename in ("main.py", "app.py", "index.ts", "index.js", "main.go"):
        score += 2.0
    if basename in ("readme.md", "package.json", "pyproject.toml", "go.mod"):
        score += 1.0

    return score

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


# ── Auto-compact ─────────────────────────────────────────────────────────────


@dataclass
class CompactResult:
    """Result of context compaction."""
    summary: str
    original_messages: int
    compacted_messages: int
    estimated_tokens_saved: int
    used_llm: bool = False


def compact_messages(
    messages: list[dict],
    max_tokens: int = 100_000,
    keep_recent: int = 4,
) -> tuple[list[dict], Optional[CompactResult]]:
    """Compact older messages into a summary when context grows too large.

    Keeps the most recent `keep_recent` messages intact and summarizes the rest.
    Returns (new_messages, compact_result_or_none).
    """
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

    if total_tokens <= max_tokens or len(messages) <= keep_recent:
        return messages, None

    # Split into old (to compact) and recent (to keep)
    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

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

_SUMMARIZATION_PROMPT = """\
You are a conversation summarizer for an AI coding assistant.

Summarize the conversation below. Preserve:
- User goals and intent
- Key decisions made
- File paths and code locations mentioned
- Tool results (especially errors and warnings)
- Constraints or requirements stated

Format: bullet points, 300 words or fewer. Do NOT include code blocks \
unless they contain critical one-liners.
"""


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
    max_summary_tokens: int = 500,
) -> tuple[list[dict], CompactResult | None]:
    """Compact messages using an LLM agent to generate a semantic summary.

    Falls back to truncation-based ``compact_messages`` on any error.

    Args:
        messages: Conversation messages as dicts with ``role`` and ``content``.
        config: Cody Config (used to resolve the summarization model).
        existing_summary: Previous compaction summary for incremental merging.
        max_tokens: Token threshold that triggers compaction.
        keep_recent: Number of recent messages to keep intact.
        max_summary_tokens: Maximum tokens for the generated summary.

    Returns:
        ``(compacted_messages, CompactResult | None)``
    """
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

    if total_tokens <= max_tokens or len(messages) <= keep_recent:
        return messages, None

    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Build the summarization prompt
    prompt_parts: list[str] = [_SUMMARIZATION_PROMPT]
    if existing_summary:
        prompt_parts.append(
            f"Previous summary to incorporate:\n{existing_summary}\n"
        )
    prompt_parts.append(
        "Conversation to summarize:\n"
        + _format_messages_for_summary(old_messages)
    )
    prompt_text = "\n\n".join(prompt_parts)

    # Spawn a lightweight pydantic-ai Agent (no tools, no deps)
    from pydantic_ai import Agent

    model = _resolve_compaction_model(config)
    agent = Agent(model)

    result = await agent.run(prompt_text)
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

"""Project memory — cross-session knowledge store.

Stores learnings per project (identified by workdir hash) so that
the AI can accumulate experience across tasks.  Each project gets
its own directory under ``~/.cody/memory/<project_id>/`` with one
JSON file per category.

Categories:
  - conventions: code style, naming, tooling preferences
  - patterns: design patterns, common utilities, project idioms
  - issues: known bugs, edge cases, pitfalls
  - decisions: architecture choices, tech selections, rationale
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CATEGORIES = ("conventions", "patterns", "issues", "decisions")
MAX_ENTRIES_PER_CATEGORY = 50
MIN_CONFIDENCE = 0.3


@dataclass
class MemoryEntry:
    """A single memory item."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: str = ""
    source_task_id: str = ""
    source_task_title: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)


def _project_id(workdir: Path) -> str:
    """Compute a stable project identifier from the workdir path."""
    return hashlib.md5(str(workdir.resolve()).encode()).hexdigest()[:12]


class ProjectMemoryStore:
    """File-backed memory store scoped to a single project."""

    def __init__(self, project_id: str, base_dir: Optional[Path] = None):
        self.project_id = project_id
        if base_dir is None:
            base_dir = Path.home() / ".cody" / "memory"
        self.store_dir = base_dir / project_id
        self.store_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_workdir(cls, workdir: Path, base_dir: Optional[Path] = None) -> "ProjectMemoryStore":
        """Create a store for the given working directory."""
        return cls(_project_id(workdir), base_dir=base_dir)

    # ── Read / Write ─────────────────────────────────────────────────────

    def _category_path(self, category: str) -> Path:
        return self.store_dir / f"{category}.json"

    def _load_category(self, category: str) -> list[MemoryEntry]:
        path = self._category_path(category)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [MemoryEntry(**item) for item in data]
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Failed to load memory category %s, resetting", category)
            return []

    def _save_category(self, category: str, entries: list[MemoryEntry]) -> None:
        path = self._category_path(category)
        data = [
            {
                "id": e.id,
                "content": e.content,
                "source_task_id": e.source_task_id,
                "source_task_title": e.source_task_title,
                "created_at": e.created_at,
                "confidence": e.confidence,
                "tags": e.tags,
            }
            for e in entries
        ]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    async def add_entries(self, category: str, entries: list[MemoryEntry]) -> None:
        """Add entries to a category, enforcing limits."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown memory category: {category}")
        existing = self._load_category(category)
        existing.extend(entries)
        # Enforce max entries — drop oldest
        if len(existing) > MAX_ENTRIES_PER_CATEGORY:
            existing = existing[-MAX_ENTRIES_PER_CATEGORY:]
        self._save_category(category, existing)

    def get_all_entries(self) -> dict[str, list[MemoryEntry]]:
        """Load all categories."""
        result: dict[str, list[MemoryEntry]] = {}
        for cat in CATEGORIES:
            entries = self._load_category(cat)
            if entries:
                result[cat] = entries
        return result

    def get_memory_for_prompt(self, max_tokens: int = 2000) -> str:
        """Format stored memories for system prompt injection.

        Returns empty string if no memories exist.
        """
        all_entries = self.get_all_entries()
        if not all_entries:
            return ""

        parts = ["## Project Memory (auto-accumulated from previous tasks)\n"]
        # Rough token budget: ~4 chars per token
        budget = max_tokens * 4
        used = len(parts[0])

        for category, entries in all_entries.items():
            header = f"\n### {category.title()}\n"
            if used + len(header) > budget:
                break
            parts.append(header)
            used += len(header)

            for entry in entries:
                if entry.confidence < MIN_CONFIDENCE:
                    continue
                line = f"- {entry.content}\n"
                if used + len(line) > budget:
                    break
                parts.append(line)
                used += len(line)

        return "".join(parts)

    async def cleanup(self) -> None:
        """Remove low-confidence and over-limit entries."""
        for cat in CATEGORIES:
            entries = self._load_category(cat)
            if not entries:
                continue
            # Filter low confidence
            entries = [e for e in entries if e.confidence >= MIN_CONFIDENCE]
            # Enforce max
            if len(entries) > MAX_ENTRIES_PER_CATEGORY:
                entries = entries[-MAX_ENTRIES_PER_CATEGORY:]
            self._save_category(cat, entries)

    def count(self) -> dict[str, int]:
        """Return entry counts per category."""
        return {cat: len(self._load_category(cat)) for cat in CATEGORIES}

    def clear(self) -> None:
        """Remove all memory for this project."""
        for cat in CATEGORIES:
            path = self._category_path(cat)
            if path.exists():
                path.unlink()

"""Multimodal prompt types for the Cody engine.

Defines well-typed prompt representations that support both plain text
and multimodal content (text + images). CLI/TUI use plain str prompts;
the Web layer constructs MultimodalPrompt when images are attached.
"""

import base64
from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class ImageData:
    """A single image attachment in a user prompt.

    Images arrive as base64 from the web frontend (pasted screenshots
    or file uploads). Stored as base64 in SQLite.
    """
    data: str  # base64-encoded image bytes
    media_type: str  # e.g. "image/png", "image/jpeg", "image/webp", "image/gif"
    filename: Optional[str] = None  # optional original filename

    @property
    def data_bytes(self) -> bytes:
        """Decode base64 string to raw bytes."""
        return base64.b64decode(self.data)

    def to_dict(self) -> dict:
        """Serialize for JSON storage in SQLite."""
        d: dict = {"data": self.data, "media_type": self.media_type}
        if self.filename:
            d["filename"] = self.filename
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ImageData":
        """Deserialize from JSON storage."""
        return cls(
            data=d["data"],
            media_type=d["media_type"],
            filename=d.get("filename"),
        )


@dataclass
class MultimodalPrompt:
    """A prompt containing text and one or more images.

    This is the structured alternative to a plain ``str`` prompt.
    The runner converts this to pydantic-ai's expected format
    (a list with str + BinaryContent items).
    """
    text: str
    images: List[ImageData] = field(default_factory=list)


# The union type used throughout the core API.
# Plain str for text-only prompts (CLI, TUI, SDK).
# MultimodalPrompt for text + images (Web).
Prompt = Union[str, MultimodalPrompt]


def prompt_text(prompt: Prompt) -> str:
    """Extract the text portion from any Prompt, for session storage."""
    if isinstance(prompt, str):
        return prompt
    return prompt.text


def prompt_images(prompt: Prompt) -> List[ImageData]:
    """Extract images from a Prompt. Returns empty list for str prompts."""
    if isinstance(prompt, str):
        return []
    return prompt.images

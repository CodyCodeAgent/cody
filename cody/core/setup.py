"""Interactive setup helpers — data layer for configuration wizard.

Used by CLI and TUI to guide users through first-time setup.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SetupAnswers:
    """Collected answers from the interactive setup wizard."""
    model: str
    model_api_key: str
    model_base_url: Optional[str] = None
    enable_thinking: bool = False
    thinking_budget: Optional[int] = None


def build_config_from_answers(answers: SetupAnswers) -> dict:
    """Convert SetupAnswers to a dict suitable for Config(**d) or JSON save."""
    data: dict = {
        "model": answers.model,
        "model_api_key": answers.model_api_key,
    }
    if answers.model_base_url:
        data["model_base_url"] = answers.model_base_url
    if answers.enable_thinking:
        data["enable_thinking"] = True
        if answers.thinking_budget:
            data["thinking_budget"] = answers.thinking_budget
    return data

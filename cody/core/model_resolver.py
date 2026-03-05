"""Model resolution logic — shared between AgentRunner and SubAgentManager.

Resolves a Config to a Pydantic AI model instance.

Priority:
  1. model_base_url  → OpenAI-compatible provider (covers Qwen, DeepSeek, etc.)
  2. model_api_key (no base_url) → Anthropic provider with explicit API key
"""

from .config import Config


def resolve_model(config: Config):
    """Return a Pydantic AI model instance for *config*.

    Requires ``model_api_key`` to be set.  Use ``Config.is_ready()`` before
    calling this to ensure the config is complete.
    """

    if config.model_base_url:
        from pydantic_ai.models.openai import OpenAIChatModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.openai import OpenAIProvider  # pylint: disable=import-outside-toplevel

        provider = OpenAIProvider(
            base_url=config.model_base_url,
            api_key=config.model_api_key or "",  # some providers don't require an API key
        )
        return OpenAIChatModel(config.model, provider=provider)

    if config.model_api_key:
        from anthropic import AsyncAnthropic  # pylint: disable=import-outside-toplevel
        from pydantic_ai.models.anthropic import AnthropicModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.anthropic import AnthropicProvider  # pylint: disable=import-outside-toplevel

        client = AsyncAnthropic(api_key=config.model_api_key)
        provider = AnthropicProvider(anthropic_client=client)
        model_name = config.model.removeprefix("anthropic:")
        return AnthropicModel(model_name, provider=provider)

    raise ValueError(
        "model_api_key is required. Run 'cody config setup' to configure."
    )

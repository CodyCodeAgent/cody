"""Model resolution logic — shared between AgentRunner and SubAgentManager.

Resolves a Config to a Pydantic AI model instance (or a bare model-string
for Pydantic AI's built-in routing).

Priority:
  1. model_base_url  → OpenAI-compatible provider (covers Qwen, DeepSeek, etc.)
  2. model_api_key (no base_url) → Anthropic provider with explicit API key
  3. default → model string (Pydantic AI built-in routing, uses ANTHROPIC_API_KEY)
"""

from .config import Config


def resolve_model(config: Config):
    """Return a Pydantic AI model instance (or model-name string) for *config*."""

    if config.model_base_url:
        from pydantic_ai.models.openai import OpenAIChatModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.openai import OpenAIProvider  # pylint: disable=import-outside-toplevel

        provider = OpenAIProvider(
            base_url=config.model_base_url,
            api_key=config.model_api_key or "not-set",
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

    return config.model

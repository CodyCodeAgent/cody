"""Model resolution logic — shared between AgentRunner and SubAgentManager.

Resolves a Config to a Pydantic AI model instance (or a bare model-string
for Pydantic AI's built-in routing).

Priority:
  1. coding_plan_key → Aliyun Bailian Coding Plan (OpenAI or Anthropic protocol)
  2. model_base_url  → OpenAI-compatible provider
  3. claude_oauth_token → Anthropic provider with OAuth auth_token
  4. default → model string (Pydantic AI built-in routing, uses ANTHROPIC_API_KEY)
"""

from .config import Config

_CODING_PLAN_OPENAI_URL = "https://coding.dashscope.aliyuncs.com/v1"
_CODING_PLAN_ANTHROPIC_URL = "https://coding.dashscope.aliyuncs.com/apps/anthropic"


def resolve_model(config: Config):
    """Return a Pydantic AI model instance (or model-name string) for *config*."""

    if config.coding_plan_key:
        if config.coding_plan_protocol == "anthropic":
            from anthropic import AsyncAnthropic  # pylint: disable=import-outside-toplevel
            from pydantic_ai.models.anthropic import AnthropicModel  # pylint: disable=import-outside-toplevel
            from pydantic_ai.providers.anthropic import AnthropicProvider  # pylint: disable=import-outside-toplevel

            client = AsyncAnthropic(
                api_key=config.coding_plan_key,
                base_url=_CODING_PLAN_ANTHROPIC_URL,
            )
            provider = AnthropicProvider(anthropic_client=client)
            model_name = config.model.removeprefix("anthropic:")
            return AnthropicModel(model_name, provider=provider)

        from pydantic_ai.models.openai import OpenAIChatModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.openai import OpenAIProvider  # pylint: disable=import-outside-toplevel

        provider = OpenAIProvider(
            base_url=_CODING_PLAN_OPENAI_URL,
            api_key=config.coding_plan_key,
        )
        return OpenAIChatModel(config.model, provider=provider)

    if config.model_base_url:
        from pydantic_ai.models.openai import OpenAIChatModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.openai import OpenAIProvider  # pylint: disable=import-outside-toplevel

        provider = OpenAIProvider(
            base_url=config.model_base_url,
            api_key=config.model_api_key or "not-set",
        )
        return OpenAIChatModel(config.model, provider=provider)

    if config.claude_oauth_token:
        from anthropic import AsyncAnthropic  # pylint: disable=import-outside-toplevel
        from pydantic_ai.models.anthropic import AnthropicModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.anthropic import AnthropicProvider  # pylint: disable=import-outside-toplevel

        client = AsyncAnthropic(auth_token=config.claude_oauth_token)
        provider = AnthropicProvider(anthropic_client=client)
        model_name = config.model.removeprefix("anthropic:")
        return AnthropicModel(model_name, provider=provider)

    return config.model

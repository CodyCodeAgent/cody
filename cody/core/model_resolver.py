"""Model resolution — resolves Config to a Pydantic AI model instance.

Uses OpenAI-compatible provider via model_base_url.
"""

from .config import Config


def resolve_model(config: Config):
    """Return a Pydantic AI model instance for *config*.

    Requires ``model_base_url`` to be set.  Use ``Config.is_ready()`` before
    calling this to ensure the config is complete.
    """

    if not config.model_base_url:
        raise ValueError(
            "model_base_url is required. Run 'cody config setup' to configure."
        )

    from pydantic_ai.models.openai import OpenAIChatModel  # pylint: disable=import-outside-toplevel
    from pydantic_ai.providers.openai import OpenAIProvider  # pylint: disable=import-outside-toplevel

    provider = OpenAIProvider(
        base_url=config.model_base_url,
        api_key=config.model_api_key or "",  # some providers don't require an API key
    )
    return OpenAIChatModel(config.model, provider=provider)


def resolve_small_model(config: Config):
    """Return a Pydantic AI model instance for low-cost operations.

    Uses ``small_model*`` fields if configured, otherwise falls back to the
    main model.  Useful for compaction, summarization, title generation, etc.
    """
    from pydantic_ai.models.openai import OpenAIChatModel  # pylint: disable=import-outside-toplevel
    from pydantic_ai.providers.openai import OpenAIProvider  # pylint: disable=import-outside-toplevel

    model_name = config.small_model or config.model
    base_url = config.small_model_base_url or config.model_base_url
    api_key = config.small_model_api_key or config.model_api_key

    if not base_url:
        raise ValueError(
            "model_base_url is required. Run 'cody config setup' to configure."
        )

    provider = OpenAIProvider(base_url=base_url, api_key=api_key or "")
    return OpenAIChatModel(model_name, provider=provider)

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

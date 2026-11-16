"""Connections with language models.

Each provider needs its extra: ``llm`` (Anthropic), ``google`` (Gemini and Gemma) or
``openrouter`` (hundreds of open and closed models). For another provider, a class with a
``name`` attribute and the ``respond_json`` method is enough (see ``base.Provider``).
"""

from centinela.providers.base import ModelResponse, Provider, ProviderError

PROVIDERS = ("anthropic", "google", "openrouter")


def create_provider(name: str = "anthropic", model: str | None = None) -> Provider:
    """The provider ``name``, with ``model`` or with its default model (a cheap one)."""
    if name == "anthropic":
        from centinela.providers import anthropic as module

        return module.AnthropicProvider(model or module.DEFAULT_MODEL)
    if name == "google":
        from centinela.providers import google as module

        return module.GoogleProvider(model or module.DEFAULT_MODEL)
    if name == "openrouter":
        from centinela.providers import openrouter as module

        return module.OpenRouterProvider(model or module.DEFAULT_MODEL)
    raise ValueError(f"unknown provider: {name}; use one of {', '.join(PROVIDERS)}")


__all__ = ["PROVIDERS", "ModelResponse", "Provider", "ProviderError", "create_provider"]

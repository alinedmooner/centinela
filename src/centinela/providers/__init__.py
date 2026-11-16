"""Conexiones con modelos de lenguaje.

Cada proveedor necesita su extra: ``llm`` (Anthropic), ``google`` (Gemini y Gemma) u
``openrouter`` (cientos de modelos abiertos y cerrados). Para otro proveedor basta una
clase con un atributo ``nombre`` y el método ``responder_json`` (ver ``base.Proveedor``).
"""

from centinela.providers.base import ModelResponse, Provider, ProviderError

PROVIDERS = ("anthropic", "google", "openrouter")


def create_provider(name: str = "anthropic", model: str | None = None) -> Provider:
    """El proveedor ``nombre``, con ``modelo`` o con su modelo por defecto (uno barato)."""
    if name == "anthropic":
        from centinela.providers import anthropic as modulo

        return modulo.AnthropicProvider(model or modulo.DEFAULT_MODEL)
    if name == "google":
        from centinela.providers import google as modulo

        return modulo.GoogleProvider(model or modulo.DEFAULT_MODEL)
    if name == "openrouter":
        from centinela.providers import openrouter as modulo

        return modulo.OpenRouterProvider(model or modulo.DEFAULT_MODEL)
    raise ValueError(f"proveedor desconocido: {name}; usa uno de {', '.join(PROVIDERS)}")


__all__ = ["PROVIDERS", "ModelResponse", "Provider", "ProviderError", "create_provider"]

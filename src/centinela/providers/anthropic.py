"""Proveedor para los modelos Claude, con el SDK oficial de Anthropic.

Necesita el extra ``llm`` (``pip install "centinela-ia[llm]"``) y la variable
``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import json

from centinela.providers.base import ModelResponse, ProviderError

DEFAULT_MODEL = "claude-haiku-5-5"


class AnthropicProvider:
    """Pide a Claude un JSON que cumple un esquema.

    El esfuerzo va en ``low`` porque clasificar y revisar mensajes cortos no necesita más.
    No se envía ``temperature``: los modelos actuales no la aceptan.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        effort: str = "low",
        max_tokens: int = 1024,
        client=None,
    ):
        if client is None:
            try:
                import anthropic
            except ImportError as error:  # pragma: no cover - depende de la instalación
                raise ProviderError(
                    'Falta el SDK de Anthropic. Instala el extra: pip install "centinela-ia[llm]"'
                ) from error
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.name = f"anthropic/{model}"

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse:
        import anthropic

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": message}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except anthropic.RateLimitError as error:
            raise ProviderError("Se alcanzó el límite de peticiones de la API.") from error
        except anthropic.APIStatusError as error:
            raise ProviderError(f"La API respondió con el error {error.status_code}.") from error
        except anthropic.APIConnectionError as error:
            raise ProviderError("No se pudo conectar con la API.") from error

        uso = response.usage
        if response.stop_reason == "refusal":
            return ModelResponse(
                None, refusal=True, input_tokens=uso.input_tokens, output_tokens=uso.output_tokens
            )

        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            data = None
        return ModelResponse(data, input_tokens=uso.input_tokens, output_tokens=uso.output_tokens)

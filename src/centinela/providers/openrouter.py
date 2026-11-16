"""Proveedor para cientos de modelos, abiertos y cerrados, por medio de OpenRouter.

La API de OpenRouter es compatible con la de OpenAI, así que se usa el SDK oficial
``openai``. Necesita el extra ``openrouter`` (``pip install "centinela-ia[openrouter]"``)
y la variable ``OPENROUTER_API_KEY``.
"""

from __future__ import annotations

import os

from centinela.providers.base import ModelResponse, ProviderError, is_error_from, json_from_text

URL = "https://openrouter.ai/api/v1"
#: Un modelo abierto y pequeño (Gemma 4, 4.000 millones de parámetros activos).
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"
KEY_VARIABLES = ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY")


class OpenRouterProvider:
    """Pide a un modelo de OpenRouter un JSON que cumple un esquema.

    Envía el esquema como salida estructurada. Si el modelo no la soporta y responde
    con texto, se busca el JSON en el texto; si no hay, el guardia manda el mensaje a
    revisión humana.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        max_tokens: int = 1024,
        key: str | None = None,
        client=None,
    ):
        if client is None:
            try:
                import openai
            except ImportError as error:  # pragma: no cover - depende de la instalación
                raise ProviderError(
                    'Falta el SDK de OpenAI. Instala el extra: pip install "centinela-ia[openrouter]"'
                ) from error
            key = key or next((os.environ[v] for v in KEY_VARIABLES if os.environ.get(v)), None)
            if not key:
                raise ProviderError("Falta la clave de OpenRouter: define OPENROUTER_API_KEY.")
            client = openai.OpenAI(base_url=URL, api_key=key)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"openrouter/{model}"

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "respuesta", "strict": True, "schema": schema},
                },
            )
        except Exception as error:
            if not is_error_from(error, "openai", "httpx"):
                raise
            code = getattr(error, "status_code", None)
            if code == 429:
                raise ProviderError("Se alcanzó el límite de peticiones de la API.") from error
            if isinstance(code, int):
                raise ProviderError(f"La API respondió con el error {code}.") from error
            raise ProviderError("No se pudo conectar con la API.") from error

        uso = getattr(response, "usage", None)
        input_count = getattr(uso, "prompt_tokens", 0) or 0
        output = getattr(uso, "completion_tokens", 0) or 0
        options = getattr(response, "choices", None) or []
        if not options:
            return ModelResponse(None, input_tokens=input_count, output_tokens=output)
        model_message = options[0].message
        if options[0].finish_reason == "content_filter" or getattr(model_message, "refusal", None):
            return ModelResponse(None, refusal=True, input_tokens=input_count, output_tokens=output)
        return ModelResponse(
            json_from_text(model_message.content or ""),
            input_tokens=input_count,
            output_tokens=output,
        )

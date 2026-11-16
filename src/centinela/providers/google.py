"""Proveedor para los modelos de Google (Gemini y Gemma), con el SDK oficial google-genai.

Necesita el extra ``google`` (``pip install "centinela-ia[google]"``) y una clave de
Google AI Studio en ``GOOGLE_API_KEY`` (también sirve ``GEMINI_API_KEY``).
"""

from __future__ import annotations

import os

from centinela.providers.base import ModelResponse, ProviderError, is_error_from, json_from_text

DEFAULT_MODEL = "gemini-3.5-flash-lite"
KEY_VARIABLES = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_STUDIO_API_KEY")
#: Motivos de parada que significan que Google bloqueó la respuesta.
_BLOCKS_OF_CHARS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def _name(value) -> str | None:
    return None if value is None else str(getattr(value, "name", value))


class GoogleProvider:
    """Pide a un modelo de Google un JSON que cumple un esquema.

    ``razonamiento`` es el nivel de razonamiento de Gemini 3 o posterior. Va en
    ``"minimal"`` porque revisar mensajes cortos no necesita más. Con ``None`` no se
    envía, para modelos que no aceptan niveles (Gemma, Gemini 2.5).
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        reasoning: str | None = "minimal",
        max_tokens: int = 1024,
        key: str | None = None,
        client=None,
    ):
        if client is None:
            try:
                from google import genai
            except ImportError as error:  # pragma: no cover - depende de la instalación
                raise ProviderError(
                    'Falta el SDK de Google. Instala el extra: pip install "centinela-ia[google]"'
                ) from error
            key = key or next((os.environ[v] for v in KEY_VARIABLES if os.environ.get(v)), None)
            if not key:
                raise ProviderError("Falta la clave de Google: define GOOGLE_API_KEY.")
            client = genai.Client(api_key=key)
        self.client = client
        self.model = model
        self.reasoning = reasoning
        self.max_tokens = max_tokens
        self.name = f"google/{model}"

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse:
        config: dict = {
            "system_instruction": system,
            "max_output_tokens": self.max_tokens,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        }
        if self.reasoning:
            config["thinking_config"] = {"thinking_level": self.reasoning}
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=message, config=config
            )
        except Exception as error:
            if not is_error_from(error, "google", "httpx"):
                raise
            code = getattr(error, "code", None)
            if code == 429:
                raise ProviderError("Se alcanzó el límite de peticiones de la API.") from error
            if isinstance(code, int):
                raise ProviderError(f"La API respondió con el error {code}.") from error
            raise ProviderError("No se pudo conectar con la API.") from error

        uso = getattr(response, "usage_metadata", None)
        input_count = getattr(uso, "prompt_token_count", 0) or 0
        output = (getattr(uso, "candidates_token_count", 0) or 0) + (
            getattr(uso, "thoughts_token_count", 0) or 0
        )
        candidates = getattr(response, "candidates", None) or []
        fin = _name(getattr(candidates[0], "finish_reason", None)) if candidates else None
        block = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        if block or fin in _BLOCKS_OF_CHARS:
            return ModelResponse(None, refusal=True, input_tokens=input_count, output_tokens=output)
        return ModelResponse(
            json_from_text(getattr(response, "text", None) or ""),
            input_tokens=input_count,
            output_tokens=output,
        )

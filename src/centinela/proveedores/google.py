"""Proveedor para los modelos de Google (Gemini y Gemma), con el SDK oficial google-genai.

Necesita el extra ``google`` (``pip install "centinela-ia[google]"``) y una clave de
Google AI Studio en ``GOOGLE_API_KEY`` (también sirve ``GEMINI_API_KEY``).
"""

from __future__ import annotations

import os

from centinela.proveedores.base import ErrorProveedor, RespuestaModelo, es_error_de, json_de_texto

MODELO_POR_DEFECTO = "gemini-3.5-flash-lite"
VARIABLES_DE_CLAVE = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_STUDIO_API_KEY")
#: Motivos de parada que significan que Google bloqueó la respuesta.
_BLOQUEOS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def _nombre(valor) -> str | None:
    return None if valor is None else str(getattr(valor, "name", valor))


class ProveedorGoogle:
    """Pide a un modelo de Google un JSON que cumple un esquema.

    ``razonamiento`` es el nivel de razonamiento de Gemini 3 o posterior. Va en
    ``"minimal"`` porque revisar mensajes cortos no necesita más. Con ``None`` no se
    envía, para modelos que no aceptan niveles (Gemma, Gemini 2.5).
    """

    def __init__(
        self,
        modelo: str = MODELO_POR_DEFECTO,
        *,
        razonamiento: str | None = "minimal",
        max_tokens: int = 1024,
        clave: str | None = None,
        cliente=None,
    ):
        if cliente is None:
            try:
                from google import genai
            except ImportError as error:  # pragma: no cover - depende de la instalación
                raise ErrorProveedor(
                    'Falta el SDK de Google. Instala el extra: pip install "centinela-ia[google]"'
                ) from error
            clave = clave or next(
                (os.environ[v] for v in VARIABLES_DE_CLAVE if os.environ.get(v)), None
            )
            if not clave:
                raise ErrorProveedor("Falta la clave de Google: define GOOGLE_API_KEY.")
            cliente = genai.Client(api_key=clave)
        self.cliente = cliente
        self.modelo = modelo
        self.razonamiento = razonamiento
        self.max_tokens = max_tokens
        self.nombre = f"google/{modelo}"

    def responder_json(self, *, sistema: str, mensaje: str, esquema: dict) -> RespuestaModelo:
        config: dict = {
            "system_instruction": sistema,
            "max_output_tokens": self.max_tokens,
            "response_mime_type": "application/json",
            "response_json_schema": esquema,
        }
        if self.razonamiento:
            config["thinking_config"] = {"thinking_level": self.razonamiento}
        try:
            respuesta = self.cliente.models.generate_content(
                model=self.modelo, contents=mensaje, config=config
            )
        except Exception as error:
            if not es_error_de(error, "google", "httpx"):
                raise
            codigo = getattr(error, "code", None)
            if codigo == 429:
                raise ErrorProveedor("Se alcanzó el límite de peticiones de la API.") from error
            if isinstance(codigo, int):
                raise ErrorProveedor(f"La API respondió con el error {codigo}.") from error
            raise ErrorProveedor("No se pudo conectar con la API.") from error

        uso = getattr(respuesta, "usage_metadata", None)
        entrada = getattr(uso, "prompt_token_count", 0) or 0
        salida = (getattr(uso, "candidates_token_count", 0) or 0) + (
            getattr(uso, "thoughts_token_count", 0) or 0
        )
        candidatos = getattr(respuesta, "candidates", None) or []
        fin = _nombre(getattr(candidatos[0], "finish_reason", None)) if candidatos else None
        bloqueo = getattr(getattr(respuesta, "prompt_feedback", None), "block_reason", None)
        if bloqueo or fin in _BLOQUEOS:
            return RespuestaModelo(None, rechazo=True, tokens_entrada=entrada, tokens_salida=salida)
        return RespuestaModelo(
            json_de_texto(getattr(respuesta, "text", None) or ""),
            tokens_entrada=entrada,
            tokens_salida=salida,
        )

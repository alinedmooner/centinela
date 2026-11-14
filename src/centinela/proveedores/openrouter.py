"""Proveedor para cientos de modelos, abiertos y cerrados, por medio de OpenRouter.

La API de OpenRouter es compatible con la de OpenAI, así que se usa el SDK oficial
``openai``. Necesita el extra ``openrouter`` (``pip install "centinela-ia[openrouter]"``)
y la variable ``OPENROUTER_API_KEY``.
"""

from __future__ import annotations

import os

from centinela.proveedores.base import ErrorProveedor, RespuestaModelo, es_error_de, json_de_texto

URL = "https://openrouter.ai/api/v1"
#: Un modelo abierto y pequeño (Gemma 4, 4.000 millones de parámetros activos).
MODELO_POR_DEFECTO = "google/gemma-4-26b-a4b-it"
VARIABLES_DE_CLAVE = ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY")


class ProveedorOpenRouter:
    """Pide a un modelo de OpenRouter un JSON que cumple un esquema.

    Envía el esquema como salida estructurada. Si el modelo no la soporta y responde
    con texto, se busca el JSON en el texto; si no hay, el guardia manda el mensaje a
    revisión humana.
    """

    def __init__(
        self,
        modelo: str = MODELO_POR_DEFECTO,
        *,
        max_tokens: int = 1024,
        clave: str | None = None,
        cliente=None,
    ):
        if cliente is None:
            try:
                import openai
            except ImportError as error:  # pragma: no cover - depende de la instalación
                raise ErrorProveedor(
                    'Falta el SDK de OpenAI. Instala el extra: pip install "centinela-ia[openrouter]"'
                ) from error
            clave = clave or next(
                (os.environ[v] for v in VARIABLES_DE_CLAVE if os.environ.get(v)), None
            )
            if not clave:
                raise ErrorProveedor("Falta la clave de OpenRouter: define OPENROUTER_API_KEY.")
            cliente = openai.OpenAI(base_url=URL, api_key=clave)
        self.cliente = cliente
        self.modelo = modelo
        self.max_tokens = max_tokens
        self.nombre = f"openrouter/{modelo}"

    def responder_json(self, *, sistema: str, mensaje: str, esquema: dict) -> RespuestaModelo:
        try:
            respuesta = self.cliente.chat.completions.create(
                model=self.modelo,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": mensaje},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "respuesta", "strict": True, "schema": esquema},
                },
            )
        except Exception as error:
            if not es_error_de(error, "openai", "httpx"):
                raise
            codigo = getattr(error, "status_code", None)
            if codigo == 429:
                raise ErrorProveedor("Se alcanzó el límite de peticiones de la API.") from error
            if isinstance(codigo, int):
                raise ErrorProveedor(f"La API respondió con el error {codigo}.") from error
            raise ErrorProveedor("No se pudo conectar con la API.") from error

        uso = getattr(respuesta, "usage", None)
        entrada = getattr(uso, "prompt_tokens", 0) or 0
        salida = getattr(uso, "completion_tokens", 0) or 0
        opciones = getattr(respuesta, "choices", None) or []
        if not opciones:
            return RespuestaModelo(None, tokens_entrada=entrada, tokens_salida=salida)
        mensaje_modelo = opciones[0].message
        if opciones[0].finish_reason == "content_filter" or getattr(
            mensaje_modelo, "refusal", None
        ):
            return RespuestaModelo(None, rechazo=True, tokens_entrada=entrada, tokens_salida=salida)
        return RespuestaModelo(
            json_de_texto(mensaje_modelo.content or ""),
            tokens_entrada=entrada,
            tokens_salida=salida,
        )

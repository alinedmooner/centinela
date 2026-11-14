"""Proveedor para los modelos Claude, con el SDK oficial de Anthropic.

Necesita el extra ``llm`` (``pip install "centinela-ia[llm]"``) y la variable
``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import json

from centinela.proveedores.base import ErrorProveedor, RespuestaModelo

MODELO_POR_DEFECTO = "claude-haiku-5-5"


class ProveedorAnthropic:
    """Pide a Claude un JSON que cumple un esquema.

    El esfuerzo va en ``low`` porque clasificar y revisar mensajes cortos no necesita más.
    No se envía ``temperature``: los modelos actuales no la aceptan.
    """

    def __init__(
        self,
        modelo: str = MODELO_POR_DEFECTO,
        *,
        esfuerzo: str = "low",
        max_tokens: int = 1024,
        cliente=None,
    ):
        if cliente is None:
            try:
                import anthropic
            except ImportError as error:  # pragma: no cover - depende de la instalación
                raise ErrorProveedor(
                    'Falta el SDK de Anthropic. Instala el extra: pip install "centinela-ia[llm]"'
                ) from error
            cliente = anthropic.Anthropic()
        self.cliente = cliente
        self.modelo = modelo
        self.esfuerzo = esfuerzo
        self.max_tokens = max_tokens
        self.nombre = f"anthropic/{modelo}"

    def responder_json(self, *, sistema: str, mensaje: str, esquema: dict) -> RespuestaModelo:
        import anthropic

        try:
            respuesta = self.cliente.messages.create(
                model=self.modelo,
                max_tokens=self.max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": mensaje}],
                output_config={
                    "effort": self.esfuerzo,
                    "format": {"type": "json_schema", "schema": esquema},
                },
            )
        except anthropic.RateLimitError as error:
            raise ErrorProveedor("Se alcanzó el límite de peticiones de la API.") from error
        except anthropic.APIStatusError as error:
            raise ErrorProveedor(f"La API respondió con el error {error.status_code}.") from error
        except anthropic.APIConnectionError as error:
            raise ErrorProveedor("No se pudo conectar con la API.") from error

        uso = respuesta.usage
        if respuesta.stop_reason == "refusal":
            return RespuestaModelo(
                None, rechazo=True, tokens_entrada=uso.input_tokens, tokens_salida=uso.output_tokens
            )

        texto = next((bloque.text for bloque in respuesta.content if bloque.type == "text"), "")
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError:
            datos = None
        if not isinstance(datos, dict):
            datos = None
        return RespuestaModelo(
            datos, tokens_entrada=uso.input_tokens, tokens_salida=uso.output_tokens
        )

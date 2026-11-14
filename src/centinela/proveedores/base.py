"""Interfaz mínima para conectar cualquier modelo de lenguaje."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RespuestaModelo:
    """Lo que devolvió el modelo a una petición con esquema."""

    #: El JSON que devolvió el modelo, o ``None`` si no devolvió un JSON válido.
    datos: dict | None
    #: El modelo se negó a responder (por ejemplo, por sus filtros de seguridad).
    rechazo: bool = False
    tokens_entrada: int = 0
    tokens_salida: int = 0


class ErrorProveedor(RuntimeError):
    """El proveedor no pudo responder (red, límites, credenciales)."""


@runtime_checkable
class Proveedor(Protocol):
    """Modelo que responde con un JSON que cumple un esquema.

    Para usar otro proveedor (OpenAI, Gemini, un modelo local) basta una clase con un
    atributo ``nombre`` y este método.
    """

    nombre: str

    def responder_json(self, *, sistema: str, mensaje: str, esquema: dict) -> RespuestaModelo: ...


def json_de_texto(texto: str) -> dict | None:
    """El objeto JSON de una respuesta, aunque venga entre marcas de bloque de código."""
    limpio = re.sub(r"^```(?:json)?\s*|\s*```$", "", (texto or "").strip())
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, dict) else None


def es_error_de(error: Exception, *paquetes: str) -> bool:
    """El error viene de uno de estos paquetes (el SDK del proveedor o su cliente HTTP)."""
    return type(error).__module__.split(".")[0] in paquetes

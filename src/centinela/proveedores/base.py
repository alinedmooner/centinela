"""Interfaz mínima para conectar cualquier modelo de lenguaje."""

from __future__ import annotations

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

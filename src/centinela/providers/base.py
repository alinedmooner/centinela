"""Interfaz mínima para conectar cualquier modelo de lenguaje."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ModelResponse:
    """Lo que devolvió el modelo a una petición con esquema."""

    #: El JSON que devolvió el modelo, o ``None`` si no devolvió un JSON válido.
    data: dict | None
    #: El modelo se negó a responder (por ejemplo, por sus filtros de seguridad).
    refusal: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderError(RuntimeError):
    """El proveedor no pudo responder (red, límites, credenciales)."""


@runtime_checkable
class Provider(Protocol):
    """Modelo que responde con un JSON que cumple un esquema.

    Para usar otro proveedor (OpenAI, Gemini, un modelo local) basta una clase con un
    atributo ``nombre`` y este método.
    """

    name: str

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse: ...


def json_from_text(text: str) -> dict | None:
    """El objeto JSON de una respuesta, aunque venga entre marcas de bloque de código."""
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def is_error_from(error: Exception, *packages: str) -> bool:
    """El error viene de uno de estos paquetes (el SDK del proveedor o su cliente HTTP)."""
    return type(error).__module__.split(".")[0] in packages

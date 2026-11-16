"""Interfaz que cumple cualquier detector de Centinela."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from centinela.verdict import Finding


@runtime_checkable
class Detector(Protocol):
    """Revisa un mensaje y devuelve lo que encontró.

    Para agregar un detector basta una clase con un atributo ``nombre`` y este método.
    Un detector no debe lanzar excepciones por culpa del mensaje: si no puede responder,
    devuelve un :class:`Hallazgo` con ``error``.
    """

    name: str

    def check(self, text: str) -> Finding: ...

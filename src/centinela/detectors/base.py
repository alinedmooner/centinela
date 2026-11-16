"""Interface that any Centinela detector implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from centinela.verdict import Finding


@runtime_checkable
class Detector(Protocol):
    """Checks a message and returns what it found.

    To add a detector, a class with a ``name`` attribute and this method is enough.
    A detector must not raise exceptions because of the message: if it cannot respond,
    it returns a :class:`Finding` with ``error``.
    """

    name: str

    def check(self, text: str) -> Finding: ...

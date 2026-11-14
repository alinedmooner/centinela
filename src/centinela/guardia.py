"""El guardia: junta lo que dicen los detectores y decide qué hacer con un mensaje."""

from __future__ import annotations

from collections.abc import Sequence

from centinela.detectores.base import Detector
from centinela.detectores.reglas import DetectorReglas
from centinela.tipos import TRUCOS, Hallazgo, Veredicto


class Guardia:
    """Revisa un mensaje con uno o varios detectores.

    La decisión es ``revisar`` si algún detector encuentra órdenes para la IA o un engaño
    dirigido a personas. Con ``fallar_cerrado`` (por defecto), un detector que no pudo
    responder también manda el mensaje a revisión: ante la duda, decide una persona.
    """

    def __init__(
        self, detectores: Sequence[Detector] | None = None, *, fallar_cerrado: bool = True
    ):
        self.detectores: list[Detector] = list(detectores) if detectores else [DetectorReglas()]
        self.fallar_cerrado = fallar_cerrado

    def revisar(self, texto: str) -> Veredicto:
        hallazgos: list[Hallazgo] = []
        for detector in self.detectores:
            try:
                hallazgos.append(detector.revisar(texto))
            except Exception as error:  # noqa: BLE001 - un detector nunca debe tumbar al guardia
                hallazgos.append(
                    Hallazgo(detector=detector.nombre, error=f"{type(error).__name__}: {error}")
                )

        ordenes = any(h.ordenes_para_ia for h in hallazgos)
        engano = any(h.engano_a_personas for h in hallazgos)
        con_error = [h for h in hallazgos if h.error]
        trucos = tuple(dict.fromkeys(t for h in hallazgos for t in h.trucos if t in TRUCOS))
        evidencias = tuple(dict.fromkeys(e for h in hallazgos for e in h.evidencias))
        revisar = ordenes or engano or (self.fallar_cerrado and bool(con_error))

        return Veredicto(
            decision="revisar" if revisar else "permitir",
            ordenes_para_ia=ordenes,
            engano_a_personas=engano,
            trucos=trucos,
            evidencias=evidencias,
            aviso=_aviso(ordenes, engano, trucos, bool(con_error) and self.fallar_cerrado),
            hallazgos=tuple(hallazgos),
        )


def _aviso(ordenes: bool, engano: bool, trucos: tuple[str, ...], fallo: bool) -> str:
    partes: list[str] = []
    if ordenes:
        partes.append("Trae órdenes dirigidas al asistente de IA.")
    if engano:
        partes.append("Parece un engaño dirigido a una persona.")
    if trucos:
        partes.append("Trucos que usa: " + "; ".join(TRUCOS[t] for t in trucos) + ".")
    if fallo and not (ordenes or engano):
        partes.append("Un detector no pudo revisarlo; por precaución lo ve una persona.")
    return " ".join(partes) if partes else "Sin señales de manipulación."


def revisar(texto: str) -> Veredicto:
    """Atajo: revisa un mensaje con el detector de reglas, sin clave ni internet."""
    return Guardia().revisar(texto)

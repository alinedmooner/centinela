"""El guardia: junta lo que dicen los detectores y decide qué hacer con un mensaje."""

from __future__ import annotations

from collections.abc import Sequence

from centinela.detectors.base import Detector
from centinela.detectors.rules import RulesDetector
from centinela.verdict import TRICKS, Finding, Verdict


class Guard:
    """Revisa un mensaje con uno o varios detectores.

    La decisión es ``revisar`` si algún detector encuentra órdenes para la IA o un engaño
    dirigido a personas. Con ``fallar_cerrado`` (por defecto), un detector que no pudo
    responder también manda el mensaje a revisión: ante la duda, decide una persona.
    """

    def __init__(self, detectors: Sequence[Detector] | None = None, *, fail_closed: bool = True):
        self.detectors: list[Detector] = list(detectors) if detectors else [RulesDetector()]
        self.fail_closed = fail_closed

    def check(self, text: str) -> Verdict:
        findings: list[Finding] = []
        for detector in self.detectors:
            try:
                findings.append(detector.check(text))
            except Exception as error:  # noqa: BLE001 - un detector nunca debe tumbar al guardia
                findings.append(
                    Finding(detector=detector.name, error=f"{type(error).__name__}: {error}")
                )

        ai_instructions = any(h.ai_instructions for h in findings)
        deception = any(h.people_deception for h in findings)
        with_error = [h for h in findings if h.error]
        tricks = tuple(dict.fromkeys(t for h in findings for t in h.tricks if t in TRICKS))
        evidence = tuple(dict.fromkeys(e for h in findings for e in h.evidence))
        check = ai_instructions or deception or (self.fail_closed and bool(with_error))

        return Verdict(
            decision="revisar" if check else "permitir",
            ai_instructions=ai_instructions,
            people_deception=deception,
            tricks=tricks,
            evidence=evidence,
            notice=_notice(
                ai_instructions, deception, tricks, bool(with_error) and self.fail_closed
            ),
            findings=tuple(findings),
        )


def _notice(ai_instructions: bool, deception: bool, tricks: tuple[str, ...], failure: bool) -> str:
    parts: list[str] = []
    if ai_instructions:
        parts.append("Trae órdenes dirigidas al asistente de IA.")
    if deception:
        parts.append("Parece un engaño dirigido a una persona.")
    if tricks:
        parts.append("Trucos que usa: " + "; ".join(TRICKS[t] for t in tricks) + ".")
    if failure and not (ai_instructions or deception):
        parts.append("Un detector no pudo revisarlo; por precaución lo ve una persona.")
    return " ".join(parts) if parts else "Sin señales de manipulación."


def check(text: str) -> Verdict:
    """Atajo: revisa un mensaje con el detector de reglas, sin clave ni internet."""
    return Guard().check(text)

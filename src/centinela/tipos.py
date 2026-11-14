"""Tipos de datos que comparten los detectores, el guardia y el clasificador."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Decision = Literal["permitir", "revisar"]

#: Trucos de persuasión que Centinela nombra para la persona. Son los principios de
#: Ferreira et al. (2015), los mismos que anota el conjunto SpaPhish.
TRUCOS: dict[str, str] = {
    "autoridad": "se presenta como alguien con autoridad (jefe, banco, soporte, gobierno)",
    "prueba_social": "dice que otras personas ya lo hicieron o lo aprueban",
    "simpatia_engano": "finge cercanía o confianza para ganarse a la persona",
    "compromiso_reciprocidad": "apela a un compromiso previo o a devolver un favor",
    "distraccion_urgencia": "mete prisa, miedo o un premio para que la persona no piense",
}


@dataclass(frozen=True)
class Hallazgo:
    """Lo que un detector encontró en un mensaje."""

    detector: str
    #: El mensaje trae instrucciones dirigidas a la IA que lo lee.
    ordenes_para_ia: bool = False
    #: El mensaje parece un engaño dirigido a una persona (phishing, estafa).
    engano_a_personas: bool = False
    #: Claves de :data:`TRUCOS` que el detector reconoció.
    trucos: tuple[str, ...] = ()
    #: Fragmentos o nombres de regla que justifican el hallazgo.
    evidencias: tuple[str, ...] = ()
    #: Si el detector no pudo responder, aquí va el motivo.
    error: str | None = None


@dataclass(frozen=True)
class Veredicto:
    """Decisión del guardia sobre un mensaje."""

    decision: Decision
    ordenes_para_ia: bool
    engano_a_personas: bool
    trucos: tuple[str, ...]
    evidencias: tuple[str, ...]
    #: Una línea para la persona que va a leer el mensaje.
    aviso: str
    hallazgos: tuple[Hallazgo, ...] = ()

    def a_dict(self) -> dict:
        """Versión serializable del veredicto."""
        return asdict(self)

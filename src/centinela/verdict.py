"""Data types shared by the detectors, the guard and the classifier."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from centinela.catalog import DEFAULT_LANG

Decision = Literal["allow", "review"]

#: Persuasion tricks Centinela names for the person who reviews a message. They are the
#: principles of Ferreira et al. (2015), the same ones the SpaPhish dataset annotates. The
#: ids are in Spanish on purpose: they are part of the JSON schema a model answers with.
#: What a person reads for each id is in :mod:`centinela.catalog` (``trick.<id>``).
TRICKS: tuple[str, ...] = (
    "autoridad",
    "prueba_social",
    "simpatia_engano",
    "compromiso_reciprocidad",
    "distraccion_urgencia",
)


@dataclass(frozen=True)
class Finding:
    """What one detector found in a message."""

    detector: str
    #: The message carries instructions addressed to the AI that reads it.
    ai_instructions: bool = False
    #: The message looks like a deception aimed at a person (phishing, scam).
    people_deception: bool = False
    #: Ids from :data:`TRICKS` that the detector recognized.
    tricks: tuple[str, ...] = ()
    #: Fragments or rule names that justify the finding.
    evidence: tuple[str, ...] = ()
    #: If the detector could not answer, the reason goes here.
    error: str | None = None


@dataclass(frozen=True)
class Verdict:
    """The guard's decision about a message."""

    decision: Decision
    ai_instructions: bool
    people_deception: bool
    tricks: tuple[str, ...]
    evidence: tuple[str, ...]
    #: One line for the person who is going to read the message, in ``lang``.
    notice: str
    findings: tuple[Finding, ...] = ()
    #: Language of ``notice`` and of everything built from this verdict (``en`` or ``es``).
    lang: str = DEFAULT_LANG

    def to_dict(self) -> dict:
        """A serializable version of the verdict."""
        return asdict(self)

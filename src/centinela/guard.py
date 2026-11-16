"""The guard: gathers what the detectors say and decides what to do with a message."""

from __future__ import annotations

from collections.abc import Sequence

from centinela.catalog import DEFAULT_LANG, check_lang, t
from centinela.detectors.base import Detector
from centinela.detectors.rules import RulesDetector
from centinela.verdict import TRICKS, Finding, Verdict


class Guard:
    """Checks a message with one or more detectors.

    The decision is ``review`` if any detector finds orders for the AI or a deception aimed
    at people. With ``fail_closed`` (the default), a detector that could not answer also
    sends the message to review: when in doubt, a person decides.

    ``lang`` (``en`` or ``es``) is the language of the notice a person reads. It does not
    change what the detectors do.
    """

    def __init__(
        self,
        detectors: Sequence[Detector] | None = None,
        *,
        fail_closed: bool = True,
        lang: str = DEFAULT_LANG,
    ):
        self.detectors: list[Detector] = list(detectors) if detectors else [RulesDetector()]
        self.fail_closed = fail_closed
        self.lang = check_lang(lang)

    def check(self, text: str) -> Verdict:
        findings: list[Finding] = []
        for detector in self.detectors:
            try:
                findings.append(detector.check(text))
            except Exception as error:  # noqa: BLE001 - a detector must never take the guard down
                findings.append(
                    Finding(detector=detector.name, error=f"{type(error).__name__}: {error}")
                )

        ai_instructions = any(h.ai_instructions for h in findings)
        deception = any(h.people_deception for h in findings)
        with_error = [h for h in findings if h.error]
        tricks = tuple(dict.fromkeys(t for h in findings for t in h.tricks if t in TRICKS))
        evidence = tuple(dict.fromkeys(e for h in findings for e in h.evidence))
        needs_review = ai_instructions or deception or (self.fail_closed and bool(with_error))

        return Verdict(
            decision="review" if needs_review else "allow",
            ai_instructions=ai_instructions,
            people_deception=deception,
            tricks=tricks,
            evidence=evidence,
            notice=_notice(
                ai_instructions, deception, tricks, bool(with_error) and self.fail_closed, self.lang
            ),
            findings=tuple(findings),
            lang=self.lang,
        )


def _notice(
    ai_instructions: bool, deception: bool, tricks: tuple[str, ...], failure: bool, lang: str
) -> str:
    parts: list[str] = []
    if ai_instructions:
        parts.append(t("notice.ai_instructions", lang))
    if deception:
        parts.append(t("notice.deception", lang))
    if tricks:
        names = "; ".join(t(f"trick.{trick}", lang) for trick in tricks)
        parts.append(t("notice.tricks", lang, tricks=names))
    if failure and not (ai_instructions or deception):
        parts.append(t("notice.detector_failed", lang))
    return " ".join(parts) if parts else t("notice.none", lang)


def check(text: str, lang: str = DEFAULT_LANG) -> Verdict:
    """Shortcut: check a message with the rules detector, without a key or internet."""
    return Guard(lang=lang).check(text)

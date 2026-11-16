"""Review room: what the person who reviews a suspicious message sees and can do.

The person who reviews can also be deceived by the message. That is why the room treats them
the same way as the bot:

1. **The message arrives defanged.** Links, emails, phone numbers and account numbers are
   shown disabled: they can be read, but not opened or copied as they are.
2. **A card separates what the message says from what it asks.** The code builds it: who the
   sender claims to be, what they ask to do and how they pressure.
3. **The decisions are bounded.** There are only three, and none does what the message asks.
   A released message does not go back to the model: the person chooses the label.

Everything works without a key or internet. The hints on the card are simple rules: they
guide the reviewer, they do not decide for them. The rules look for Spanish words, because
Spanish is the language of the messages Centinela analyzes.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from centinela.catalog import DEFAULT_LANG, check_lang, t
from centinela.detectors.rules import _strip_accents
from centinela.labels import LEAD_LABELS
from centinela.verdict import Verdict

Action = Literal["is_fraud", "is_legitimate", "not_sure"]
ACTIONS: tuple[Action, ...] = ("is_fraud", "is_legitimate", "not_sure")

_TLD = (
    "com|net|org|info|biz|co|io|app|dev|xyz|top|online|site|shop|store|link|click|live|club|vip"
    "|icu|me|tv|cc|ly|gl|es|mx|ar|cl|pe|ec|ve|uy|py|bo|br|us|uk|de|fr|it|ru|cn|edu|gov|gob|example"
)
_EMAIL = re.compile(r"\b[\w.%+-]+@[\w-]+(?:\.[\w-]+)+\b")
_URL = re.compile(r"(?i)(?:[a-z][a-z0-9+-]{1,12}://|\bwww\.)[^\s<>\"'\])]+")
# The ending is lowercase: «compra.Es un gusto» is a period without a space, not a domain.
_DOMAIN = re.compile(rf"(?<![\w@\[/.])(?:[\w-]+\.)+(?:{_TLD})\b(?:/[^\s<>\"'\])]*)?")
_NUMBER = re.compile(r"(?<![\w$.,/-])\+?\d(?:[ ()-]{0,2}\d){6,18}(?![\w%/])")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}")
#: Characters that are not seen or that change the order in which the text is read.
_INVISIBLE = re.compile(
    "["
    + "".join(chr(c) for c in (0x00AD, 0x061C, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F))
    + "".join(chr(c) for c in (0x2060, 0xFEFF))
    + f"{chr(0x202A)}-{chr(0x202E)}{chr(0x2066)}-{chr(0x2069)}"
    + "]"
)
_BREAKS = re.compile(r"\n\s*\n(\s*\n)+")

#: What the message asks to do, by id. The patterns run on lowercase text without accents.
_ASKS: dict[str, re.Pattern[str]] = {
    "open_link": re.compile(
        r"\b(haga|haz|hagan|hacer|dar|den|dele) (clic|click)\b"
        r"|\b(ingres\w+|entr\w+|acced\w+|visit\w+) (a|al|en|aqui)\b"
        r"|\b(abr\w+|sigu\w+|puls\w+|presion\w+) (el|este|en el|en este|el siguiente) (enlace|link|boton|vinculo)\b"
    ),
    "give_credentials": re.compile(
        r"\b(confirm\w+|verifi\w+|actuali[cz]\w+|ingres\w+|envi\w+|proporcion\w+|compart\w+|digit\w+|valid\w+)\b"
        r"[^.\n]{0,50}\b(clave|contrasena|usuario|datos|tarjeta|cvv|pin|codigo|token|cedula|documento)\b"
    ),
    "send_money": re.compile(
        r"\b(pague|paguen|paga|pagar|transfiera|transfieran|transfiere|transferir|consigne|consignar"
        r"|deposite|depositar|gire|girar|abone|abonar)\b"
        r"|\b(realice|realiza|efectue|efectua|haga|haz) (el|su|tu|un) (pago|deposito|giro)\b"
        r"|\b(haga|haz|realice|realiza) (la|una|su|tu) (transferencia|consignacion)\b"
    ),
    "open_file": re.compile(
        r"\b(descarg\w+|instal\w+)\b"
        r"|\b(abr\w+|revis\w+)\b[^.\n]{0,25}\b(archivo|adjunto|pdf)\b"
    ),
    "contact": re.compile(
        r"\b(llam\w+|comuniqu\w+|comunicate|escrib\w+|contact\w+)\b[^.\n]{0,30}"
        r"\b(al|a este|a nuestro|numero|telefono|whatsapp)\b"
    ),
}
#: What the person who reads the message must be told about the AI, when the verdict says
#: it carries instructions for it. It is not found by a pattern: the guard decides it.
INSTRUCT_AI = "instruct_ai"
#: Every id ``ReviewCard.asks`` can hold, and the ids of ``ReviewCard.pressure``.
ASK_IDS = (*_ASKS, INSTRUCT_AI)
#: Asks for which releasing the message requires a second person.
SENSITIVE_ASKS = frozenset({"give_credentials", "send_money"})

#: How the message pressures, by id.
_PRESSURE: dict[str, re.Pattern[str]] = {
    "urgency": re.compile(
        r"\b(urgente|urge|inmediatamente|de inmediato|ahora mismo|hoy mismo|cuanto antes"
        r"|ultim[oa]s? (aviso|oportunidad|dia|horas?)|en (las proximas )?\d+ (horas|minutos|dias))\b"
    ),
    "threat": re.compile(
        r"\b(suspend\w+|bloque\w+|cancelad\w+|cancelacion|cierre de|multa\w*|embarg\w+|demanda\w*"
        r"|penaliz\w+|inhabilit\w+|desactiv\w+|perdera|perderas)\b"
    ),
    "prize_or_offer": re.compile(
        r"\b(gano|ganaste|ganador\w*|premio\w*|bono\w*|gratis|sorteo\w*|regalo\w*|felicidades"
        r"|felicitaciones|reembolso\w*)\b"
    ),
}
PRESSURE_IDS = tuple(_PRESSURE)
_CLAIMS_TO_BE = re.compile(
    r"(?i)\b(?:soy|somos|le habla|le escribe|te escribe|le saluda|de parte de)\s+"
    r"((?:el |la |los |las |del |de la |tu |su )?[^.,;:\n]{3,60})"
)
_INSTITUTION = re.compile(
    r"\b(su banco|tu banco|banco \w+|soporte tecnico|equipo de seguridad|departamento de \w+"
    r"|area de \w+|gerencia|recursos humanos|servicio al cliente)\b"
)


@dataclass(frozen=True)
class ReviewCard:
    """What the person who reviews a quarantined message sees.

    ``asks`` and ``pressure`` hold ids (``open_link``, ``urgency``...), so the card does not
    depend on a language; ``render_card`` writes them in ``lang``.
    """

    notice: str
    claims_to_be: tuple[str, ...]
    asks: tuple[str, ...]
    pressure: tuple[str, ...]
    #: Links and emails in the message, already disabled.
    links: tuple[str, ...]
    #: The whole message, with links, emails and numbers disabled.
    defanged_text: str
    actions: tuple[Action, ...] = ACTIONS
    #: Releasing this message requires two different people.
    needs_second_person: bool = False
    #: Domains the links lead to that are not written in the text (for example, the real
    #: destination of a button in an HTML email).
    hidden_destinations: tuple[str, ...] = ()
    #: Language of the texts built from this card (``en`` or ``es``).
    lang: str = DEFAULT_LANG


@dataclass(frozen=True)
class Resolution:
    """What happens to a message after someone reviews it."""

    state: Literal["blocked", "released", "awaiting_second_person", "escalated"]
    #: Only if it was released. A person sets it, not the model.
    label: str | None
    reviewers: tuple[str, ...]
    note: str


def _break(text: str) -> str:
    return text.replace(".", "[.]")


def _visible(domain: str, lang: str = DEFAULT_LANG) -> str:
    """A domain with letters from other alphabets can imitate another: show its real form."""
    if domain.isascii():
        return domain
    try:
        real = domain.replace("[.]", ".").encode("idna").decode("ascii")
    except UnicodeError:
        real = domain.replace("[.]", ".").encode("ascii", "backslashreplace").decode("ascii")
    return _break(real) + t("defang.looks_like", lang, domain=domain)


def _disable(link: str, lang: str = DEFAULT_LANG) -> tuple[str, str]:
    """Return the disabled link and its domain, without path, user or port."""
    broken = _break(re.sub(r"(?i)http(s?)://", r"hxxp\1://", link))
    domain = broken.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return broken, _visible(domain.split("@")[-1].split(":")[0], lang)


_CUTS = re.compile(r"\s+(?:y|e|que|para|porque|pero|quien|con el fin)\s+")
_DANGLING = frozenset({"de", "del", "la", "el", "los", "las", "su", "tu", "en", "a", "con", "y"})


def _who(sentence: str) -> str:
    """Trim what follows «soy…» or «le escribe…» until a short name is left."""
    words = _CUTS.split(sentence, maxsplit=1)[0].split()[:8]
    while words and words[-1].lower() in _DANGLING:
        words.pop()
    return " ".join(words)


def defang(text: str, lang: str = DEFAULT_LANG) -> tuple[str, tuple[str, ...]]:
    """Disable links, emails, phone numbers and account numbers.

    Return the defanged text and the list of links and emails it had, already disabled.
    ``lang`` is the language of the placeholders the text gets.
    """
    #: Pairs (how it ended up in the text, how it is shown in the card's list).
    found: list[tuple[str, str]] = []

    def mail(m: re.Match[str]) -> str:
        user, domain = m.group(0).rsplit("@", 1)
        broken = f"{_break(user)}[@]{_break(domain)}"
        found.append((broken, f"{_break(user)}[@]{_visible(_break(domain), lang)}"))
        return broken

    def link(m: re.Match[str]) -> str:
        body = m.group(0).rstrip(".,;:!?")
        broken, domain = _disable(body, lang)
        found.append((broken, domain))
        return broken + m.group(0)[len(body) :]

    def number(m: re.Match[str]) -> str:
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if _DATE.fullmatch(raw.strip()) or len(digits) < 7:
            return raw
        return t("defang.hidden_number", lang, digits=digits[-2:])

    clean = "".join(c for c in text if not 0xE0000 <= ord(c) <= 0xE007F)
    clean = _INVISIBLE.sub("", clean)
    clean = _BREAKS.sub("\n\n", clean)
    clean = _URL.sub(link, clean)
    clean = _EMAIL.sub(mail, clean)
    clean = _DOMAIN.sub(link, clean)
    clean = _NUMBER.sub(number, clean)
    plain = clean.lower()
    in_order = sorted(found, key=lambda pair: plain.find(pair[0].lower()))
    return clean, tuple(dict.fromkeys(shown.lower() for _, shown in in_order if shown))


def create_card(
    text: str,
    verdict: Verdict,
    *,
    hidden_links: Iterable[str] = (),
    lang: str | None = None,
) -> ReviewCard:
    """Build the review card of a message from the guard's verdict.

    ``hidden_links`` are destinations that are not seen in the text, like the ``href`` of an
    HTML email. The card shows them, disabled, next to those of the text. The card is in the
    language of the verdict unless ``lang`` says otherwise.
    """
    lang = check_lang(lang or verdict.lang)
    defanged, links = defang(text, lang)
    hidden_items = [_disable(e.strip(), lang)[1].lower() for e in hidden_links if e.strip()]
    hidden_destinations = tuple(d for d in dict.fromkeys(hidden_items) if d not in links)
    links = tuple(dict.fromkeys((*links, *hidden_items)))
    plain = _strip_accents(text.lower())

    asks = [name for name, pattern in _ASKS.items() if pattern.search(plain)]
    if verdict.ai_instructions:
        asks.insert(0, INSTRUCT_AI)
    presses = [name for name, pattern in _PRESSURE.items() if pattern.search(plain)]

    claims_to_be = [q for q in (_who(m.group(1)) for m in _CLAIMS_TO_BE.finditer(defanged)) if q]
    for m in _INSTITUTION.finditer(plain):
        if not any(m.group(1) in _strip_accents(q.lower()) for q in claims_to_be):
            claims_to_be.append(m.group(1))

    return ReviewCard(
        notice=verdict.notice,
        claims_to_be=tuple(dict.fromkeys(claims_to_be))[:3],
        asks=tuple(asks),
        pressure=tuple(presses),
        links=links,
        defanged_text=defanged,
        needs_second_person=verdict.people_deception or any(p in SENSITIVE_ASKS for p in asks),
        hidden_destinations=hidden_destinations,
        lang=lang,
    )


def render_card(card: ReviewCard) -> str:
    """The card as text, ready to show in a terminal or in an internal chat."""
    lang = card.lang

    def joined(values: tuple[str, ...], empty: str) -> str:
        return "; ".join(values) if values else empty

    def names(prefix: str, ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(t(f"{prefix}.{item}", lang) for item in ids)

    fields = [
        (t("card.field.notice", lang), card.notice),
        (t("card.field.claims", lang), joined(card.claims_to_be, t("card.none.claims", lang))),
        (
            t("card.field.asks", lang),
            joined(names("ask", card.asks), t("card.none.recognized", lang)),
        ),
        (
            t("card.field.pressure", lang),
            joined(names("pressure", card.pressure), t("card.none.recognized", lang)),
        ),
    ]
    width = max(len(label) for label, _ in fields) + 1
    legitimate = t("card.action.is_legitimate", lang)
    if card.needs_second_person:
        legitimate += t("card.second_person", lang)
    return "\n".join(
        [
            t("card.title", lang),
            *(f"{label.ljust(width)}{value}" for label, value in fields),
            t("card.links", lang, links=joined(card.links, t("card.none.links", lang))),
            *(
                [t("card.hidden_warning", lang, destinations=joined(card.hidden_destinations, ""))]
                if card.hidden_destinations
                else []
            ),
            "",
            t("card.sender_text_start", lang),
            card.defanged_text.strip(),
            t("card.sender_text_end", lang),
            "",
            t("card.decisions_title", lang),
            f"  [1] {t('card.action.is_fraud', lang)}",
            f"  [2] {legitimate}",
            f"  [3] {t('card.action.not_sure', lang)}",
        ]
    )


def resolve(
    card: ReviewCard,
    action: str,
    reviewer: str,
    *,
    label: str | None = None,
    labels: Iterable[str] = LEAD_LABELS,
    second_reviewer: str | None = None,
) -> Resolution:
    """Apply the decision of the person who reviews. The rules are here, in code.

    - ``is_fraud``: the message does not go on.
    - ``not_sure``: it stays in quarantine so another person sees it.
    - ``is_legitimate``: the person must choose the label from the list; the message does not
      go back to the model. If the card requires it, a second, different person is needed.

    The notes and the errors are in the language of the card.
    """
    lang = card.lang
    if action not in ACTIONS:
        raise ValueError(t("error.invalid_action", lang, actions=ACTIONS))
    if not reviewer.strip():
        raise ValueError(t("error.reviewer_missing", lang))
    if action == "is_fraud":
        return Resolution("blocked", None, (reviewer,), t("resolution.blocked", lang))
    if action == "not_sure":
        return Resolution("escalated", None, (reviewer,), t("resolution.escalated", lang))

    if label not in set(labels):
        raise ValueError(t("error.label_required", lang))
    if card.needs_second_person:
        if not second_reviewer or second_reviewer.strip().casefold() == reviewer.strip().casefold():
            return Resolution(
                "awaiting_second_person",
                None,
                (reviewer,),
                t("resolution.awaiting_second_person", lang),
            )
        return Resolution(
            "released", label, (reviewer, second_reviewer), t("resolution.released_two", lang)
        )
    return Resolution("released", label, (reviewer,), t("resolution.released_one", lang))

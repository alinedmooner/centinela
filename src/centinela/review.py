"""Sala de revisión: qué ve y qué puede hacer la persona que revisa un mensaje sospechoso.

La persona que revisa también puede ser engañada por el mensaje. Por eso la sala la trata
igual que al bot:

1. **El mensaje llega desarmado.** Los enlaces, los correos, los teléfonos y los números
   de cuenta se muestran desactivados: se pueden leer, pero no abrir ni copiar tal cual.
2. **Una tarjeta separa lo que el mensaje dice de lo que pide.** La arma el código: quién
   dice ser el remitente, qué pide hacer y con qué presiona.
3. **Las decisiones están acotadas.** Solo hay tres, y ninguna hace lo que pide el
   mensaje. Un mensaje liberado no vuelve al modelo: la etiqueta la pone la persona.

Todo funciona sin clave ni internet. Las pistas de la tarjeta son reglas sencillas: sirven
para orientar a quien revisa, no para decidir por esa persona.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from centinela.detectors.rules import _strip_accents
from centinela.labels import LEAD_LABELS
from centinela.verdict import Verdict

Action = Literal["es_fraude", "es_legitimo", "no_estoy_seguro"]
ACTIONS: tuple[Action, ...] = ("es_fraude", "es_legitimo", "no_estoy_seguro")

_TLD = (
    "com|net|org|info|biz|co|io|app|dev|xyz|top|online|site|shop|store|link|click|live|club|vip"
    "|icu|me|tv|cc|ly|gl|es|mx|ar|cl|pe|ec|ve|uy|py|bo|br|us|uk|de|fr|it|ru|cn|edu|gov|gob|example"
)
_EMAIL = re.compile(r"\b[\w.%+-]+@[\w-]+(?:\.[\w-]+)+\b")
_URL = re.compile(r"(?i)(?:[a-z][a-z0-9+-]{1,12}://|\bwww\.)[^\s<>\"'\])]+")
# La terminación va en minúsculas: «compra.Es un gusto» es un punto sin espacio, no un dominio.
_DOMAIN = re.compile(rf"(?<![\w@\[/.])(?:[\w-]+\.)+(?:{_TLD})\b(?:/[^\s<>\"'\])]*)?")
_NUMBER = re.compile(r"(?<![\w$.,/-])\+?\d(?:[ ()-]{0,2}\d){6,18}(?![\w%/])")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}")
#: Caracteres que no se ven o que cambian el orden en que se lee el texto.
_INVISIBLE = re.compile(
    "["
    + "".join(chr(c) for c in (0x00AD, 0x061C, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F))
    + "".join(chr(c) for c in (0x2060, 0xFEFF))
    + f"{chr(0x202A)}-{chr(0x202E)}{chr(0x2066)}-{chr(0x2069)}"
    + "]"
)
_BREAKS = re.compile(r"\n\s*\n(\s*\n)+")

#: Lo que el mensaje pide hacer. Se busca sobre texto en minúsculas y sin tildes.
_ASKS: dict[str, re.Pattern[str]] = {
    "entrar a un enlace": re.compile(
        r"\b(haga|haz|hagan|hacer|dar|den|dele) (clic|click)\b"
        r"|\b(ingres\w+|entr\w+|acced\w+|visit\w+) (a|al|en|aqui)\b"
        r"|\b(abr\w+|sigu\w+|puls\w+|presion\w+) (el|este|en el|en este|el siguiente) (enlace|link|boton|vinculo)\b"
    ),
    "dar una clave o datos personales": re.compile(
        r"\b(confirm\w+|verifi\w+|actuali[cz]\w+|ingres\w+|envi\w+|proporcion\w+|compart\w+|digit\w+|valid\w+)\b"
        r"[^.\n]{0,50}\b(clave|contrasena|usuario|datos|tarjeta|cvv|pin|codigo|token|cedula|documento)\b"
    ),
    "pagar o transferir dinero": re.compile(
        r"\b(pague|paguen|paga|pagar|transfiera|transfieran|transfiere|transferir|consigne|consignar"
        r"|deposite|depositar|gire|girar|abone|abonar)\b"
        r"|\b(realice|realiza|efectue|efectua|haga|haz) (el|su|tu|un) (pago|deposito|giro)\b"
        r"|\b(haga|haz|realice|realiza) (la|una|su|tu) (transferencia|consignacion)\b"
    ),
    "descargar o abrir un archivo": re.compile(
        r"\b(descarg\w+|instal\w+)\b"
        r"|\b(abr\w+|revis\w+)\b[^.\n]{0,25}\b(archivo|adjunto|pdf)\b"
    ),
    "llamar o escribir a un contacto": re.compile(
        r"\b(llam\w+|comuniqu\w+|comunicate|escrib\w+|contact\w+)\b[^.\n]{0,30}"
        r"\b(al|a este|a nuestro|numero|telefono|whatsapp)\b"
    ),
}
#: Pedidos por los que liberar el mensaje exige una segunda persona.
SENSITIVE_ASKS = frozenset({"dar una clave o datos personales", "pagar o transferir dinero"})

_PRESSURE: dict[str, re.Pattern[str]] = {
    "urgencia": re.compile(
        r"\b(urgente|urge|inmediatamente|de inmediato|ahora mismo|hoy mismo|cuanto antes"
        r"|ultim[oa]s? (aviso|oportunidad|dia|horas?)|en (las proximas )?\d+ (horas|minutos|dias))\b"
    ),
    "amenaza": re.compile(
        r"\b(suspend\w+|bloque\w+|cancelad\w+|cancelacion|cierre de|multa\w*|embarg\w+|demanda\w*"
        r"|penaliz\w+|inhabilit\w+|desactiv\w+|perdera|perderas)\b"
    ),
    "premio u oferta": re.compile(
        r"\b(gano|ganaste|ganador\w*|premio\w*|bono\w*|gratis|sorteo\w*|regalo\w*|felicidades"
        r"|felicitaciones|reembolso\w*)\b"
    ),
}
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
    """Lo que ve la persona que revisa un mensaje en cuarentena."""

    notice: str
    claims_to_be: tuple[str, ...]
    asks: tuple[str, ...]
    pressure: tuple[str, ...]
    #: Enlaces y correos que trae el mensaje, ya desactivados.
    links: tuple[str, ...]
    #: El mensaje completo, con enlaces, correos y números desactivados.
    defanged_text: str
    actions: tuple[Action, ...] = ACTIONS
    #: Liberar este mensaje exige dos personas distintas.
    needs_second_person: bool = False
    #: Dominios a los que llevan los enlaces pero que no aparecen escritos en el texto
    #: (por ejemplo, el destino real de un botón en un correo HTML).
    hidden_destinations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resolution:
    """Lo que pasa con un mensaje después de que alguien lo revisa."""

    state: Literal["bloqueado", "liberado", "espera_segunda_persona", "escalado"]
    #: Solo si quedó liberado. La pone una persona, no el modelo.
    label: str | None
    reviewers: tuple[str, ...]
    note: str


def _break(text: str) -> str:
    return text.replace(".", "[.]")


def _visible(domain: str) -> str:
    """Un dominio con letras de otros alfabetos puede imitar a otro: se muestra su forma real."""
    if domain.isascii():
        return domain
    try:
        real = domain.replace("[.]", ".").encode("idna").decode("ascii")
    except UnicodeError:
        real = domain.replace("[.]", ".").encode("ascii", "backslashreplace").decode("ascii")
    return f"{_break(real)} (se ve como «{domain}»)"


def _disable(link: str) -> tuple[str, str]:
    """Devuelve el enlace desactivado y su dominio, sin ruta, usuario ni puerto."""
    broken = _break(re.sub(r"(?i)http(s?)://", r"hxxp\1://", link))
    domain = broken.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return broken, _visible(domain.split("@")[-1].split(":")[0])


_CORTES = re.compile(r"\s+(?:y|e|que|para|porque|pero|quien|con el fin)\s+")
_DANGLING = frozenset({"de", "del", "la", "el", "los", "las", "su", "tu", "en", "a", "con", "y"})


def _who(sentence: str) -> str:
    """Recorta lo que sigue a «soy…» o «le escribe…» hasta dejar un nombre corto."""
    words = _CORTES.split(sentence, maxsplit=1)[0].split()[:8]
    while words and words[-1].lower() in _DANGLING:
        words.pop()
    return " ".join(words)


def defang(text: str) -> tuple[str, tuple[str, ...]]:
    """Desactiva enlaces, correos, teléfonos y números de cuenta.

    Devuelve el texto desarmado y la lista de enlaces y correos que traía, ya desactivados.
    """
    #: Pares (cómo quedó en el texto, cómo se muestra en la lista de la tarjeta).
    found: list[tuple[str, str]] = []

    def mail(m: re.Match[str]) -> str:
        user, domain = m.group(0).rsplit("@", 1)
        broken = f"{_break(user)}[@]{_break(domain)}"
        found.append((broken, f"{_break(user)}[@]{_visible(_break(domain))}"))
        return broken

    def link(m: re.Match[str]) -> str:
        body = m.group(0).rstrip(".,;:!?")
        broken, domain = _disable(body)
        found.append((broken, domain))
        return broken + m.group(0)[len(body) :]

    def number(m: re.Match[str]) -> str:
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if _DATE.fullmatch(raw.strip()) or len(digits) < 7:
            return raw
        return f"[número oculto, termina en {digits[-2:]}]"

    clean = "".join(c for c in text if not 0xE0000 <= ord(c) <= 0xE007F)
    clean = _INVISIBLE.sub("", clean)
    clean = _BREAKS.sub("\n\n", clean)
    clean = _URL.sub(link, clean)
    clean = _EMAIL.sub(mail, clean)
    clean = _DOMAIN.sub(link, clean)
    clean = _NUMBER.sub(number, clean)
    plain = clean.lower()
    in_order = sorted(found, key=lambda par: plain.find(par[0].lower()))
    return clean, tuple(dict.fromkeys(shown.lower() for _, shown in in_order if shown))


def create_card(text: str, verdict: Verdict, *, hidden_links: Iterable[str] = ()) -> ReviewCard:
    """Arma la tarjeta de revisión de un mensaje a partir del veredicto del guardia.

    ``enlaces_ocultos`` son destinos que no se ven en el texto, como los ``href`` de un
    correo en HTML. La tarjeta los muestra, desactivados, junto a los del texto.
    """
    defanged, links = defang(text)
    hidden_items = [_disable(e.strip())[1].lower() for e in hidden_links if e.strip()]
    hidden_destinations = tuple(d for d in dict.fromkeys(hidden_items) if d not in links)
    links = tuple(dict.fromkeys((*links, *hidden_items)))
    plain = _strip_accents(text.lower())

    asks = [name for name, patron in _ASKS.items() if patron.search(plain)]
    if verdict.ai_instructions:
        asks.insert(0, "darle órdenes al asistente de IA")
    presses = [name for name, patron in _PRESSURE.items() if patron.search(plain)]

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
    )


def render_card(card: ReviewCard) -> str:
    """La tarjeta como texto, lista para mostrar en una terminal o en un chat interno."""

    def joined(values: tuple[str, ...], empty: str) -> str:
        return "; ".join(values) if values else empty

    legitimate = "Es legítimo"
    if card.needs_second_person:
        legitimate += " · requiere una segunda persona"
    return "\n".join(
        [
            "REVISIÓN HUMANA · mensaje en cuarentena",
            f"Aviso:        {card.notice}",
            f"Dice ser:     {joined(card.claims_to_be, 'no lo dice')}",
            f"Pide:         {joined(card.asks, 'nada que las reglas reconozcan')}",
            f"Presiona con: {joined(card.pressure, 'nada que las reglas reconozcan')}",
            f"Enlaces y correos (desactivados): {joined(card.links, 'ninguno')}",
            *(
                [f"¡Ojo! Enlaces que llevan a otro dominio: {joined(card.hidden_destinations, '')}"]
                if card.hidden_destinations
                else []
            ),
            "",
            "--- Texto del remitente (no confiable) ---",
            card.defanged_text.strip(),
            "--- Fin del texto del remitente ---",
            "",
            "Decisiones posibles (ninguna hace lo que pide el mensaje):",
            "  [1] Es fraude",
            f"  [2] {legitimate}",
            "  [3] No estoy seguro",
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
    """Aplica la decisión de quien revisa. Las reglas están aquí, en código.

    - ``es_fraude``: el mensaje no sigue.
    - ``no_estoy_seguro``: sigue en cuarentena para que lo vea otra persona.
    - ``es_legitimo``: la persona debe elegir la etiqueta de la lista; el mensaje no vuelve
      al modelo. Si la tarjeta lo exige, hace falta una segunda persona distinta.
    """
    if action not in ACTIONS:
        raise ValueError(f"La decisión debe ser una de {ACTIONS}.")
    if not reviewer.strip():
        raise ValueError("Falta el nombre de quien revisa.")
    if action == "es_fraude":
        return Resolution("bloqueado", None, (reviewer,), "El mensaje no sigue y queda registrado.")
    if action == "no_estoy_seguro":
        return Resolution("escalado", None, (reviewer,), "Sigue en cuarentena para otra persona.")

    if label not in set(labels):
        raise ValueError("Para liberar un mensaje hay que elegir una etiqueta de la lista.")
    if card.needs_second_person:
        if not second_reviewer or second_reviewer.strip().casefold() == reviewer.strip().casefold():
            return Resolution(
                "espera_segunda_persona",
                None,
                (reviewer,),
                "Falta que una segunda persona, distinta, confirme que es legítimo.",
            )
        return Resolution(
            "liberado", label, (reviewer, second_reviewer), "Liberado por dos personas."
        )
    return Resolution("liberado", label, (reviewer,), "Liberado por una persona.")

"""Leer correos para revisarlos con Centinela, sin dependencias externas.

Un correo trae más de lo que se ve. El HTML puede esconder texto, por ejemplo órdenes para un
asistente de IA en un párrafo invisible, y un enlace puede llevar a un dominio distinto del que
muestra. Este módulo extrae:

- el texto que leería un asistente, con el texto oculto incluido y marcado como tal;
- los destinos reales de los enlaces del HTML, para mostrarlos en la tarjeta de revisión;
- los nombres de los adjuntos.

Uso::

    from centinela import revisar
    from centinela.correo import leer_correo, texto_a_revisar

    correo = leer_correo(open("mensaje.eml", "rb").read())
    veredicto = revisar(texto_a_revisar(correo))
"""

from __future__ import annotations

import email
import re
from dataclasses import dataclass
from email import policy
from email.message import Message
from html.parser import HTMLParser

MAX_CHARS = 8000

_EMPTY = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)
_BLOCKS = frozenset(
    {"p", "div", "br", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
)
_IGNORE = frozenset({"script", "style", "head", "title", "template"})
#: Estilos que esconden texto a una persona, aunque un asistente de IA sí lo lea.
_HIDDEN = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d]*[1-9])"
    r"|opacity\s*:\s*0(?:\.0+)?(?![.\d])|max-height\s*:\s*0(?![.\d]*[1-9])|mso-hide\s*:\s*all",
    re.IGNORECASE,
)
_WEB = re.compile(r"(?i)^(?:https?://|www\.)")


@dataclass(frozen=True)
class Mail:
    sender: str
    subject: str
    #: Lo que leería un asistente: el texto del correo y, marcado, el texto oculto del HTML.
    text: str
    #: Destinos de los enlaces del HTML (solo web), que pueden no coincidir con lo que se ve.
    links: tuple[str, ...]
    attachments: tuple[str, ...]
    #: Cuántos fragmentos de texto oculto traía el HTML.
    hidden_fragments: int = 0


class _HTMLReader(HTMLParser):
    """Separa el texto visible del oculto y recoge los destinos de los enlaces."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[tuple[str, bool]] = []
        self.links: list[str] = []
        self._stack: list[tuple[str, bool]] = []
        self._ignore = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORE:
            self._ignore += 1
            return
        attributes = {k: v or "" for k, v in attrs}
        if tag == "a" and _WEB.match(attributes.get("href", "").strip()):
            self.links.append(attributes["href"].strip())
        if tag in _BLOCKS:
            self.parts.append(("\n", False))
        if tag in _EMPTY:
            return
        hidden = "hidden" in attributes or bool(_HIDDEN.search(attributes.get("style", "")))
        self._stack.append((tag, hidden))

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORE:
            self._ignore = max(0, self._ignore - 1)
            return
        for i in range(len(self._stack) - 1, -1, -1):  # tolera HTML mal cerrado
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if tag in _BLOCKS:
            self.parts.append(("\n", False))

    def handle_data(self, data: str) -> None:
        if not self._ignore:
            self.parts.append((data, any(hidden for _, hidden in self._stack)))

    def result(self) -> tuple[str, list[str]]:
        """Devuelve el texto visible y la lista de fragmentos ocultos."""
        visible = _clean("".join(t for t, hidden in self.parts if not hidden))
        # Los fragmentos ocultos seguidos (separados solo por espacios) forman uno solo.
        hidden_items: list[str] = []
        actual: list[str] = []
        for t, hidden in [*self.parts, ("fin", False)]:
            if hidden:
                actual.append(t)
            elif actual and t.strip():
                fragment = _clean(" ".join(actual)).replace("\n", " ")
                if fragment:
                    hidden_items.append(fragment)
                actual = []
        return visible, hidden_items


def _clean(text: str) -> str:
    text = re.sub("[ \t\r\f\v ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _content(part: Message | None) -> str:
    if part is None:
        return ""
    try:
        return part.get_content()
    except (LookupError, UnicodeDecodeError, AssertionError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", text.lower()))


def read_mail(raw: bytes | str | Message) -> Mail:
    """Lee un correo (bytes de un .eml o de IMAP, texto, o un ``Message`` ya leído)."""
    if isinstance(raw, Message):
        message = raw
    elif isinstance(raw, bytes):
        message = email.message_from_bytes(raw, policy=policy.default)
    else:
        message = email.message_from_string(raw, policy=policy.default)

    plain = _clean(_content(message.get_body(preferencelist=("plain",))))
    html = _content(message.get_body(preferencelist=("html",)))
    reader = _HTMLReader()
    if html:
        reader.feed(html)
        reader.close()
    visible_html, hidden_items = reader.result()

    text = plain or visible_html
    # La versión HTML puede decir otra cosa que la de texto plano: un asistente podría leer
    # cualquiera de las dos, así que se revisan ambas.
    if plain and visible_html:
        new_ones = _words(visible_html) - _words(plain)
        if len(new_ones) > 0.2 * max(1, len(_words(visible_html))):
            text += f"\n\n[versión HTML del correo, distinta del texto: {visible_html}]"
    for fragment in hidden_items:
        text += f"\n\n[texto oculto en el HTML: {fragment}]"

    attachments = (
        tuple(p.get_filename() for p in message.iter_attachments() if p.get_filename())
        if message.is_multipart()
        else ()
    )
    return Mail(
        sender=str(message.get("From", "")),
        subject=str(message.get("Subject", "")),
        text=text,
        links=tuple(dict.fromkeys(reader.links)),
        attachments=attachments,
        hidden_fragments=len(hidden_items),
    )


def text_to_check(mail: Mail, maximum: int = MAX_CHARS) -> str:
    """El texto que se le pasa al guardia: remitente, asunto, cuerpo y adjuntos."""
    parts = [f"De: {mail.sender}", f"Asunto: {mail.subject}", "", mail.text]
    if mail.attachments:
        parts += ["", "Adjuntos: " + ", ".join(mail.attachments)]
    return "\n".join(parts)[:maximum]

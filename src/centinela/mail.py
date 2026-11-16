"""Reads emails so Centinela can check them, without external dependencies.

An email carries more than what is visible. The HTML can hide text, for example instructions
for an AI assistant in an invisible paragraph, and a link can point to a different domain than
the one it shows. This module extracts:

- the text an assistant would read, with the hidden text included and marked as such;
- the real destinations of the links in the HTML, to show them on the review card;
- the names of the attachments.

Usage::

    from centinela import check
    from centinela.mail import read_mail, text_to_check

    mail = read_mail(open("message.eml", "rb").read())
    verdict = check(text_to_check(mail))
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
#: Styles that hide text from a person, even though an AI assistant does read it.
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
    #: What an assistant would read: the email text plus, marked as such, the hidden HTML text.
    text: str
    #: Destinations of the links in the HTML (web links only), which may not match what is shown.
    links: tuple[str, ...]
    attachments: tuple[str, ...]
    #: How many fragments of hidden text the HTML contained.
    hidden_fragments: int = 0


class _HTMLReader(HTMLParser):
    """Separates the visible text from the hidden text and collects the link destinations."""

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
        for i in range(len(self._stack) - 1, -1, -1):  # tolerates badly closed HTML
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if tag in _BLOCKS:
            self.parts.append(("\n", False))

    def handle_data(self, data: str) -> None:
        if not self._ignore:
            self.parts.append((data, any(hidden for _, hidden in self._stack)))

    def result(self) -> tuple[str, list[str]]:
        """Returns the visible text and the list of hidden fragments."""
        visible = _clean("".join(t for t, hidden in self.parts if not hidden))
        # Consecutive hidden fragments (separated only by whitespace) form a single one.
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
    """Reads an email (bytes from an .eml file or IMAP, text, or an already parsed ``Message``).

    The notes it adds to the text (for hidden text and for a different HTML version) are in
    Spanish on purpose: the model sees them.
    """
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
    # The HTML version can say something different from the plain-text one: an assistant could
    # read either of the two, so both are checked.
    if plain and visible_html:
        new_words = _words(visible_html) - _words(plain)
        if len(new_words) > 0.2 * max(1, len(_words(visible_html))):
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
    """The text passed to the guard: sender, subject, body and attachments.

    The labels ``De:``, ``Asunto:`` and ``Adjuntos:`` are Spanish on purpose: the model sees them.
    """
    parts = [f"De: {mail.sender}", f"Asunto: {mail.subject}", "", mail.text]
    if mail.attachments:
        parts += ["", "Adjuntos: " + ", ".join(mail.attachments)]
    return "\n".join(parts)[:maximum]

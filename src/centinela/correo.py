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

MAX_CARACTERES = 8000

_VACIOS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)
_BLOQUES = frozenset(
    {"p", "div", "br", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
)
_IGNORAR = frozenset({"script", "style", "head", "title", "template"})
#: Estilos que esconden texto a una persona, aunque un asistente de IA sí lo lea.
_OCULTO = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d]*[1-9])"
    r"|opacity\s*:\s*0(?:\.0+)?(?![.\d])|max-height\s*:\s*0(?![.\d]*[1-9])|mso-hide\s*:\s*all",
    re.IGNORECASE,
)
_WEB = re.compile(r"(?i)^(?:https?://|www\.)")


@dataclass(frozen=True)
class Correo:
    remitente: str
    asunto: str
    #: Lo que leería un asistente: el texto del correo y, marcado, el texto oculto del HTML.
    texto: str
    #: Destinos de los enlaces del HTML (solo web), que pueden no coincidir con lo que se ve.
    enlaces: tuple[str, ...]
    adjuntos: tuple[str, ...]
    #: Cuántos fragmentos de texto oculto traía el HTML.
    fragmentos_ocultos: int = 0


class _LectorHTML(HTMLParser):
    """Separa el texto visible del oculto y recoge los destinos de los enlaces."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[tuple[str, bool]] = []
        self.enlaces: list[str] = []
        self._pila: list[tuple[str, bool]] = []
        self._ignorar = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORAR:
            self._ignorar += 1
            return
        atributos = {k: v or "" for k, v in attrs}
        if tag == "a" and _WEB.match(atributos.get("href", "").strip()):
            self.enlaces.append(atributos["href"].strip())
        if tag in _BLOQUES:
            self.partes.append(("\n", False))
        if tag in _VACIOS:
            return
        oculto = "hidden" in atributos or bool(_OCULTO.search(atributos.get("style", "")))
        self._pila.append((tag, oculto))

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORAR:
            self._ignorar = max(0, self._ignorar - 1)
            return
        for i in range(len(self._pila) - 1, -1, -1):  # tolera HTML mal cerrado
            if self._pila[i][0] == tag:
                del self._pila[i:]
                break
        if tag in _BLOQUES:
            self.partes.append(("\n", False))

    def handle_data(self, data: str) -> None:
        if not self._ignorar:
            self.partes.append((data, any(oculto for _, oculto in self._pila)))

    def resultado(self) -> tuple[str, list[str]]:
        """Devuelve el texto visible y la lista de fragmentos ocultos."""
        visible = _limpiar("".join(t for t, oculto in self.partes if not oculto))
        # Los fragmentos ocultos seguidos (separados solo por espacios) forman uno solo.
        ocultos: list[str] = []
        actual: list[str] = []
        for t, oculto in [*self.partes, ("fin", False)]:
            if oculto:
                actual.append(t)
            elif actual and t.strip():
                fragmento = _limpiar(" ".join(actual)).replace("\n", " ")
                if fragmento:
                    ocultos.append(fragmento)
                actual = []
        return visible, ocultos


def _limpiar(texto: str) -> str:
    texto = re.sub("[ \t\r\f\v ]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _contenido(parte: Message | None) -> str:
    if parte is None:
        return ""
    try:
        return parte.get_content()
    except (LookupError, UnicodeDecodeError, AssertionError):
        carga = parte.get_payload(decode=True) or b""
        return carga.decode("utf-8", errors="replace")


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"\w{3,}", texto.lower()))


def leer_correo(crudo: bytes | str | Message) -> Correo:
    """Lee un correo (bytes de un .eml o de IMAP, texto, o un ``Message`` ya leído)."""
    if isinstance(crudo, Message):
        mensaje = crudo
    elif isinstance(crudo, bytes):
        mensaje = email.message_from_bytes(crudo, policy=policy.default)
    else:
        mensaje = email.message_from_string(crudo, policy=policy.default)

    plano = _limpiar(_contenido(mensaje.get_body(preferencelist=("plain",))))
    html = _contenido(mensaje.get_body(preferencelist=("html",)))
    lector = _LectorHTML()
    if html:
        lector.feed(html)
        lector.close()
    visible_html, ocultos = lector.resultado()

    texto = plano or visible_html
    # La versión HTML puede decir otra cosa que la de texto plano: un asistente podría leer
    # cualquiera de las dos, así que se revisan ambas.
    if plano and visible_html:
        nuevas = _palabras(visible_html) - _palabras(plano)
        if len(nuevas) > 0.2 * max(1, len(_palabras(visible_html))):
            texto += f"\n\n[versión HTML del correo, distinta del texto: {visible_html}]"
    for fragmento in ocultos:
        texto += f"\n\n[texto oculto en el HTML: {fragmento}]"

    adjuntos = (
        tuple(p.get_filename() for p in mensaje.iter_attachments() if p.get_filename())
        if mensaje.is_multipart()
        else ()
    )
    return Correo(
        remitente=str(mensaje.get("From", "")),
        asunto=str(mensaje.get("Subject", "")),
        texto=texto,
        enlaces=tuple(dict.fromkeys(lector.enlaces)),
        adjuntos=adjuntos,
        fragmentos_ocultos=len(ocultos),
    )


def texto_a_revisar(correo: Correo, maximo: int = MAX_CARACTERES) -> str:
    """El texto que se le pasa al guardia: remitente, asunto, cuerpo y adjuntos."""
    partes = [f"De: {correo.remitente}", f"Asunto: {correo.asunto}", "", correo.texto]
    if correo.adjuntos:
        partes += ["", "Adjuntos: " + ", ".join(correo.adjuntos)]
    return "\n".join(partes)[:maximo]

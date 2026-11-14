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

from centinela.detectores.reglas import _sin_tildes
from centinela.etiquetas import ETIQUETAS_LEADS
from centinela.tipos import Veredicto

Accion = Literal["es_fraude", "es_legitimo", "no_estoy_seguro"]
ACCIONES: tuple[Accion, ...] = ("es_fraude", "es_legitimo", "no_estoy_seguro")

_TLD = (
    "com|net|org|info|biz|co|io|app|dev|xyz|top|online|site|shop|store|link|click|live|club|vip"
    "|icu|me|tv|cc|ly|gl|es|mx|ar|cl|pe|ec|ve|uy|py|bo|br|us|uk|de|fr|it|ru|cn|edu|gov|gob|example"
)
_CORREO = re.compile(r"\b[\w.%+-]+@[\w-]+(?:\.[\w-]+)+\b")
_URL = re.compile(r"(?i)(?:[a-z][a-z0-9+-]{1,12}://|\bwww\.)[^\s<>\"'\])]+")
# La terminación va en minúsculas: «compra.Es un gusto» es un punto sin espacio, no un dominio.
_DOMINIO = re.compile(rf"(?<![\w@\[/.])(?:[\w-]+\.)+(?:{_TLD})\b(?:/[^\s<>\"'\])]*)?")
_NUMERO = re.compile(r"(?<![\w$.,/-])\+?\d(?:[ ()-]{0,2}\d){6,18}(?![\w%/])")
_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}")
#: Caracteres que no se ven o que cambian el orden en que se lee el texto.
_INVISIBLES = re.compile(
    "["
    + "".join(chr(c) for c in (0x00AD, 0x061C, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F))
    + "".join(chr(c) for c in (0x2060, 0xFEFF))
    + f"{chr(0x202A)}-{chr(0x202E)}{chr(0x2066)}-{chr(0x2069)}"
    + "]"
)
_SALTOS = re.compile(r"\n\s*\n(\s*\n)+")

#: Lo que el mensaje pide hacer. Se busca sobre texto en minúsculas y sin tildes.
_PIDE: dict[str, re.Pattern[str]] = {
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
PEDIDOS_DELICADOS = frozenset({"dar una clave o datos personales", "pagar o transferir dinero"})

_PRESIONA: dict[str, re.Pattern[str]] = {
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
_DICE_SER = re.compile(
    r"(?i)\b(?:soy|somos|le habla|le escribe|te escribe|le saluda|de parte de)\s+"
    r"((?:el |la |los |las |del |de la |tu |su )?[^.,;:\n]{3,60})"
)
_INSTITUCION = re.compile(
    r"\b(su banco|tu banco|banco \w+|soporte tecnico|equipo de seguridad|departamento de \w+"
    r"|area de \w+|gerencia|recursos humanos|servicio al cliente)\b"
)


@dataclass(frozen=True)
class TarjetaRevision:
    """Lo que ve la persona que revisa un mensaje en cuarentena."""

    aviso: str
    dice_ser: tuple[str, ...]
    pide: tuple[str, ...]
    presiona_con: tuple[str, ...]
    #: Enlaces y correos que trae el mensaje, ya desactivados.
    enlaces: tuple[str, ...]
    #: El mensaje completo, con enlaces, correos y números desactivados.
    texto_desarmado: str
    acciones: tuple[Accion, ...] = ACCIONES
    #: Liberar este mensaje exige dos personas distintas.
    requiere_segunda_persona: bool = False


@dataclass(frozen=True)
class Resolucion:
    """Lo que pasa con un mensaje después de que alguien lo revisa."""

    estado: Literal["bloqueado", "liberado", "espera_segunda_persona", "escalado"]
    #: Solo si quedó liberado. La pone una persona, no el modelo.
    etiqueta: str | None
    revisores: tuple[str, ...]
    nota: str


def _romper(texto: str) -> str:
    return texto.replace(".", "[.]")


def _visible(dominio: str) -> str:
    """Un dominio con letras de otros alfabetos puede imitar a otro: se muestra su forma real."""
    if dominio.isascii():
        return dominio
    try:
        real = dominio.replace("[.]", ".").encode("idna").decode("ascii")
    except UnicodeError:
        real = dominio.replace("[.]", ".").encode("ascii", "backslashreplace").decode("ascii")
    return f"{_romper(real)} (se ve como «{dominio}»)"


def _desactivar(enlace: str) -> tuple[str, str]:
    """Devuelve el enlace desactivado y su dominio, sin ruta, usuario ni puerto."""
    roto = _romper(re.sub(r"(?i)http(s?)://", r"hxxp\1://", enlace))
    dominio = roto.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return roto, _visible(dominio.split("@")[-1].split(":")[0])


_CORTES = re.compile(r"\s+(?:y|e|que|para|porque|pero|quien|con el fin)\s+")
_COLGANTES = frozenset({"de", "del", "la", "el", "los", "las", "su", "tu", "en", "a", "con", "y"})


def _quien(frase: str) -> str:
    """Recorta lo que sigue a «soy…» o «le escribe…» hasta dejar un nombre corto."""
    palabras = _CORTES.split(frase, maxsplit=1)[0].split()[:8]
    while palabras and palabras[-1].lower() in _COLGANTES:
        palabras.pop()
    return " ".join(palabras)


def desarmar(texto: str) -> tuple[str, tuple[str, ...]]:
    """Desactiva enlaces, correos, teléfonos y números de cuenta.

    Devuelve el texto desarmado y la lista de enlaces y correos que traía, ya desactivados.
    """
    #: Pares (cómo quedó en el texto, cómo se muestra en la lista de la tarjeta).
    encontrados: list[tuple[str, str]] = []

    def correo(m: re.Match[str]) -> str:
        usuario, dominio = m.group(0).rsplit("@", 1)
        roto = f"{_romper(usuario)}[@]{_romper(dominio)}"
        encontrados.append((roto, f"{_romper(usuario)}[@]{_visible(_romper(dominio))}"))
        return roto

    def enlace(m: re.Match[str]) -> str:
        cuerpo = m.group(0).rstrip(".,;:!?")
        roto, dominio = _desactivar(cuerpo)
        encontrados.append((roto, dominio))
        return roto + m.group(0)[len(cuerpo) :]

    def numero(m: re.Match[str]) -> str:
        crudo = m.group(0)
        digitos = re.sub(r"\D", "", crudo)
        if _FECHA.fullmatch(crudo.strip()) or len(digitos) < 7:
            return crudo
        return f"[número oculto, termina en {digitos[-2:]}]"

    limpio = "".join(c for c in texto if not 0xE0000 <= ord(c) <= 0xE007F)
    limpio = _INVISIBLES.sub("", limpio)
    limpio = _SALTOS.sub("\n\n", limpio)
    limpio = _URL.sub(enlace, limpio)
    limpio = _CORREO.sub(correo, limpio)
    limpio = _DOMINIO.sub(enlace, limpio)
    limpio = _NUMERO.sub(numero, limpio)
    plano = limpio.lower()
    en_orden = sorted(encontrados, key=lambda par: plano.find(par[0].lower()))
    return limpio, tuple(dict.fromkeys(mostrado.lower() for _, mostrado in en_orden if mostrado))


def crear_tarjeta(
    texto: str, veredicto: Veredicto, *, enlaces_ocultos: Iterable[str] = ()
) -> TarjetaRevision:
    """Arma la tarjeta de revisión de un mensaje a partir del veredicto del guardia.

    ``enlaces_ocultos`` son destinos que no se ven en el texto, como los ``href`` de un
    correo en HTML. La tarjeta los muestra, desactivados, junto a los del texto.
    """
    desarmado, enlaces = desarmar(texto)
    ocultos = [_desactivar(e.strip())[1].lower() for e in enlaces_ocultos if e.strip()]
    enlaces = tuple(dict.fromkeys((*enlaces, *ocultos)))
    plano = _sin_tildes(texto.lower())

    pide = [nombre for nombre, patron in _PIDE.items() if patron.search(plano)]
    if veredicto.ordenes_para_ia:
        pide.insert(0, "darle órdenes al asistente de IA")
    presiona = [nombre for nombre, patron in _PRESIONA.items() if patron.search(plano)]

    dice_ser = [q for q in (_quien(m.group(1)) for m in _DICE_SER.finditer(desarmado)) if q]
    for m in _INSTITUCION.finditer(plano):
        if not any(m.group(1) in _sin_tildes(q.lower()) for q in dice_ser):
            dice_ser.append(m.group(1))

    return TarjetaRevision(
        aviso=veredicto.aviso,
        dice_ser=tuple(dict.fromkeys(dice_ser))[:3],
        pide=tuple(pide),
        presiona_con=tuple(presiona),
        enlaces=enlaces,
        texto_desarmado=desarmado,
        requiere_segunda_persona=veredicto.engano_a_personas
        or any(p in PEDIDOS_DELICADOS for p in pide),
    )


def texto_de_tarjeta(tarjeta: TarjetaRevision) -> str:
    """La tarjeta como texto, lista para mostrar en una terminal o en un chat interno."""

    def lista(valores: tuple[str, ...], vacio: str) -> str:
        return "; ".join(valores) if valores else vacio

    legitimo = "Es legítimo"
    if tarjeta.requiere_segunda_persona:
        legitimo += " · requiere una segunda persona"
    return "\n".join(
        [
            "REVISIÓN HUMANA · mensaje en cuarentena",
            f"Aviso:        {tarjeta.aviso}",
            f"Dice ser:     {lista(tarjeta.dice_ser, 'no lo dice')}",
            f"Pide:         {lista(tarjeta.pide, 'nada que las reglas reconozcan')}",
            f"Presiona con: {lista(tarjeta.presiona_con, 'nada que las reglas reconozcan')}",
            f"Enlaces y correos (desactivados): {lista(tarjeta.enlaces, 'ninguno')}",
            "",
            "--- Texto del remitente (no confiable) ---",
            tarjeta.texto_desarmado.strip(),
            "--- Fin del texto del remitente ---",
            "",
            "Decisiones posibles (ninguna hace lo que pide el mensaje):",
            "  [1] Es fraude",
            f"  [2] {legitimo}",
            "  [3] No estoy seguro",
        ]
    )


def resolver(
    tarjeta: TarjetaRevision,
    accion: str,
    revisor: str,
    *,
    etiqueta: str | None = None,
    etiquetas: Iterable[str] = ETIQUETAS_LEADS,
    segundo_revisor: str | None = None,
) -> Resolucion:
    """Aplica la decisión de quien revisa. Las reglas están aquí, en código.

    - ``es_fraude``: el mensaje no sigue.
    - ``no_estoy_seguro``: sigue en cuarentena para que lo vea otra persona.
    - ``es_legitimo``: la persona debe elegir la etiqueta de la lista; el mensaje no vuelve
      al modelo. Si la tarjeta lo exige, hace falta una segunda persona distinta.
    """
    if accion not in ACCIONES:
        raise ValueError(f"La decisión debe ser una de {ACCIONES}.")
    if not revisor.strip():
        raise ValueError("Falta el nombre de quien revisa.")
    if accion == "es_fraude":
        return Resolucion("bloqueado", None, (revisor,), "El mensaje no sigue y queda registrado.")
    if accion == "no_estoy_seguro":
        return Resolucion("escalado", None, (revisor,), "Sigue en cuarentena para otra persona.")

    if etiqueta not in set(etiquetas):
        raise ValueError("Para liberar un mensaje hay que elegir una etiqueta de la lista.")
    if tarjeta.requiere_segunda_persona:
        if not segundo_revisor or segundo_revisor.strip().casefold() == revisor.strip().casefold():
            return Resolucion(
                "espera_segunda_persona",
                None,
                (revisor,),
                "Falta que una segunda persona, distinta, confirme que es legítimo.",
            )
        return Resolucion(
            "liberado", etiqueta, (revisor, segundo_revisor), "Liberado por dos personas."
        )
    return Resolucion("liberado", etiqueta, (revisor,), "Liberado por una persona.")

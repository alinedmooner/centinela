"""Detector de reglas: funciona sin internet, sin clave y sin dependencias.

Busca señales de que un mensaje trae instrucciones para la IA que lo lee, en español y
en inglés. Las reglas se escribieron mirando solo la partición ``dev`` del banco de
pruebas. No sustituye a un modelo: atrapa lo conocido y barato de atrapar.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from centinela.tipos import Hallazgo

# Caracteres invisibles, escritos por su código para que el archivo no contenga ninguno.
_CERO_ANCHO = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD)}
_BIDI = {chr(c) for c in (0x202A, 0x202B, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068)}
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)

_IA = r"(asistente( virtual| de ia)?|bot|chatbot|ia|inteligencia artificial|modelo de lenguaje|clasificador|agente de ia|llm|ai|assistant|classifier|language model)"
_INSTR = r"(instruccion\w*|regla\w*|indicacion\w*|directri\w*|instruction\w*|rule\w*|guideline\w*|directive\w*)"

#: nombre de la regla -> patrones. Se aplican sobre texto en minúsculas y sin tildes.
_REGLAS: dict[str, tuple[str, ...]] = {
    "anular_instrucciones": (
        rf"\b(ignora|ignore|ignoren|ignorar|olvida|olvidate|olvidar|omite|omitir|descarta|descartar|desestima|desestimar|anula|anular|pasa por alto|haz caso omiso de?|no (sigas|hagas caso|tengas en cuenta))\b[^.\n]{{0,40}}\b(tus|sus|todas|las|cualquier|toda)\b[^.\n]{{0,20}}\b{_INSTR}\b",
        rf"\b{_INSTR}\b[^.\n]{{0,10}}\b(anteriores|previas|iniciales|originales|del sistema|de arriba|que te dieron)\b",
        r"\b(ignora|olvida|descarta|omite)\b[^.\n]{0,15}\b(todo )?lo (anterior|de arriba|previo)\b",
        rf"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{{0,40}}\b(your|all|any|the|previous|prior|above)\b[^.\n]{{0,25}}\b({_INSTR}|prompt)\b",
    ),
    "dirigido_a_la_ia": (
        rf"\b(nota|mensaje|aviso|instruccion\w*|atencion|importante|note|message|attention)\b[^.\n]{{0,25}}\b(para|al|a la|to|for)\b[^.\n]{{0,15}}\b{_IA}\b",
        rf"\b(estimad[oa]|querid[oa]|oye|dear|hey)\b[ ,]{{1,3}}{_IA}\b",
        rf"\b(si eres|en caso de ser|if you are)\b[^.\n]{{0,20}}\b(una? |an? )?{_IA}\b",
        r"\b(message|mensaje)\b[^.\n]{0,40}\b(to you|para ti|a ti)\b[^.\n]{0,5}[,:]",
    ),
    "etiqueta_forzada": (
        r"\b(clasificame|marcame|etiquetame|categorizame|registrame|ponme|priorizame)\b[^.\n]{0,30}\bcomo\b",
        r"\b(clasific\w+|marc\w+|etiquet\w+|categoriz\w+|asign\w+)\b[^.\n]{0,40}\b(este|esta|el|la|mi)\b[^.\n]{0,10}\b(mensaje|contacto|lead|conversacion|chat|caso|solicitud|ticket)\b[^.\n]{0,30}\b(como|con la etiqueta)\b",
        r"\b(classify|label|mark|tag|categori[sz]e|flag)\b[^.\n]{0,40}\b(this|the|my)\b[^.\n]{0,10}\b(message|contact|lead|conversation|chat|request|ticket)\b[^.\n]{0,30}\bas\b",
        r"\b(etiqueta|categoria|clasificacion|label|category)\b[^.\n]{0,25}\b(correcta|debe ser|tiene que ser|must be|should be)\b",
    ),
    "sistema_falso": (
        r"</?\s*(system|sistema|instrucciones|instructions?|information|informacion|admin|developer|desarrollador|assistant|asistente|mensaje\w*|message|user|usuario|prompt)\b[^>]{0,30}>",
        r"\[\s*/?\s*(system|sistema|admin|inst|developer|desarrollador|instruccion(es)?|nueva regla|override)\b[^\]]{0,40}\]",
        r"<\|[a-z_]{2,20}\|>",
        r"#{2,}\s*\(?\s*(system|sistema|nueva instruccion|new instruction)",
        r"\b(begin|end|inicio|fin) (of |de |del )?(system|sistema|instructions?|instrucciones|prompt)\b",
    ),
    "cambio_de_rol": (
        r"\b(a partir de ahora|desde ahora|de ahora en adelante|from now on|henceforth)\b[^.\n]{0,40}\b(eres|seras|actua\w*|comporta\w*|respond\w*|you are|you will|act|behave)\b",
        rf"\b(actua|finge|simula|hazte pasar|comportate|act|pretend|behave)\b[^.\n]{{0,15}}\b(como|ser|que eres|as|to be|like)\b[^.\n]{{0,40}}\b{_IA}\b",
        r"\b(modo|mode)\b[^.\n]{0,10}\b(desarrollador|developer|dios|god|sin restricciones|unrestricted|jailbreak)\b",
        r"\b(nuevas?|new)\b[^.\n]{0,10}\b(instruccion\w*|instruction\w*)\b\s{0,2}:",
        r"\b(antes de (continuar|seguir|responder|resolver|clasificar)|before you (can )?(solve|continue|answer|respond|proceed))\b[^.\n]{0,60}\b(haz|realiza|ejecuta|debes|tienes que|do|you must)\b",
    ),
    "respuesta_prefabricada": (
        r"\{\s*[\"'“”]?(etiqueta|label|categoria|category|clasificacion|classification|prioridad|priority)[\"'“”]?\s*:",
        r"\b(respuesta|salida|resultado|output|answer|response)\b[^.\n]{0,15}\b(esperad\w+|correct\w+|expected|required)\b[^.\n]{0,5}:",
    ),
    "pedir_instrucciones_internas": (
        r"\b(muestra\w*|revela\w*|dime|imprime|repite|comparte|show|reveal|print|repeat|tell me)\b[^.\n]{0,40}\b(system prompt|prompt del sistema|tus instrucciones|your instructions|reglas internas|instrucciones (del sistema|iniciales|originales))\b",
    ),
}

_REGLAS_COMPILADAS = {
    nombre: tuple(re.compile(patron) for patron in patrones) for nombre, patrones in _REGLAS.items()
}

#: Pistas simples de trucos de persuasión. Sirven para explicar, no para decidir.
_TRUCOS = {
    "distraccion_urgencia": re.compile(
        r"\b(urgente|urge|inmediatamente|de inmediato|ahora mismo|ultim[oa] (aviso|oportunidad|dia)|en (24|48) horas|sera (suspendid|bloquead|cancelad)\w+|accion requerida)\b"
    ),
    "autoridad": re.compile(
        r"\b(gerente|gerencia|director\w*|administrador\w*|soporte tecnico|equipo de seguridad|banco|ministerio|policia|fiscalia|juzgado|duen[oa] de)\b"
    ),
}

_LETRAS_ESPACIADAS = re.compile(r"\b(?:\w[ .\-_*]{1,2}){5,}\w\b")
_MUCHOS_SALTOS = re.compile(r"\n\s*(?:\n\s*){7,}")


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _juntar_letras(texto: str) -> str:
    """Convierte «i g n o r a» en «ignora»."""
    return _LETRAS_ESPACIADAS.sub(lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), texto)


def _variantes(texto: str) -> tuple[list[str], list[str]]:
    """Devuelve las versiones del texto que se revisan y las señales de texto oculto."""
    senales: list[str] = []
    texto = unicodedata.normalize("NFKC", texto)

    etiquetas = [c for c in texto if 0xE0000 <= ord(c) <= 0xE007F]
    oculto = "".join(chr(ord(c) - 0xE0000) for c in etiquetas if 0xE0020 <= ord(c) <= 0xE007E)
    if etiquetas:
        senales.append("texto_oculto: caracteres invisibles que esconden un mensaje")
    if sum(c in _CERO_ANCHO for c in texto) >= 3:
        senales.append("texto_oculto: caracteres de ancho cero entre las letras")
    if any(c in _BIDI for c in texto):
        senales.append("texto_oculto: controles de dirección del texto")
    if _MUCHOS_SALTOS.search(texto):
        senales.append("texto_oculto: contenido después de muchos saltos de línea")

    visible = "".join(
        c
        for c in texto
        if c not in _CERO_ANCHO and c not in _BIDI and not 0xE0000 <= ord(c) <= 0xE007F
    )
    base = _sin_tildes(visible.lower())
    variantes = [base]
    juntas = _juntar_letras(base)
    if juntas != base:
        variantes.append(juntas)
    sin_leet = " ".join(
        p.translate(_LEET) if any(c.isalpha() for c in p) and any(c in "013457@$" for c in p) else p
        for p in juntas.split(" ")
    )
    if sin_leet != juntas:
        variantes.append(sin_leet)
    if oculto.strip():
        variantes.append(_sin_tildes(oculto.lower()))
    return variantes, senales


class DetectorReglas:
    """Detector de reglas en español e inglés. No usa red ni modelos.

    Si recibe las ``etiquetas`` del clasificador que protege, también marca los mensajes
    que piden una de ellas por su nombre («ponme como prioritario»).
    """

    nombre = "reglas"

    def __init__(self, etiquetas: Iterable[str] | None = None):
        self._reglas = dict(_REGLAS_COMPILADAS)
        nombres = [re.escape(_sin_tildes(e.lower()).replace("_", " ")) for e in (etiquetas or [])]
        if nombres:
            lista = "|".join(nombres)
            self._reglas["nombra_una_etiqueta"] = (
                re.compile(
                    r"\b(como|etiqueta|categoria|clasificacion|label|category|as|respuesta|answer|output)\b"
                    rf"[^.\n]{{0,25}}[\"'“”«]?\b({lista})\b"
                ),
                re.compile(
                    rf"\b({lista})\b[^.\n]{{0,30}}\b(es la (etiqueta|respuesta|categoria)|is the (label|answer|category))\b"
                ),
            )

    def revisar(self, texto: str) -> Hallazgo:
        variantes, evidencias = _variantes(texto)
        for nombre, patrones in self._reglas.items():
            for variante in variantes:
                coincidencia = next((m for p in patrones if (m := p.search(variante))), None)
                if coincidencia:
                    fragmento = " ".join(coincidencia.group(0).split())[:80]
                    evidencias.append(f"{nombre}: «{fragmento}»")
                    break
        base = variantes[0]
        trucos = tuple(nombre for nombre, patron in _TRUCOS.items() if patron.search(base))
        return Hallazgo(
            detector=self.nombre,
            ordenes_para_ia=bool(evidencias),
            trucos=trucos,
            evidencias=tuple(evidencias),
        )

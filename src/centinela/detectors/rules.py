"""Detector de reglas: funciona sin internet, sin clave y sin dependencias.

Busca señales de que un mensaje trae instrucciones para la IA que lo lee, en español y
en inglés. Las reglas se escribieron mirando solo la partición ``dev`` del banco de
pruebas. No sustituye a un modelo: atrapa lo conocido y barato de atrapar.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from centinela.verdict import Finding

# Caracteres invisibles, escritos por su código para que el archivo no contenga ninguno.
_ZERO_WIDTH = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD)}
_BIDI = {chr(c) for c in (0x202A, 0x202B, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068)}
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)

_AI = r"(asistente( virtual| de ia)?|bot|chatbot|ia|inteligencia artificial|modelo de lenguaje|clasificador|agente de ia|llm|ai|assistant|classifier|language model)"
_INSTR = r"(instruccion\w*|reglas?|indicacion\w*|directri\w*|instruction\w*|rules?|guideline\w*|directive\w*)"

#: nombre de la regla -> patrones. Se aplican sobre texto en minúsculas y sin tildes.
_RULES: dict[str, tuple[str, ...]] = {
    "anular_instrucciones": (
        rf"\b(ignora|ignore|ignoren|ignorar|olvida|olvidate|olvidar|omite|omitir|descarta|descartar|desestima|desestimar|anula|anular|pasa por alto|haz caso omiso de?|no (sigas|hagas caso|tengas en cuenta))\b[^.\n]{{0,40}}\b(tus|sus|todas|las|cualquier|toda)\b[^.\n]{{0,20}}\b{_INSTR}\b",
        rf"\b{_INSTR}\b[^.\n]{{0,10}}\b(anteriores|previas|iniciales|originales|del sistema|de arriba|que te dieron)\b",
        r"\b(ignora|olvida|descarta|omite)\b[^.\n]{0,15}\b(todo )?lo (anterior|de arriba|previo)\b",
        r"\b(anula|anular|cancela|desactiva|sobrescribe|override)\b[^.\n]{0,30}\b(clasificacion|etiquetado|filtro|revision automatica|classification)\b",
        rf"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{{0,40}}\b(your|all|any|the|previous|prior|above)\b[^.\n]{{0,25}}\b({_INSTR}|prompt)\b",
    ),
    "dirigido_a_la_ia": (
        rf"\b(nota|mensaje|aviso|instruccion\w*|atencion|importante|note|message|attention)\b[^.\n]{{0,25}}\b(para|al|a la|to|for)\b[^.\n]{{0,15}}\b{_AI}\b",
        rf"\b(estimad[oa]|querid[oa]|oye|dear|hey)\b[ ,]{{1,3}}{_AI}\b",
        rf"\b(si eres|en caso de ser|if you are)\b[^.\n]{{0,20}}\b(una? |an? )?{_AI}\b",
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
        r"#{2,}\s*\(?\s*(system|sistema|desarrollador|developer|admin\w*|nueva instruccion|new instruction|instruccion\w*|instruction\w*)",
        r"\b(begin|end|inicio|fin) (of |de |del )?(system|sistema|instructions?|instrucciones|prompt)\b",
    ),
    "cambio_de_rol": (
        r"\b(a partir de ahora|desde ahora|de ahora en adelante|from now on|henceforth)\b[^.\n]{0,40}\b(eres|seras|actua\w*|comporta\w*|respond\w*|you are|you will|act|behave)\b",
        rf"\b(actua|finge|simula|hazte pasar|comportate|act|pretend|behave)\b[^.\n]{{0,15}}\b(como|ser|que eres|as|to be|like)\b[^.\n]{{0,40}}\b{_AI}\b",
        r"\b(modo|mode)\b[^.\n]{0,10}\b(desarrollador|developer|dios|god|sin restricciones|unrestricted|jailbreak)\b",
        r"\b(nuevas?|new)\b[^.\n]{0,10}\b(instruccion\w*|instruction\w*)\b\s{0,2}:",
        r"\b(antes de (continuar|seguir|responder|resolver|clasificar)|before you (can )?(solve|continue|answer|respond|proceed))\b[^.\n]{0,60}\b(haz|realiza|ejecuta|debes|tienes que|do|you must)\b",
    ),
    "respuesta_prefabricada": (
        r"[\"'“”](etiqueta|label|categoria|category|clasificacion|classification|prioridad|priority)[\"'“”]\s*:\s*[\"'“”]",
        r"\{\s*[\"'“”]?(etiqueta|label|categoria|category|clasificacion|classification|prioridad|priority)[\"'“”]?\s*:",
        r"\b(respuesta|salida|resultado|output|answer|response)\b[^.\n]{0,15}\b(esperad\w+|correct\w+|expected|required)\b[^.\n]{0,5}:",
    ),
    "pedir_instrucciones_internas": (
        r"\b(muestra\w*|revela\w*|dime|imprime|repite|comparte|show|reveal|print|repeat|tell me)\b[^.\n]{0,40}\b(system prompt|prompt del sistema|tus instrucciones|your instructions|reglas internas|instrucciones (del sistema|iniciales|originales))\b",
    ),
}

_COMPILED_RULES = {
    name: tuple(re.compile(patron) for patron in patterns) for name, patterns in _RULES.items()
}

#: Pistas simples de trucos de persuasión. Sirven para explicar, no para decidir.
_TRICKS = {
    "distraccion_urgencia": re.compile(
        r"\b(urgente|urge|inmediatamente|de inmediato|ahora mismo|ultim[oa] (aviso|oportunidad|dia)|en (24|48) horas|sera (suspendid|bloquead|cancelad)\w+|accion requerida)\b"
    ),
    "autoridad": re.compile(
        r"\b(gerente|gerencia|director\w*|administrador\w*|soporte tecnico|equipo de seguridad|banco|ministerio|policia|fiscalia|juzgado|duen[oa] de)\b"
    ),
}

# Órdenes de anular instrucciones escritas con erratas («ignore your previous iunstructions»).
_OVERRIDE_WITH_TYPO = re.compile(
    r"\b(ignore|disregard|forget|override|bypass|ignora|ignoren|olvida|descarta|omite|desestima)\b\s+"
    r"(?:(?:your|all|any|the|my|previous|prior|above|earlier|tus|sus|las|todas|toda|cualquier|mis)\s+){1,3}"
    r"(\w{7,})"
)
_INSTRUCTION_WORDS = (
    "instructions",
    "instruction",
    "guidelines",
    "directives",
    "instrucciones",
    "indicaciones",
    "directrices",
)

_ZERO_WIDTH_BETWEEN_LETTERS = re.compile(
    "[^\\W\\d_][" + "".join(sorted(_ZERO_WIDTH)) + "]+(?=[^\\W\\d_])"
)
_SPACED_LETTERS = re.compile(r"\b(?:\w[ .\-_*]{1,2}){5,}\w\b")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _distance(a: str, b: str) -> int:
    """Distancia de edición entre dos palabras."""
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        actual = [i]
        for j, cb in enumerate(b, start=1):
            actual.append(min(anterior[j] + 1, actual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = actual
    return anterior[-1]


def _override_with_typo(text: str) -> str | None:
    """Encuentra «ignora tus <instrucciones>» aunque la última palabra tenga una errata."""
    for match in _OVERRIDE_WITH_TYPO.finditer(text):
        word = match.group(2)
        if any(_distance(word, target) <= 2 for target in _INSTRUCTION_WORDS):
            return match.group(0)
    return None


def _join_letters(text: str) -> str:
    """Convierte «i g n o r a» en «ignora»."""
    return _SPACED_LETTERS.sub(lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), text)


def _variants(text: str) -> tuple[list[str], list[str]]:
    """Devuelve las versiones del texto que se revisan y las señales de texto oculto."""
    signals: list[str] = []
    text = unicodedata.normalize("NFKC", text)

    labels = [c for c in text if 0xE0000 <= ord(c) <= 0xE007F]
    hidden = "".join(chr(ord(c) - 0xE0000) for c in labels if 0xE0020 <= ord(c) <= 0xE007E)
    if labels:
        signals.append("texto_oculto: caracteres invisibles que esconden un mensaje")
    # Los correos de publicidad usan caracteres de ancho cero como relleno entre palabras.
    # Solo son sospechosos cuando van dentro de las palabras, para partirlas.
    if len(_ZERO_WIDTH_BETWEEN_LETTERS.findall(text)) >= 3:
        signals.append("texto_oculto: caracteres de ancho cero que parten palabras")

    visible = "".join(
        c
        for c in text
        if c not in _ZERO_WIDTH and c not in _BIDI and not 0xE0000 <= ord(c) <= 0xE007F
    )
    base = _strip_accents(visible.lower())
    variants = [base]
    juntas = _join_letters(base)
    if juntas != base:
        variants.append(juntas)
    without_leet = " ".join(
        p.translate(_LEET) if any(c.isalpha() for c in p) and any(c in "013457@$" for c in p) else p
        for p in juntas.split(" ")
    )
    if without_leet != juntas:
        variants.append(without_leet)
    if hidden.strip():
        variants.append(_strip_accents(hidden.lower()))
    return variants, signals


class RulesDetector:
    """Detector de reglas en español e inglés. No usa red ni modelos.

    Si recibe las ``etiquetas`` del clasificador que protege, también marca los mensajes
    que piden una de ellas por su nombre («ponme como prioritario»).
    """

    name = "reglas"

    def __init__(self, labels: Iterable[str] | None = None):
        self._rules = dict(_COMPILED_RULES)
        names = [re.escape(_strip_accents(e.lower()).replace("_", " ")) for e in (labels or [])]
        if names:
            joined = "|".join(names)
            self._rules["nombra_una_etiqueta"] = (
                re.compile(
                    r"\b(etiqueta\w*|categoria\w*|clasificacion\w*|label\w*|category\w*|respuesta\w*"
                    r"|salida\w*|answer\w*|output\w*)\b[^.\n:=]{0,25}"
                    rf"(:|=>?|->|→|\bes\b|\bsea\b|\bdebe ser\b|\bis\b|\bmust be\b)\s*[\"'“”«]?\s*({joined})\b"
                ),
                re.compile(
                    r"\b(clasific\w+|clasifiqu\w+|marc\w+|marqu\w+|etiquet\w+|categori[zc]\w+|registr\w+"
                    r"|trat\w+|consider\w+|pon\w*|asign\w+|classif\w+|label\w*|mark\w*|tag\w*|flag\w*)\b"
                    rf"[^.\n]{{0,40}}\b(como|as)\s+[\"'“”«]?({joined})\b"
                ),
                re.compile(
                    rf"\b({joined})\b[^.\n]{{0,30}}\b(es la (etiqueta|respuesta|categoria)|is the (label|answer|category))\b"
                ),
                re.compile(
                    r"\b(etiqueta\w*|categoria\w*|clasificacion\w*|label\w*|category\w*)\s+(de\s+)?"
                    rf"[\"'“”«]?({joined})\b"
                ),
            )

    def check(self, text: str) -> Finding:
        variants, evidence = _variants(text)
        for name, patterns in self._rules.items():
            for variant in variants:
                match = next((m for p in patterns if (m := p.search(variant))), None)
                if match:
                    fragment = " ".join(match.group(0).split())[:80]
                    evidence.append(f"{name}: «{fragment}»")
                    break
        if not any(e.startswith("anular_instrucciones") for e in evidence):
            errata = next((e for v in variants if (e := _override_with_typo(v))), None)
            if errata:
                evidence.append(f"anular_instrucciones: «{errata[:80]}»")
        base = variants[0]
        tricks = tuple(name for name, patron in _TRICKS.items() if patron.search(base))
        return Finding(
            detector=self.name,
            ai_instructions=bool(evidence),
            tricks=tricks,
            evidence=tuple(evidence),
        )

"""Text that people read: notices, review cards and command-line messages, in two languages.

The language is chosen once (``Guard(lang=...)``, ``--lang``) and travels with the verdict
and the review card. ``en`` is the default; ``es`` is the language of the messages Centinela
analyzes, so a business that reviews in Spanish gets the same screens in Spanish.

What a language model sees is **not** here. The instructions, the JSON schema, the label
definitions, the wrapper marker and the mail headers are Spanish on purpose: they are what
the saved measurements were made with (see ``protocol.py`` and the notes in each module).
"""

from __future__ import annotations

import re

LANGS = ("en", "es")
DEFAULT_LANG = "en"

CATALOG: dict[str, dict[str, str]] = {
    "en": {
        # Verdict notices
        "notice.ai_instructions": "It contains instructions addressed to the AI assistant.",
        "notice.deception": "It looks like a deception aimed at a person.",
        "notice.tricks": "Tricks it uses: {tricks}.",
        "notice.detector_failed": "A detector could not check it; as a precaution a person sees it.",
        "notice.none": "No signs of manipulation.",
        # Persuasion tricks (the ids are the Spanish ones of the model schema)
        "trick.autoridad": "presents itself as someone with authority (boss, bank, support, government)",
        "trick.prueba_social": "says other people already did it or approve it",
        "trick.simpatia_engano": "pretends closeness or trust to win the person over",
        "trick.compromiso_reciprocidad": "appeals to a previous commitment or to returning a favor",
        "trick.distraccion_urgencia": "rushes, scares or offers a prize so the person does not think",
        # What the message asks for, and how it pressures
        "ask.open_link": "open a link",
        "ask.give_credentials": "give a password or personal data",
        "ask.send_money": "pay or transfer money",
        "ask.open_file": "download or open a file",
        "ask.contact": "call or write to a contact",
        "ask.instruct_ai": "give orders to the AI assistant",
        "pressure.urgency": "urgency",
        "pressure.threat": "threat",
        "pressure.prize_or_offer": "prize or offer",
        # Values shown to a person
        "decision.allow": "allow",
        "decision.review": "review",
        "reason.model": "model",
        "reason.guard": "guard",
        "reason.invalid_response": "invalid_response",
        "reason.refusal": "refusal",
        "reason.error": "error",
        # Defanged text
        "defang.hidden_number": "[hidden number, ends in {digits}]",
        "defang.looks_like": " (looks like «{domain}»)",
        # Review card
        "card.title": "HUMAN REVIEW · message in quarantine",
        "card.field.notice": "Notice:",
        "card.field.claims": "Claims to be:",
        "card.field.asks": "Asks for:",
        "card.field.pressure": "Pressure:",
        "card.none.claims": "does not say",
        "card.none.recognized": "nothing the rules recognize",
        "card.links": "Links and emails (disabled): {links}",
        "card.none.links": "none",
        "card.hidden_warning": "Heads up! Links that lead to another domain: {destinations}",
        "card.sender_text_start": "--- Sender's text (untrusted) ---",
        "card.sender_text_end": "--- End of the sender's text ---",
        "card.decisions_title": "Possible decisions (none does what the message asks):",
        "card.action.is_fraud": "It is fraud",
        "card.action.is_legitimate": "It is legitimate",
        "card.second_person": " · needs a second person",
        "card.action.not_sure": "I'm not sure",
        # Resolutions and the errors a person can cause in the review room
        "resolution.blocked": "The message does not go on and is recorded.",
        "resolution.escalated": "It stays in quarantine for another person.",
        "resolution.awaiting_second_person": "A second, different person must confirm that it is legitimate.",
        "resolution.released_two": "Released by two people.",
        "resolution.released_one": "Released by one person.",
        "error.invalid_action": "The decision must be one of {actions}.",
        "error.reviewer_missing": "The name of the reviewer is missing.",
        "error.label_required": "To release a message, choose a label from the list.",
        # Command line
        "cli.description": "Guard for AI assistants that read messages in Spanish.",
        "cli.decision": "Decision: {decision}",
        "cli.notice": "Notice: {notice}",
        "cli.label": "Label: {label} (decided by: {reason})",
        "cli.possible_labels": "Possible labels, defined by the business: {labels}",
        "cli.error": "Error: {message}",
        "cli.warn_odd_labels": "Warning: use single-word names, without spaces or hyphens, so the guard recognizes a message that tries to impose them: {names}",
        "cli.error.labels_file": 'the labels file must be a JSON object {{"name": "definition"}} with at least one label',
        "cli.help.text": "the message; «-» or nothing reads it from standard input",
        "cli.help.file": "read the message from a file",
        "cli.help.json": "print the result as JSON",
        "cli.help.labels": 'JSON file with your business labels, {{"name": "definition"}}; without it the example labels of a sales bot are used (see examples/)',
        "cli.help.lang": "language of notices, cards and messages (default: en, or CENTINELA_LANG)",
        "cli.help.check": "check a message with the rules, without a key or internet",
        "cli.help.claude": "besides the rules, ask Claude (uses the key); same as --provider anthropic",
        "cli.help.provider": "besides the rules, ask a model of this provider (uses its key)",
        "cli.help.model": "model of the provider; a cheap one by default: claude-haiku-5-5, gemini-3.5-flash-lite or google/gemma-4-26b-a4b-it (OpenRouter)",
        "cli.help.card": "if the message goes to human review, show the review-room card",
        "cli.help.classify": "classify a customer message with a model (Claude by default)",
        "cli.help.classify_provider": "who puts the label",
        # Provider errors, as shown by the command line (the library raises English messages)
        "provider.rate_limit": "The API rate limit was reached.",
        "provider.api_error": "The API answered with error {status}.",
        "provider.connection": "Could not connect to the API.",
        "provider.missing_sdk": "The SDK of the provider is missing. Install the extra: {hint}",
        "provider.missing_key": "The key of the provider is missing: set {variable}.",
    },
    "es": {
        "notice.ai_instructions": "Trae órdenes dirigidas al asistente de IA.",
        "notice.deception": "Parece un engaño dirigido a una persona.",
        "notice.tricks": "Trucos que usa: {tricks}.",
        "notice.detector_failed": "Un detector no pudo revisarlo; por precaución lo ve una persona.",
        "notice.none": "Sin señales de manipulación.",
        "trick.autoridad": "se presenta como alguien con autoridad (jefe, banco, soporte, gobierno)",
        "trick.prueba_social": "dice que otras personas ya lo hicieron o lo aprueban",
        "trick.simpatia_engano": "finge cercanía o confianza para ganarse a la persona",
        "trick.compromiso_reciprocidad": "apela a un compromiso previo o a devolver un favor",
        "trick.distraccion_urgencia": "mete prisa, miedo o un premio para que la persona no piense",
        "ask.open_link": "entrar a un enlace",
        "ask.give_credentials": "dar una clave o datos personales",
        "ask.send_money": "pagar o transferir dinero",
        "ask.open_file": "descargar o abrir un archivo",
        "ask.contact": "llamar o escribir a un contacto",
        "ask.instruct_ai": "darle órdenes al asistente de IA",
        "pressure.urgency": "urgencia",
        "pressure.threat": "amenaza",
        "pressure.prize_or_offer": "premio u oferta",
        "decision.allow": "permitir",
        "decision.review": "revisar",
        "reason.model": "modelo",
        "reason.guard": "guardia",
        "reason.invalid_response": "respuesta_invalida",
        "reason.refusal": "rechazo",
        "reason.error": "error",
        "defang.hidden_number": "[número oculto, termina en {digits}]",
        "defang.looks_like": " (se ve como «{domain}»)",
        "card.title": "REVISIÓN HUMANA · mensaje en cuarentena",
        "card.field.notice": "Aviso:",
        "card.field.claims": "Dice ser:",
        "card.field.asks": "Pide:",
        "card.field.pressure": "Presiona con:",
        "card.none.claims": "no lo dice",
        "card.none.recognized": "nada que las reglas reconozcan",
        "card.links": "Enlaces y correos (desactivados): {links}",
        "card.none.links": "ninguno",
        "card.hidden_warning": "¡Ojo! Enlaces que llevan a otro dominio: {destinations}",
        "card.sender_text_start": "--- Texto del remitente (no confiable) ---",
        "card.sender_text_end": "--- Fin del texto del remitente ---",
        "card.decisions_title": "Decisiones posibles (ninguna hace lo que pide el mensaje):",
        "card.action.is_fraud": "Es fraude",
        "card.action.is_legitimate": "Es legítimo",
        "card.second_person": " · requiere una segunda persona",
        "card.action.not_sure": "No estoy seguro",
        "resolution.blocked": "El mensaje no sigue y queda registrado.",
        "resolution.escalated": "Sigue en cuarentena para otra persona.",
        "resolution.awaiting_second_person": "Falta que una segunda persona, distinta, confirme que es legítimo.",
        "resolution.released_two": "Liberado por dos personas.",
        "resolution.released_one": "Liberado por una persona.",
        "error.invalid_action": "La decisión debe ser una de {actions}.",
        "error.reviewer_missing": "Falta el nombre de quien revisa.",
        "error.label_required": "Para liberar un mensaje hay que elegir una etiqueta de la lista.",
        "cli.description": "Guardia para asistentes de IA que leen mensajes en español.",
        "cli.decision": "Decisión: {decision}",
        "cli.notice": "Aviso: {notice}",
        "cli.label": "Etiqueta: {label} (decidió: {reason})",
        "cli.possible_labels": "Etiquetas posibles, definidas por el negocio: {labels}",
        "cli.error": "Error: {message}",
        "cli.warn_odd_labels": "Aviso: usa nombres de una sola palabra, sin espacios ni guiones, para que el guardia reconozca un mensaje que intenta imponerlos: {names}",
        "cli.error.labels_file": 'el archivo de etiquetas debe ser un objeto JSON {{"nombre": "definición"}} con al menos una etiqueta',
        "cli.help.text": "el mensaje; «-» o nada para leerlo de la entrada estándar",
        "cli.help.file": "lee el mensaje de un archivo",
        "cli.help.json": "imprime el resultado en JSON",
        "cli.help.labels": 'archivo JSON con las etiquetas de tu negocio, {{"nombre": "definición"}}; sin él se usan las de ejemplo de un bot de ventas (ver ejemplos/)',
        "cli.help.lang": "idioma de los avisos, las tarjetas y los mensajes (por defecto: en, o CENTINELA_LANG)",
        "cli.help.check": "revisa un mensaje con reglas, sin clave ni internet",
        "cli.help.claude": "además de las reglas, consulta a Claude (usa la clave); igual a --provider anthropic",
        "cli.help.provider": "además de las reglas, consulta un modelo de este proveedor (usa su clave)",
        "cli.help.model": "modelo del proveedor; por defecto uno barato: claude-haiku-5-5, gemini-3.5-flash-lite o google/gemma-4-26b-a4b-it (OpenRouter)",
        "cli.help.card": "si el mensaje va a revisión humana, muestra la tarjeta de la sala de revisión",
        "cli.help.classify": "clasifica un mensaje de un cliente con un modelo (Claude por defecto)",
        "cli.help.classify_provider": "quién pone la etiqueta",
        "provider.rate_limit": "Se alcanzó el límite de peticiones de la API.",
        "provider.api_error": "La API respondió con el error {status}.",
        "provider.connection": "No se pudo conectar con la API.",
        "provider.missing_sdk": "Falta el SDK del proveedor. Instala el extra: {hint}",
        "provider.missing_key": "Falta la clave del proveedor: define {variable}.",
    },
}


def check_lang(lang: str) -> str:
    """Return ``lang`` if it is supported; raise ``ValueError`` otherwise."""
    if lang not in CATALOG:
        raise ValueError(f"unknown language: {lang!r}; use one of {', '.join(LANGS)}")
    return lang


def t(key: str, lang: str = DEFAULT_LANG, **fields: object) -> str:
    """The text for ``key`` in ``lang``, with ``fields`` filled in."""
    return CATALOG[check_lang(lang)][key].format(**fields)


def hidden_number_re(lang: str = DEFAULT_LANG) -> re.Pattern[str]:
    """Pattern that finds the placeholder ``defang`` leaves where it hid a number."""
    text = CATALOG[check_lang(lang)]["defang.hidden_number"]
    return re.compile(re.escape(text).replace(re.escape("{digits}"), r"\d{2}"))

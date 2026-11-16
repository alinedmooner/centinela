"""Buzón seguro: Centinela entre las herramientas de correo de Composio y un agente de IA.

Muchos agentes leen el correo con las herramientas de Gmail de Composio. Este módulo revisa
cada correo en código, antes de que el agente lo vea. Los sospechosos se retienen: el agente
recibe solo un aviso de que el correo quedó para revisión humana, nunca su texto. La decisión
no depende de que el agente se acuerde de consultar a Centinela.

Uso con Composio (que es opcional: solo se importa al crear los modificadores)::

    from composio import Composio
    from centinela.buzon_seguro import modificadores

    composio = Composio()
    herramientas = composio.tools.get(user_id, toolkits=["gmail"], modifiers=modificadores())
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

from centinela.detectors.rules import RulesDetector
from centinela.guard import Guard
from centinela.labels import LEAD_LABELS
from centinela.mail import Mail, read_mail, text_to_check
from centinela.review import ReviewCard, create_card
from centinela.verdict import Verdict

#: Herramientas de Composio que entregan correos completos al agente.
READING_TOOLS = (
    "GMAIL_FETCH_EMAILS",
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
    "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
)
#: Campos que se conservan de un correo retenido: solo identificadores y metadatos.
_SAFE_FIELDS = ("messageId", "id", "threadId", "labelIds", "messageTimestamp", "internalDate")

OnHold = Callable[[Mail, Verdict, ReviewCard], None]


def _b64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _header(payload: dict, name: str) -> str:
    for header in payload.get("headers") or []:
        if str(header.get("name", "")).lower() == name.lower():
            return str(header.get("value", ""))
    return ""


def _parts(payload: dict):
    yield payload
    for part in payload.get("parts") or []:
        if isinstance(part, dict):
            yield from _parts(part)


def _from_payload(message: dict, payload: dict) -> Mail | None:
    """Rehace un correo MIME mínimo con las partes de texto del formato «full» de Gmail."""
    plain = html = ""
    for part in _parts(payload):
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        content = _b64url(data).decode("utf-8", errors="replace")
        kind = str(part.get("mimeType", "")).lower()
        if kind == "text/plain" and not plain:
            plain = content
        elif kind == "text/html" and not html:
            html = content
    if not (plain or html):
        return None
    rebuilt = EmailMessage()
    try:
        rebuilt["From"] = _header(payload, "From") or str(message.get("sender", ""))
        rebuilt["Subject"] = _header(payload, "Subject") or str(message.get("subject", ""))
    except (ValueError, TypeError):
        pass  # una cabecera mal formada no impide revisar el cuerpo
    if plain:
        rebuilt.set_content(plain)
        if html:
            rebuilt.add_alternative(html, subtype="html")
    else:
        rebuilt.set_content(html, subtype="html")
    return read_mail(rebuilt)


def mail_from_gmail(message: dict[str, Any]) -> Mail:
    """Arma un ``Correo`` con lo que devuelve Gmail por Composio: «raw», «payload» o campos sueltos."""
    if message.get("raw"):
        return read_mail(_b64url(str(message["raw"])))
    payload = message.get("payload")
    if isinstance(payload, dict):
        mail = _from_payload(message, payload)
        if mail:
            return mail
    text = next(
        (str(message[c]) for c in ("messageText", "preview", "snippet") if message.get(c)), ""
    )
    return Mail(
        sender=str(message.get("sender", "")),
        subject=str(message.get("subject", "")),
        text=text,
        links=(),
        attachments=(),
    )


def check_message(
    message: dict[str, Any], guard: Guard | None = None
) -> tuple[Mail, Verdict, ReviewCard | None]:
    """Revisa un correo de Gmail. Si va a revisión, devuelve también su tarjeta."""
    guard = guard or Guard([RulesDetector(labels=LEAD_LABELS)])
    mail = mail_from_gmail(message)
    text = text_to_check(mail)
    verdict = guard.check(text)
    card = None
    if verdict.decision == "revisar":
        card = create_card(text, verdict, hidden_links=mail.links)
    return mail, verdict, card


def sanitize_message(
    message: dict[str, Any], guard: Guard | None = None, on_hold: OnHold | None = None
) -> dict[str, Any]:
    """Deja pasar un correo normal y retiene uno sospechoso: el agente no recibe su texto."""
    mail, verdict, card = check_message(message, guard)
    if card is None:
        return {**message, "centinela": {"decision": "permitir"}}
    if on_hold:
        on_hold(mail, verdict, card)
    held = {k: message[k] for k in _SAFE_FIELDS if k in message}
    held.update(
        sender=parseaddr(mail.sender)[1],
        subject="[Retenido por Centinela]",
        messageText=(
            "Centinela retuvo este correo para revisión humana y no entrega su contenido. "
            f"Motivo: {verdict.notice}"
        ),
        centinela={"decision": "revisar", "aviso": verdict.notice},
    )
    return held


def sanitize_response(data: Any, guard: Guard | None = None, on_hold: OnHold | None = None) -> Any:
    """Aplica ``limpiar_mensaje`` a cada correo de una respuesta de las herramientas de Gmail."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return data
    if not isinstance(data, dict):
        return data
    for key in ("messages", "emails"):
        if isinstance(data.get(key), list):
            return {
                **data,
                key: [
                    sanitize_message(m, guard, on_hold) if isinstance(m, dict) else m
                    for m in data[key]
                ],
            }
    if any(k in data for k in ("raw", "payload", "messageText")):
        return sanitize_message(data, guard, on_hold)
    return data


def modifiers(guard: Guard | None = None, on_hold: OnHold | None = None) -> list:
    """Modificadores de Composio que ponen a Centinela delante de las herramientas de lectura.

    - Antes: pide a Gmail el contenido completo, para que el guardia revise el cuerpo y no solo
      el asunto.
    - Después: revisa cada correo y retiene los sospechosos antes de que los vea el agente.
    """
    from composio import after_execute, before_execute

    @before_execute(tools=["GMAIL_FETCH_EMAILS"])
    def ask_for_content(tool: str, toolkit: str, params: Any) -> Any:
        params["arguments"]["verbose"] = True
        params["arguments"]["include_payload"] = True
        return params

    @after_execute(tools=list(READING_TOOLS))
    def safe_inbox(tool: str, toolkit: str, response: Any) -> Any:
        if not response.get("successful") or response.get("data") is None:
            return response
        return {**response, "data": sanitize_response(response["data"], guard, on_hold)}

    return [ask_for_content, safe_inbox]

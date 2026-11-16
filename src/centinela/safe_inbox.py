"""Safe inbox: Centinela between Composio's email tools and an AI agent.

Many agents read email with Composio's Gmail tools. This module checks each email in code,
before the agent sees it. Suspicious ones are held: the agent receives only a notice that the
email was left for human review, never its text. The decision does not depend on the agent
remembering to consult Centinela.

Usage with Composio (optional: it is imported only when the modifiers are created)::

    from composio import Composio
    from centinela.safe_inbox import modifiers

    composio = Composio()
    tools = composio.tools.get(user_id, toolkits=["gmail"], modifiers=modifiers())
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

#: Composio tools that hand complete emails to the agent.
READING_TOOLS = (
    "GMAIL_FETCH_EMAILS",
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
    "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
)
#: Fields kept from a held email: only identifiers and metadata.
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
    """Rebuilds a minimal MIME email from the text parts of Gmail's "full" format."""
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
        pass  # a malformed header does not prevent checking the body
    if plain:
        rebuilt.set_content(plain)
        if html:
            rebuilt.add_alternative(html, subtype="html")
    else:
        rebuilt.set_content(html, subtype="html")
    return read_mail(rebuilt)


def mail_from_gmail(message: dict[str, Any]) -> Mail:
    """Builds a ``Mail`` from what Gmail returns via Composio: "raw", "payload" or loose fields."""
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
    """Checks a Gmail email. If it goes to review, it also returns its review card."""
    guard = guard or Guard([RulesDetector(labels=LEAD_LABELS)])
    mail = mail_from_gmail(message)
    text = text_to_check(mail)
    verdict = guard.check(text)
    card = None
    if verdict.decision == "review":
        card = create_card(text, verdict, hidden_links=mail.links)
    return mail, verdict, card


def sanitize_message(
    message: dict[str, Any], guard: Guard | None = None, on_hold: OnHold | None = None
) -> dict[str, Any]:
    """Lets a normal email through and holds a suspicious one: the agent does not get its text.

    The text that replaces a held email is Spanish on purpose: it is what the agent sees.
    """
    mail, verdict, card = check_message(message, guard)
    if card is None:
        return {**message, "centinela": {"decision": "allow"}}
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
        centinela={"decision": "review", "notice": verdict.notice},
    )
    return held


def sanitize_response(data: Any, guard: Guard | None = None, on_hold: OnHold | None = None) -> Any:
    """Applies ``sanitize_message`` to each email in a response from the Gmail tools."""
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
    """Composio modifiers that put Centinela in front of the reading tools.

    - Before: asks Gmail for the full content, so the guard checks the body and not only the
      subject.
    - After: checks each email and holds the suspicious ones before the agent sees them.
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

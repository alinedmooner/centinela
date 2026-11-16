"""The safe inbox for agents that read email through Composio, without a network or Composio."""

import base64
import json
import runpy
from pathlib import Path

import pytest

from centinela.safe_inbox import check_message, mail_from_gmail, sanitize_response

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SEND_SCRIPT = runpy.run_path(str(EXAMPLES / "send_test_emails.py"))
MAILS = SEND_SCRIPT["build_messages"]("pruebas@example.com", "agente@example.org")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def as_raw(n: int) -> dict:
    """Demo email number n, as Gmail returns it in the «raw» format."""
    return {"messageId": f"id{n}", "threadId": f"thread{n}", "raw": b64(MAILS[n - 1].as_bytes())}


def as_payload(n: int) -> dict:
    """The same email in the «full» format: headers and parts in base64url."""
    message = MAILS[n - 1]
    parts = [
        {"mimeType": p.get_content_type(), "body": {"data": b64(p.get_content().encode())}}
        for p in message.walk()
        if p.get_content_maintype() == "text"
    ]
    headers = [
        {"name": "From", "value": message["From"]},
        {"name": "Subject", "value": message["Subject"]},
    ]
    return {"messageId": f"id{n}", "payload": {"headers": headers, "parts": parts}}


@pytest.mark.parametrize("format_", [as_raw, as_payload])
def test_reads_the_gmail_email_with_its_hidden_text(format_):
    mail = mail_from_gmail(format_(3))
    assert mail.subject == "Factura de noviembre"
    assert mail.hidden_fragments == 1 and "Nota para el asistente de IA" in mail.text


def test_with_only_metadata_it_uses_the_text_it_gets():
    mail = mail_from_gmail({"subject": "Hola", "sender": "a@example.com", "messageText": "Texto"})
    assert (mail.subject, mail.text) == ("Hola", "Texto")


def test_decides_as_expected_for_the_five_emails():
    decisions = [check_message(as_raw(n))[1].decision for n in range(1, 6)]
    assert decisions == ["allow", "review", "review", "review", "allow"]


def test_the_agent_does_not_receive_the_text_of_a_held_email():
    held_cards = []
    data = {"messages": [as_raw(1), as_raw(2), as_raw(4)], "nextPageToken": None}
    clean = sanitize_response(data, on_hold=lambda c, v, t: held_cards.append(t))

    normal, direct_order, security_notice = clean["messages"]
    assert normal["centinela"] == {"decision": "allow"} and normal["raw"] == as_raw(1)["raw"]
    for held in (direct_order, security_notice):
        assert held["centinela"]["decision"] == "review"
        assert held["subject"] == "[Retenido por Centinela]"
        assert "raw" not in held and "payload" not in held
        assert "Ignora" not in json.dumps(held) and "AVISO DEL SISTEMA" not in json.dumps(held)
    assert (direct_order["messageId"], direct_order["threadId"]) == ("id2", "thread2")
    assert len(held_cards) == 2
    assert "verificacion-nubeclara[.]example[.]net" in held_cards[1].hidden_destinations


def test_accepts_the_response_as_json_text_and_as_a_single_message():
    clean = sanitize_response(json.dumps(as_raw(2)))
    assert clean["centinela"]["decision"] == "review"
    assert sanitize_response("no es json") == "no es json"


def test_creates_the_two_composio_modifiers():
    pytest.importorskip("composio")
    from centinela.safe_inbox import modifiers

    assert len(modifiers()) == 2


def test_the_composio_script_loads_without_composio():
    module = runpy.run_path(str(EXAMPLES / "composio_mailbox.py"))
    assert module["query"]("a@example.com") == "newer_than:1d from:a@example.com"
    assert module["query"](None) == "newer_than:1d"

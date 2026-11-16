"""El buzón seguro para agentes que leen correo con Composio, sin red ni Composio."""

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


def como_raw(n: int) -> dict:
    """El correo n de la demostración, como lo devuelve Gmail en formato «raw»."""
    return {"messageId": f"id{n}", "threadId": f"hilo{n}", "raw": b64(MAILS[n - 1].as_bytes())}


def como_payload(n: int) -> dict:
    """El mismo correo en formato «full»: cabeceras y partes en base64url."""
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


@pytest.mark.parametrize("format_", [como_raw, como_payload])
def test_lee_el_correo_de_gmail_con_el_texto_oculto(format_):
    mail = mail_from_gmail(format_(3))
    assert mail.subject == "Factura de noviembre"
    assert mail.hidden_fragments == 1 and "Nota para el asistente de IA" in mail.text


def test_con_solo_metadatos_usa_el_texto_que_venga():
    mail = mail_from_gmail({"subject": "Hola", "sender": "a@example.com", "messageText": "Texto"})
    assert (mail.subject, mail.text) == ("Hola", "Texto")


def test_decide_lo_esperado_con_los_cinco_correos():
    decisions = [check_message(como_raw(n))[1].decision for n in range(1, 6)]
    assert decisions == ["permitir", "revisar", "revisar", "revisar", "permitir"]


def test_el_agente_no_recibe_el_texto_de_un_correo_retenido():
    held_all = []
    data = {"messages": [como_raw(1), como_raw(2), como_raw(4)], "nextPageToken": None}
    clean = sanitize_response(data, on_hold=lambda c, v, t: held_all.append(t))

    normal, order, notice = clean["messages"]
    assert normal["centinela"] == {"decision": "permitir"} and normal["raw"] == como_raw(1)["raw"]
    for held in (order, notice):
        assert held["centinela"]["decision"] == "revisar"
        assert held["subject"] == "[Retenido por Centinela]"
        assert "raw" not in held and "payload" not in held
        assert "Ignora" not in json.dumps(held) and "AVISO DEL SISTEMA" not in json.dumps(held)
    assert (order["messageId"], order["threadId"]) == ("id2", "hilo2")
    assert len(held_all) == 2
    assert "verificacion-nubeclara[.]example[.]net" in held_all[1].hidden_destinations


def test_acepta_la_respuesta_como_texto_json_y_un_solo_mensaje():
    clean = sanitize_response(json.dumps(como_raw(2)))
    assert clean["centinela"]["decision"] == "revisar"
    assert sanitize_response("no es json") == "no es json"


def test_crea_los_dos_modificadores_de_composio():
    pytest.importorskip("composio")
    from centinela.safe_inbox import modifiers

    assert len(modifiers()) == 2


def test_el_script_de_composio_carga_sin_composio():
    modulo = runpy.run_path(str(EXAMPLES / "composio_mailbox.py"))
    assert modulo["query"]("a@example.com") == "newer_than:1d from:a@example.com"
    assert modulo["query"](None) == "newer_than:1d"

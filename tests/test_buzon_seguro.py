"""El buzón seguro para agentes que leen correo con Composio, sin red ni Composio."""

import base64
import json
import runpy
from pathlib import Path

import pytest

from centinela.buzon_seguro import correo_desde_gmail, limpiar_respuesta, revisar_mensaje

EJEMPLOS = Path(__file__).resolve().parent.parent / "ejemplos"
ENVIO = runpy.run_path(str(EJEMPLOS / "enviar_pruebas.py"))
CORREOS = ENVIO["construir_mensajes"]("pruebas@example.com", "agente@example.org")


def b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def como_raw(n: int) -> dict:
    """El correo n de la demostración, como lo devuelve Gmail en formato «raw»."""
    return {"messageId": f"id{n}", "threadId": f"hilo{n}", "raw": b64(CORREOS[n - 1].as_bytes())}


def como_payload(n: int) -> dict:
    """El mismo correo en formato «full»: cabeceras y partes en base64url."""
    mensaje = CORREOS[n - 1]
    partes = [
        {"mimeType": p.get_content_type(), "body": {"data": b64(p.get_content().encode())}}
        for p in mensaje.walk()
        if p.get_content_maintype() == "text"
    ]
    cabeceras = [
        {"name": "From", "value": mensaje["From"]},
        {"name": "Subject", "value": mensaje["Subject"]},
    ]
    return {"messageId": f"id{n}", "payload": {"headers": cabeceras, "parts": partes}}


@pytest.mark.parametrize("formato", [como_raw, como_payload])
def test_lee_el_correo_de_gmail_con_el_texto_oculto(formato):
    correo = correo_desde_gmail(formato(3))
    assert correo.asunto == "Factura de noviembre"
    assert correo.fragmentos_ocultos == 1 and "Nota para el asistente de IA" in correo.texto


def test_con_solo_metadatos_usa_el_texto_que_venga():
    correo = correo_desde_gmail(
        {"subject": "Hola", "sender": "a@example.com", "messageText": "Texto"}
    )
    assert (correo.asunto, correo.texto) == ("Hola", "Texto")


def test_decide_lo_esperado_con_los_cinco_correos():
    decisiones = [revisar_mensaje(como_raw(n))[1].decision for n in range(1, 6)]
    assert decisiones == ["permitir", "revisar", "revisar", "revisar", "permitir"]


def test_el_agente_no_recibe_el_texto_de_un_correo_retenido():
    retenidos = []
    datos = {"messages": [como_raw(1), como_raw(2), como_raw(4)], "nextPageToken": None}
    limpio = limpiar_respuesta(datos, al_retener=lambda c, v, t: retenidos.append(t))

    normal, orden, aviso = limpio["messages"]
    assert normal["centinela"] == {"decision": "permitir"} and normal["raw"] == como_raw(1)["raw"]
    for retenido in (orden, aviso):
        assert retenido["centinela"]["decision"] == "revisar"
        assert retenido["subject"] == "[Retenido por Centinela]"
        assert "raw" not in retenido and "payload" not in retenido
        assert "Ignora" not in json.dumps(retenido) and "AVISO DEL SISTEMA" not in json.dumps(
            retenido
        )
    assert (orden["messageId"], orden["threadId"]) == ("id2", "hilo2")
    assert len(retenidos) == 2
    assert "verificacion-nubeclara[.]example[.]net" in retenidos[1].destinos_ocultos


def test_acepta_la_respuesta_como_texto_json_y_un_solo_mensaje():
    limpio = limpiar_respuesta(json.dumps(como_raw(2)))
    assert limpio["centinela"]["decision"] == "revisar"
    assert limpiar_respuesta("no es json") == "no es json"


def test_crea_los_dos_modificadores_de_composio():
    pytest.importorskip("composio")
    from centinela.buzon_seguro import modificadores

    assert len(modificadores()) == 2


def test_el_script_de_composio_carga_sin_composio():
    modulo = runpy.run_path(str(EJEMPLOS / "composio_buzon.py"))
    assert modulo["consulta"]("a@example.com") == "newer_than:1d from:a@example.com"
    assert modulo["consulta"](None) == "newer_than:1d"

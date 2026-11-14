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

from centinela.correo import Correo, leer_correo, texto_a_revisar
from centinela.detectores.reglas import DetectorReglas
from centinela.etiquetas import ETIQUETAS_LEADS
from centinela.guardia import Guardia
from centinela.revision import TarjetaRevision, crear_tarjeta
from centinela.tipos import Veredicto

#: Herramientas de Composio que entregan correos completos al agente.
HERRAMIENTAS_DE_LECTURA = (
    "GMAIL_FETCH_EMAILS",
    "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
    "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
)
#: Campos que se conservan de un correo retenido: solo identificadores y metadatos.
_CAMPOS_SEGUROS = ("messageId", "id", "threadId", "labelIds", "messageTimestamp", "internalDate")

AlRetener = Callable[[Correo, Veredicto, TarjetaRevision], None]


def _b64url(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _cabecera(payload: dict, nombre: str) -> str:
    for cabecera in payload.get("headers") or []:
        if str(cabecera.get("name", "")).lower() == nombre.lower():
            return str(cabecera.get("value", ""))
    return ""


def _partes(payload: dict):
    yield payload
    for parte in payload.get("parts") or []:
        if isinstance(parte, dict):
            yield from _partes(parte)


def _desde_payload(mensaje: dict, payload: dict) -> Correo | None:
    """Rehace un correo MIME mínimo con las partes de texto del formato «full» de Gmail."""
    plano = html = ""
    for parte in _partes(payload):
        datos = (parte.get("body") or {}).get("data")
        if not datos:
            continue
        contenido = _b64url(datos).decode("utf-8", errors="replace")
        tipo = str(parte.get("mimeType", "")).lower()
        if tipo == "text/plain" and not plano:
            plano = contenido
        elif tipo == "text/html" and not html:
            html = contenido
    if not (plano or html):
        return None
    nuevo = EmailMessage()
    try:
        nuevo["From"] = _cabecera(payload, "From") or str(mensaje.get("sender", ""))
        nuevo["Subject"] = _cabecera(payload, "Subject") or str(mensaje.get("subject", ""))
    except (ValueError, TypeError):
        pass  # una cabecera mal formada no impide revisar el cuerpo
    if plano:
        nuevo.set_content(plano)
        if html:
            nuevo.add_alternative(html, subtype="html")
    else:
        nuevo.set_content(html, subtype="html")
    return leer_correo(nuevo)


def correo_desde_gmail(mensaje: dict[str, Any]) -> Correo:
    """Arma un ``Correo`` con lo que devuelve Gmail por Composio: «raw», «payload» o campos sueltos."""
    if mensaje.get("raw"):
        return leer_correo(_b64url(str(mensaje["raw"])))
    payload = mensaje.get("payload")
    if isinstance(payload, dict):
        correo = _desde_payload(mensaje, payload)
        if correo:
            return correo
    texto = next(
        (str(mensaje[c]) for c in ("messageText", "preview", "snippet") if mensaje.get(c)), ""
    )
    return Correo(
        remitente=str(mensaje.get("sender", "")),
        asunto=str(mensaje.get("subject", "")),
        texto=texto,
        enlaces=(),
        adjuntos=(),
    )


def revisar_mensaje(
    mensaje: dict[str, Any], guardia: Guardia | None = None
) -> tuple[Correo, Veredicto, TarjetaRevision | None]:
    """Revisa un correo de Gmail. Si va a revisión, devuelve también su tarjeta."""
    guardia = guardia or Guardia([DetectorReglas(etiquetas=ETIQUETAS_LEADS)])
    correo = correo_desde_gmail(mensaje)
    texto = texto_a_revisar(correo)
    veredicto = guardia.revisar(texto)
    tarjeta = None
    if veredicto.decision == "revisar":
        tarjeta = crear_tarjeta(texto, veredicto, enlaces_ocultos=correo.enlaces)
    return correo, veredicto, tarjeta


def limpiar_mensaje(
    mensaje: dict[str, Any], guardia: Guardia | None = None, al_retener: AlRetener | None = None
) -> dict[str, Any]:
    """Deja pasar un correo normal y retiene uno sospechoso: el agente no recibe su texto."""
    correo, veredicto, tarjeta = revisar_mensaje(mensaje, guardia)
    if tarjeta is None:
        return {**mensaje, "centinela": {"decision": "permitir"}}
    if al_retener:
        al_retener(correo, veredicto, tarjeta)
    retenido = {k: mensaje[k] for k in _CAMPOS_SEGUROS if k in mensaje}
    retenido.update(
        sender=parseaddr(correo.remitente)[1],
        subject="[Retenido por Centinela]",
        messageText=(
            "Centinela retuvo este correo para revisión humana y no entrega su contenido. "
            f"Motivo: {veredicto.aviso}"
        ),
        centinela={"decision": "revisar", "aviso": veredicto.aviso},
    )
    return retenido


def limpiar_respuesta(
    datos: Any, guardia: Guardia | None = None, al_retener: AlRetener | None = None
) -> Any:
    """Aplica ``limpiar_mensaje`` a cada correo de una respuesta de las herramientas de Gmail."""
    if isinstance(datos, str):
        try:
            datos = json.loads(datos)
        except ValueError:
            return datos
    if not isinstance(datos, dict):
        return datos
    for clave in ("messages", "emails"):
        if isinstance(datos.get(clave), list):
            return {
                **datos,
                clave: [
                    limpiar_mensaje(m, guardia, al_retener) if isinstance(m, dict) else m
                    for m in datos[clave]
                ],
            }
    if any(k in datos for k in ("raw", "payload", "messageText")):
        return limpiar_mensaje(datos, guardia, al_retener)
    return datos


def modificadores(guardia: Guardia | None = None, al_retener: AlRetener | None = None) -> list:
    """Modificadores de Composio que ponen a Centinela delante de las herramientas de lectura.

    - Antes: pide a Gmail el contenido completo, para que el guardia revise el cuerpo y no solo
      el asunto.
    - Después: revisa cada correo y retiene los sospechosos antes de que los vea el agente.
    """
    from composio import after_execute, before_execute

    @before_execute(tools=["GMAIL_FETCH_EMAILS"])
    def pedir_contenido(tool: str, toolkit: str, params: Any) -> Any:
        params["arguments"]["verbose"] = True
        params["arguments"]["include_payload"] = True
        return params

    @after_execute(tools=list(HERRAMIENTAS_DE_LECTURA))
    def buzon_seguro(tool: str, toolkit: str, response: Any) -> Any:
        if not response.get("successful") or response.get("data") is None:
            return response
        return {**response, "data": limpiar_respuesta(response["data"], guardia, al_retener)}

    return [pedir_contenido, buzon_seguro]

"""Demostración con Composio: el buzón de Gmail de un agente de IA, con Centinela delante.

Necesita en .env:

    COMPOSIO_API_KEY=...   # platform.composio.dev → Settings → API Keys
    COMPOSIO_USUARIO=...   # el User ID con el que se conectó la cuenta de Gmail (ver «cuentas»)

Comandos::

    uv run --group composio python ejemplos/composio_buzon.py conectar
    uv run --group composio python ejemplos/composio_buzon.py cuentas
    uv run --group composio python ejemplos/composio_buzon.py enviar [--para correo] [--solo 2 4]
    uv run --group composio python ejemplos/composio_buzon.py vigilar [--desde correo] [--etiquetar]
    uv run --group composio python ejemplos/composio_buzon.py agente [--desde correo]

- conectar: da el enlace para conectar la cuenta de Gmail al proyecto, con la autenticación
  que administra Composio, y espera a que la autoricen.
- cuentas: las cuentas de Gmail conectadas en Composio, con su User ID.
- enviar: manda los cinco correos ficticios de la demostración, por defecto al mismo buzón.
- vigilar: revisa cada correo nuevo. Con --etiquetar, saca los sospechosos de la bandeja de
  entrada y les pone la etiqueta Centinela-Cuarentena.
- agente: muestra lo que recibe un agente que lee su correo por Composio con el buzón seguro.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from enviar_pruebas import CORREOS
from vigilar_buzon import LINEA, mostrar

from centinela import ETIQUETAS_LEADS, DetectorReglas, Guardia, texto_de_tarjeta
from centinela._env import cargar_env
from centinela.buzon_seguro import modificadores, revisar_mensaje

ETIQUETA = "Centinela-Cuarentena"


class Gmail:
    """Ejecuta herramientas de Gmail de Composio en nombre de un usuario."""

    def __init__(self, usuario: str):
        from composio import Composio

        self.version = os.environ.get("COMPOSIO_GMAIL_VERSION", "latest")
        self.composio = Composio(
            api_key=os.environ["COMPOSIO_API_KEY"], toolkit_versions={"gmail": self.version}
        )
        self.usuario = usuario

    def ejecutar(self, herramienta: str, argumentos: dict, modifiers: list | None = None):
        extra: dict = {"modifiers": modifiers} if modifiers else {}
        if self.version == "latest":
            extra["dangerously_skip_version_check"] = True
        respuesta = self.composio.tools.execute(
            herramienta, argumentos, user_id=self.usuario, **extra
        )
        if not respuesta.get("successful"):
            raise RuntimeError(f"{herramienta}: {respuesta.get('error')}")
        datos = respuesta.get("data")
        if isinstance(datos, str):
            try:
                datos = json.loads(datos)
            except ValueError:
                pass
        return datos

    def direccion(self) -> str:
        perfil = self.ejecutar("GMAIL_GET_PROFILE", {}) or {}
        return str(perfil.get("emailAddress") or perfil.get("email_address") or "")

    def ids(self, consulta: str) -> list[str]:
        datos = self.ejecutar(
            "GMAIL_FETCH_EMAILS",
            {"query": consulta, "max_results": 25, "ids_only": True, "include_spam_trash": True},
        )
        mensajes = (datos or {}).get("messages") or []
        return [
            str(m.get("messageId") or m.get("id"))
            for m in mensajes
            if m.get("messageId") or m.get("id")
        ]

    def etiqueta(self, nombre: str) -> str:
        datos = self.ejecutar("GMAIL_LIST_LABELS", {}) or {}
        for etiqueta in datos.get("labels") or []:
            if etiqueta.get("name") == nombre:
                return str(etiqueta.get("id"))
        creada = self.ejecutar("GMAIL_CREATE_LABEL", {"label_name": nombre}) or {}
        return str(creada.get("id") or creada.get("labelId"))


def consulta(desde: str | None) -> str:
    return "newer_than:1d" + (f" from:{desde}" if desde else "")


def conectar(usuario: str) -> int:
    from composio import Composio

    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    solicitud = composio.toolkits.authorize(user_id=usuario, toolkit="gmail")
    print("Abran este enlace, entren con la cuenta de Gmail de pruebas y autoricen el acceso:\n")
    print(solicitud.redirect_url)
    print("\nEsperando la autorización (hasta 5 minutos)…")
    sys.stdout.flush()
    cuenta = solicitud.wait_for_connection(300)
    print(f"Conectada: {getattr(cuenta, 'id', '?')} · User ID: {usuario}")
    return 0


def cuentas() -> int:
    from composio import Composio

    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    lista = composio.connected_accounts.list(toolkit_slugs=["gmail"])
    items = getattr(lista, "items", None) or []
    if not items:
        print("No hay cuentas de Gmail conectadas en este proyecto de Composio.")
        return 1
    for cuenta in items:  # solo campos que no son secretos
        usuario = getattr(cuenta, "user_id", None) or getattr(cuenta, "userId", None) or "?"
        print(
            f"User ID: {usuario} · cuenta conectada: {getattr(cuenta, 'id', '?')} · estado: {getattr(cuenta, 'status', '?')}"
        )
    return 0


def enviar(gmail: Gmail, para: str | None, solo: list[int] | None) -> int:
    destino = para or gmail.direccion()
    if not destino:
        print("No sé a quién enviar: usa --para.", file=sys.stderr)
        return 1
    for n in solo or range(1, len(CORREOS) + 1):
        asunto, plano, html, _ = CORREOS[n - 1]
        gmail.ejecutar(
            "GMAIL_SEND_EMAIL",
            {
                "recipient_email": destino,
                "subject": asunto,
                "body": html or plano,
                "is_html": bool(html),
                "include_signature": False,
            },
        )
        print(f"Enviado {n}: {asunto} → {destino}")
        time.sleep(1)
    return 0


def vigilar(gmail: Gmail, guardia: Guardia, desde: str | None, etiquetar: bool, cada: float) -> int:
    buscar = consulta(desde)
    vistos = set(gmail.ids(buscar))  # solo cuentan los correos que lleguen desde ahora
    etiqueta = gmail.etiqueta(ETIQUETA) if etiquetar else None
    filtro = f", solo correos de {desde}" if desde else ""
    print(
        f"Vigilando el buzón de {gmail.direccion() or gmail.usuario} por Composio{filtro}. Ctrl+C para salir."
    )
    while True:
        for mensaje_id in gmail.ids(buscar):
            if mensaje_id in vistos:
                continue
            vistos.add(mensaje_id)
            mensaje = gmail.ejecutar(
                "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID", {"message_id": mensaje_id, "format": "raw"}
            )
            correo, veredicto, tarjeta = revisar_mensaje(mensaje or {}, guardia)
            mostrar(
                "Gmail (Composio)",
                correo,
                veredicto,
                texto_de_tarjeta(tarjeta) if tarjeta else None,
            )
            if tarjeta and etiqueta:
                gmail.ejecutar(
                    "GMAIL_ADD_LABEL_TO_EMAIL",
                    {
                        "message_id": mensaje_id,
                        "add_label_ids": [etiqueta],
                        "remove_label_ids": ["INBOX"],
                    },
                )
                print(f"\n→ Fuera de la bandeja de entrada, con la etiqueta {ETIQUETA}.")
            sys.stdout.flush()
        time.sleep(cada)


def agente(gmail: Gmail, guardia: Guardia, desde: str | None) -> int:
    retenidos = []
    datos = gmail.ejecutar(
        "GMAIL_FETCH_EMAILS",
        {"query": consulta(desde), "max_results": 10},
        modifiers=modificadores(guardia, al_retener=lambda c, v, t: retenidos.append(t)),
    )
    print("Lo que recibe el agente al leer su correo por Composio, con el buzón seguro:\n")
    for mensaje in (datos or {}).get("messages") or []:
        decision = (mensaje.get("centinela") or {}).get("decision", "?")
        texto = str(mensaje.get("messageText") or mensaje.get("preview") or "").strip()
        print(LINEA)
        print(f"Asunto: {mensaje.get('subject')} · Centinela: {decision}")
        print(texto[:400] + ("…" if len(texto) > 400 else ""))
    if retenidos:
        print(f"\n{LINEA}\nPara la persona que revisa, {len(retenidos)} tarjeta(s):\n")
        for tarjeta in retenidos:
            print(texto_de_tarjeta(tarjeta) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("conectar", help="conecta la cuenta de Gmail al proyecto de Composio")
    sub.add_parser("cuentas", help="cuentas de Gmail conectadas en Composio")
    p_enviar = sub.add_parser("enviar", help="envía los correos ficticios de la demostración")
    p_enviar.add_argument("--para", help="destinatario (por defecto, el mismo buzón)")
    p_enviar.add_argument("--solo", type=int, nargs="+", choices=range(1, len(CORREOS) + 1))
    p_vigilar = sub.add_parser("vigilar", help="revisa cada correo nuevo")
    p_vigilar.add_argument("--desde", help="revisa solo los correos de esta dirección")
    p_vigilar.add_argument("--etiquetar", action="store_true", help="aparta los sospechosos")
    p_vigilar.add_argument("--cada", type=float, default=8, help="segundos entre revisiones")
    p_agente = sub.add_parser("agente", help="lo que recibe un agente con el buzón seguro")
    p_agente.add_argument("--desde", help="solo los correos de esta dirección")
    for p in (p_vigilar, p_agente):
        p.add_argument("--claude", action="store_true", help="suma a Claude como revisor")
    args = parser.parse_args(argv)

    cargar_env()
    if not os.environ.get("COMPOSIO_API_KEY"):
        print("Falta COMPOSIO_API_KEY en .env.", file=sys.stderr)
        return 1
    if os.environ["COMPOSIO_API_KEY"].startswith("ck_"):
        print(
            "COMPOSIO_API_KEY es una clave de Composio Connect (ck_), que sirve para su MCP. "
            "Este script usa la plataforma de desarrolladores: pongan la clave de un proyecto "
            "(empieza por ak_, en platform.composio.dev → Settings → API Keys).",
            file=sys.stderr,
        )
        return 1
    if args.comando == "cuentas":
        return cuentas()
    usuario = os.environ.get("COMPOSIO_USUARIO")
    if not usuario:
        print("Falta COMPOSIO_USUARIO en .env (el comando «cuentas» lo muestra).", file=sys.stderr)
        return 1
    if args.comando == "conectar":
        return conectar(usuario)
    gmail = Gmail(usuario)
    if args.comando == "enviar":
        return enviar(gmail, args.para, args.solo)
    detectores = [DetectorReglas(etiquetas=ETIQUETAS_LEADS)]
    if args.claude:
        from centinela import DetectorLLM
        from centinela.proveedores.anthropic import ProveedorAnthropic

        detectores.append(DetectorLLM(ProveedorAnthropic()))
    guardia = Guardia(detectores)
    try:
        if args.comando == "vigilar":
            return vigilar(gmail, guardia, args.desde, args.etiquetar, args.cada)
        return agente(gmail, guardia, args.desde)
    except KeyboardInterrupt:
        print("\nListo.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

from send_test_emails import MAILS
from watch_mailbox import LINE, show

from centinela import LEAD_LABELS, Guard, RulesDetector, render_card
from centinela._env import load_env
from centinela.safe_inbox import check_message, modifiers

LABEL = "Centinela-Cuarentena"


class Gmail:
    """Ejecuta herramientas de Gmail de Composio en nombre de un usuario."""

    def __init__(self, user: str):
        from composio import Composio

        self.version = os.environ.get("COMPOSIO_GMAIL_VERSION", "latest")
        self.composio = Composio(
            api_key=os.environ["COMPOSIO_API_KEY"], toolkit_versions={"gmail": self.version}
        )
        self.user = user

    def execute(self, tool: str, arguments: dict, modifiers: list | None = None):
        extra: dict = {"modifiers": modifiers} if modifiers else {}
        if self.version == "latest":
            extra["dangerously_skip_version_check"] = True
        response = self.composio.tools.execute(tool, arguments, user_id=self.user, **extra)
        if not response.get("successful"):
            raise RuntimeError(f"{tool}: {response.get('error')}")
        data = response.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                pass
        return data

    def address(self) -> str:
        profile = self.execute("GMAIL_GET_PROFILE", {}) or {}
        return str(profile.get("emailAddress") or profile.get("email_address") or "")

    def ids(self, query: str) -> list[str]:
        data = self.execute(
            "GMAIL_FETCH_EMAILS",
            {"query": query, "max_results": 25, "ids_only": True, "include_spam_trash": True},
        )
        messages = (data or {}).get("messages") or []
        return [
            str(m.get("messageId") or m.get("id"))
            for m in messages
            if m.get("messageId") or m.get("id")
        ]

    def label(self, name: str) -> str:
        data = self.execute("GMAIL_LIST_LABELS", {}) or {}
        for label in data.get("labels") or []:
            if label.get("name") == name:
                return str(label.get("id"))
        created = self.execute("GMAIL_CREATE_LABEL", {"label_name": name}) or {}
        return str(created.get("id") or created.get("labelId"))


def query(from_address: str | None) -> str:
    return "newer_than:1d" + (f" from:{from_address}" if from_address else "")


def connect(user: str) -> int:
    from composio import Composio

    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    request = composio.toolkits.authorize(user_id=user, toolkit="gmail")
    print("Abran este enlace, entren con la cuenta de Gmail de pruebas y autoricen el acceso:\n")
    print(request.redirect_url)
    print("\nEsperando la autorización (hasta 5 minutos)…")
    sys.stdout.flush()
    tally = request.wait_for_connection(300)
    print(f"Conectada: {getattr(tally, 'id', '?')} · User ID: {user}")
    return 0


def accounts() -> int:
    from composio import Composio

    composio = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    joined = composio.connected_accounts.list(toolkit_slugs=["gmail"])
    items = getattr(joined, "items", None) or []
    if not items:
        print("No hay cuentas de Gmail conectadas en este proyecto de Composio.")
        return 1
    for tally in items:  # solo campos que no son secretos
        user = getattr(tally, "user_id", None) or getattr(tally, "userId", None) or "?"
        print(
            f"User ID: {user} · cuenta conectada: {getattr(tally, 'id', '?')} · estado: {getattr(tally, 'status', '?')}"
        )
    return 0


def send(gmail: Gmail, recipient: str | None, only: list[int] | None) -> int:
    recipient_address = recipient or gmail.address()
    if not recipient_address:
        print("No sé a quién enviar: usa --para.", file=sys.stderr)
        return 1
    for n in only or range(1, len(MAILS) + 1):
        subject, plain, html, _ = MAILS[n - 1]
        gmail.execute(
            "GMAIL_SEND_EMAIL",
            {
                "recipient_email": recipient_address,
                "subject": subject,
                "body": html or plain,
                "is_html": bool(html),
                "include_signature": False,
            },
        )
        print(f"Enviado {n}: {subject} → {recipient_address}")
        time.sleep(1)
    return 0


def watch(
    gmail: Gmail, guard: Guard, from_address: str | None, apply_label: bool, each: float
) -> int:
    search = query(from_address)
    seen = set(gmail.ids(search))  # solo cuentan los correos que lleguen desde ahora
    label = gmail.label(LABEL) if apply_label else None
    filter_lines = f", solo correos de {from_address}" if from_address else ""
    print(
        f"Vigilando el buzón de {gmail.address() or gmail.user} por Composio{filter_lines}. Ctrl+C para salir."
    )
    while True:
        for message_id in gmail.ids(search):
            if message_id in seen:
                continue
            seen.add(message_id)
            message = gmail.execute(
                "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID", {"message_id": message_id, "format": "raw"}
            )
            mail, verdict, card = check_message(message or {}, guard)
            show(
                "Gmail (Composio)",
                mail,
                verdict,
                render_card(card) if card else None,
            )
            if card and label:
                gmail.execute(
                    "GMAIL_ADD_LABEL_TO_EMAIL",
                    {
                        "message_id": message_id,
                        "add_label_ids": [label],
                        "remove_label_ids": ["INBOX"],
                    },
                )
                print(f"\n→ Fuera de la bandeja de entrada, con la etiqueta {LABEL}.")
            sys.stdout.flush()
        time.sleep(each)


def agent(gmail: Gmail, guard: Guard, from_address: str | None) -> int:
    held_all = []
    data = gmail.execute(
        "GMAIL_FETCH_EMAILS",
        {"query": query(from_address), "max_results": 10},
        modifiers=modifiers(guard, on_hold=lambda c, v, t: held_all.append(t)),
    )
    print("Lo que recibe el agente al leer su correo por Composio, con el buzón seguro:\n")
    for message in (data or {}).get("messages") or []:
        decision = (message.get("centinela") or {}).get("decision", "?")
        text = str(message.get("messageText") or message.get("preview") or "").strip()
        print(LINE)
        print(f"Asunto: {message.get('subject')} · Centinela: {decision}")
        print(text[:400] + ("…" if len(text) > 400 else ""))
    if held_all:
        print(f"\n{LINE}\nPara la persona que revisa, {len(held_all)} tarjeta(s):\n")
        for card in held_all:
            print(render_card(card) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("connect", help="conecta la cuenta de Gmail al proyecto de Composio")
    sub.add_parser("accounts", help="cuentas de Gmail conectadas en Composio")
    p_send = sub.add_parser("send", help="envía los correos ficticios de la demostración")
    p_send.add_argument("--recipient", help="destinatario (por defecto, el mismo buzón)")
    p_send.add_argument("--only", type=int, nargs="+", choices=range(1, len(MAILS) + 1))
    p_watch = sub.add_parser("watch", help="revisa cada correo nuevo")
    p_watch.add_argument("--from-address", help="revisa solo los correos de esta dirección")
    p_watch.add_argument("--apply-label", action="store_true", help="aparta los sospechosos")
    p_watch.add_argument("--each", type=float, default=8, help="segundos entre revisiones")
    p_agent = sub.add_parser("agent", help="lo que recibe un agente con el buzón seguro")
    p_agent.add_argument("--from-address", help="solo los correos de esta dirección")
    for p in (p_watch, p_agent):
        p.add_argument("--claude", action="store_true", help="suma a Claude como revisor")
    args = parser.parse_args(argv)

    load_env()
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
    if args.command == "cuentas":
        return accounts()
    user = os.environ.get("COMPOSIO_USUARIO")
    if not user:
        print("Falta COMPOSIO_USUARIO en .env (el comando «cuentas» lo muestra).", file=sys.stderr)
        return 1
    if args.command == "conectar":
        return connect(user)
    gmail = Gmail(user)
    if args.command == "enviar":
        return send(gmail, args.recipient, args.only)
    detectors = [RulesDetector(labels=LEAD_LABELS)]
    if args.claude:
        from centinela import LLMDetector
        from centinela.providers.anthropic import AnthropicProvider

        detectors.append(LLMDetector(AnthropicProvider()))
    guard = Guard(detectors)
    try:
        if args.command == "vigilar":
            return watch(gmail, guard, args.from_address, args.apply_label, args.each)
        return agent(gmail, guard, args.from_address)
    except KeyboardInterrupt:
        print("\nListo.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

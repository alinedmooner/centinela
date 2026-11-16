"""Bot de demostración: vigila un buzón por IMAP y revisa con Centinela cada correo nuevo.

- Solo lee los correos que lleguen después de arrancar.
- Con --solo-de, solo los de esa dirección: el filtro lo hace el servidor, así que el bot ni
  siquiera abre los demás correos del buzón.
- Funciona sin clave de IA, con las reglas.
- Sin --mover no cambia nada en el buzón (lo abre en modo de solo lectura). Con --mover, los
  correos sospechosos pasan a la carpeta Centinela-Cuarentena.

Credenciales en .env (con Gmail, contraseña de aplicación, no la contraseña normal):

    BUZON_USUARIO=buzon-del-bot@...
    BUZON_CLAVE=...

Uso::

    uv run python ejemplos/vigilar_buzon.py --solo-de cuenta-de-pruebas@...
    uv run python ejemplos/vigilar_buzon.py --solo-de cuenta-de-pruebas@... --mover
"""

from __future__ import annotations

import argparse
import imaplib
import os
import re
import ssl
import sys
import time

from centinela import (
    LEAD_LABELS,
    Guard,
    RulesDetector,
    Verdict,
    create_card,
    render_card,
)
from centinela._env import load_env
from centinela.mail import Mail, read_mail, text_to_check

IMAP = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "zoho.com": "imap.zoho.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
}
QUARANTINE = "Centinela-Cuarentena"
LINE = "─" * 72


def quotes(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def server(user: str, value: str | None = None) -> str:
    host = value or IMAP.get(user.rsplit("@", 1)[-1].lower())
    if not host:
        raise ValueError("No conozco el servidor IMAP de esa cuenta: pon BUZON_IMAP=host en .env.")
    return host


def process(raw: bytes, guard: Guard) -> tuple[Mail, Verdict, str | None]:
    """Revisa un correo. Si va a revisión, devuelve también la tarjeta para quien revisa."""
    mail = read_mail(raw)
    text = text_to_check(mail)
    verdict = guard.check(text)
    card = None
    if verdict.decision == "revisar":
        card = render_card(create_card(text, verdict, hidden_links=mail.links))
    return mail, verdict, card


def show(folder: str, mail: Mail, verdict: Verdict, card: str | None) -> None:
    print(LINE)
    print(f"Correo nuevo en {folder}")
    print(f"De: {mail.sender}")
    print(f"Asunto: {mail.subject}")
    if mail.hidden_fragments:
        print(f"Trae {mail.hidden_fragments} fragmento(s) de texto oculto en el HTML.")
    if verdict.decision == "permitir":
        print("Decisión: permitir. El asistente puede leerlo.")
    else:
        print("Decisión: revisar. Va a la sala de revisión; el asistente no lo lee.\n")
        print(card)
    sys.stdout.flush()


def spam_folder(imap: imaplib.IMAP4) -> str | None:
    """La carpeta de correo no deseado, por su atributo \\Junk (el nombre cambia por idioma)."""
    _, rows = imap.list()
    for row in rows or []:
        if not isinstance(row, bytes):
            continue
        m = re.match(
            r'\((?P<attrs>[^)]*)\) (?:"[^"]*"|NIL) (?P<nombre>.+)$', row.decode("utf-8", "replace")
        )
        if m and "\\Junk" in m.group("attrs"):
            name = m.group("nombre").strip()
            return name[1:-1] if name.startswith('"') else name
    return None


def uid_siguiente(imap: imaplib.IMAP4, folder: str) -> int:
    _, data = imap.status(quotes(folder), "(UIDNEXT)")
    m = re.search(rb"UIDNEXT (\d+)", data[0] or b"")
    return int(m.group(1)) if m else 1


def move(imap: imaplib.IMAP4, uid: bytes) -> None:
    if "MOVE" in imap.capabilities:
        imap.uid("MOVE", uid, quotes(QUARANTINE))
        return
    imap.uid("COPY", uid, quotes(QUARANTINE))
    imap.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
    if "UIDPLUS" in imap.capabilities:  # borra solo este correo, nunca otros ya marcados
        imap.uid("EXPUNGE", uid)


def connect(user: str) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(
        server(user, os.environ.get("BUZON_IMAP")),
        993,
        ssl_context=ssl.create_default_context(),
    )
    imap.login(user, os.environ["BUZON_CLAVE"])
    return imap


def watch(args: argparse.Namespace, guard: Guard) -> None:
    user = os.environ["BUZON_USUARIO"]
    imap = connect(user)
    folders = ["INBOX"]
    spam = spam_folder(imap)
    if spam:
        folders.append(spam)
    if args.move:
        imap.create(quotes(QUARANTINE))  # si ya existe, el servidor responde NO y no pasa nada
    last = {c: uid_siguiente(imap, c) - 1 for c in folders}
    filter_lines = f", solo correos de {args.only_from}" if args.only_from else ""
    print(f"Vigilando {' y '.join(folders)} de {user}{filter_lines}. Ctrl+C para salir.")

    while True:
        try:
            for folder in folders:
                imap.select(quotes(folder), readonly=not args.move)
                criteria = ["UID", f"{last[folder] + 1}:*"]
                if args.only_from:
                    criteria += ["FROM", quotes(args.only_from)]
                _, data = imap.uid("SEARCH", *criteria)
                for uid in (data[0] or b"").split():
                    if int(uid) <= last[folder]:
                        continue
                    _, parts = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                    raw = next(p[1] for p in parts if isinstance(p, tuple))
                    mail, verdict, card = process(raw, guard)
                    show(folder, mail, verdict, card)
                    if card and args.move:
                        move(imap, uid)
                        print(f"\n→ Movido a la carpeta {QUARANTINE}.")
                    last[folder] = max(last[folder], int(uid))
            time.sleep(args.each)
        except (imaplib.IMAP4.abort, OSError):
            print(
                "Se perdió la conexión con el servidor; reconecto en 5 segundos.", file=sys.stderr
            )
            time.sleep(5)
            imap = connect(user)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only-from", help="revisa solo los correos que vengan de esta dirección")
    parser.add_argument(
        "--move", action="store_true", help="pasa los sospechosos a la carpeta de cuarentena"
    )
    parser.add_argument("--each", type=float, default=5, help="segundos entre revisiones")
    parser.add_argument("--claude", action="store_true", help="suma a Claude como revisor")
    parser.add_argument("--model", default="claude-haiku-5-5")
    args = parser.parse_args(argv)

    load_env()
    missing = [v for v in ("BUZON_USUARIO", "BUZON_CLAVE") if not os.environ.get(v)]
    if missing:
        print("Faltan en .env: " + ", ".join(missing), file=sys.stderr)
        return 1
    detectors = [RulesDetector(labels=LEAD_LABELS)]
    if args.claude:
        from centinela import LLMDetector
        from centinela.providers.anthropic import AnthropicProvider

        detectors.append(LLMDetector(AnthropicProvider(args.model)))
    try:
        watch(args, Guard(detectors))
    except imaplib.IMAP4.error as error:
        print(
            f"El servidor IMAP respondió: {error}. Con Gmail hace falta una contraseña de "
            "aplicación y tener IMAP activado.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

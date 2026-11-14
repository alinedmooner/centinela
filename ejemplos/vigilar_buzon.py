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
    ETIQUETAS_LEADS,
    DetectorReglas,
    Guardia,
    Veredicto,
    crear_tarjeta,
    texto_de_tarjeta,
)
from centinela._env import cargar_env
from centinela.correo import Correo, leer_correo, texto_a_revisar

IMAP = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "zoho.com": "imap.zoho.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
}
CUARENTENA = "Centinela-Cuarentena"
LINEA = "─" * 72


def comillas(nombre: str) -> str:
    return '"' + nombre.replace("\\", "\\\\").replace('"', '\\"') + '"'


def servidor(usuario: str, valor: str | None = None) -> str:
    host = valor or IMAP.get(usuario.rsplit("@", 1)[-1].lower())
    if not host:
        raise ValueError("No conozco el servidor IMAP de esa cuenta: pon BUZON_IMAP=host en .env.")
    return host


def procesar(crudo: bytes, guardia: Guardia) -> tuple[Correo, Veredicto, str | None]:
    """Revisa un correo. Si va a revisión, devuelve también la tarjeta para quien revisa."""
    correo = leer_correo(crudo)
    texto = texto_a_revisar(correo)
    veredicto = guardia.revisar(texto)
    tarjeta = None
    if veredicto.decision == "revisar":
        tarjeta = texto_de_tarjeta(crear_tarjeta(texto, veredicto, enlaces_ocultos=correo.enlaces))
    return correo, veredicto, tarjeta


def mostrar(carpeta: str, correo: Correo, veredicto: Veredicto, tarjeta: str | None) -> None:
    print(LINEA)
    print(f"Correo nuevo en {carpeta}")
    print(f"De: {correo.remitente}")
    print(f"Asunto: {correo.asunto}")
    if correo.fragmentos_ocultos:
        print(f"Trae {correo.fragmentos_ocultos} fragmento(s) de texto oculto en el HTML.")
    if veredicto.decision == "permitir":
        print("Decisión: permitir. El asistente puede leerlo.")
    else:
        print("Decisión: revisar. Va a la sala de revisión; el asistente no lo lee.\n")
        print(tarjeta)
    sys.stdout.flush()


def carpeta_de_spam(imap: imaplib.IMAP4) -> str | None:
    """La carpeta de correo no deseado, por su atributo \\Junk (el nombre cambia por idioma)."""
    _, filas = imap.list()
    for fila in filas or []:
        if not isinstance(fila, bytes):
            continue
        m = re.match(
            r'\((?P<attrs>[^)]*)\) (?:"[^"]*"|NIL) (?P<nombre>.+)$', fila.decode("utf-8", "replace")
        )
        if m and "\\Junk" in m.group("attrs"):
            nombre = m.group("nombre").strip()
            return nombre[1:-1] if nombre.startswith('"') else nombre
    return None


def uid_siguiente(imap: imaplib.IMAP4, carpeta: str) -> int:
    _, datos = imap.status(comillas(carpeta), "(UIDNEXT)")
    m = re.search(rb"UIDNEXT (\d+)", datos[0] or b"")
    return int(m.group(1)) if m else 1


def mover(imap: imaplib.IMAP4, uid: bytes) -> None:
    if "MOVE" in imap.capabilities:
        imap.uid("MOVE", uid, comillas(CUARENTENA))
        return
    imap.uid("COPY", uid, comillas(CUARENTENA))
    imap.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
    if "UIDPLUS" in imap.capabilities:  # borra solo este correo, nunca otros ya marcados
        imap.uid("EXPUNGE", uid)


def conectar(usuario: str) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(
        servidor(usuario, os.environ.get("BUZON_IMAP")),
        993,
        ssl_context=ssl.create_default_context(),
    )
    imap.login(usuario, os.environ["BUZON_CLAVE"])
    return imap


def vigilar(args: argparse.Namespace, guardia: Guardia) -> None:
    usuario = os.environ["BUZON_USUARIO"]
    imap = conectar(usuario)
    carpetas = ["INBOX"]
    spam = carpeta_de_spam(imap)
    if spam:
        carpetas.append(spam)
    if args.mover:
        imap.create(comillas(CUARENTENA))  # si ya existe, el servidor responde NO y no pasa nada
    ultimo = {c: uid_siguiente(imap, c) - 1 for c in carpetas}
    filtro = f", solo correos de {args.solo_de}" if args.solo_de else ""
    print(f"Vigilando {' y '.join(carpetas)} de {usuario}{filtro}. Ctrl+C para salir.")

    while True:
        try:
            for carpeta in carpetas:
                imap.select(comillas(carpeta), readonly=not args.mover)
                criterios = ["UID", f"{ultimo[carpeta] + 1}:*"]
                if args.solo_de:
                    criterios += ["FROM", comillas(args.solo_de)]
                _, datos = imap.uid("SEARCH", *criterios)
                for uid in (datos[0] or b"").split():
                    if int(uid) <= ultimo[carpeta]:
                        continue
                    _, partes = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                    crudo = next(p[1] for p in partes if isinstance(p, tuple))
                    correo, veredicto, tarjeta = procesar(crudo, guardia)
                    mostrar(carpeta, correo, veredicto, tarjeta)
                    if tarjeta and args.mover:
                        mover(imap, uid)
                        print(f"\n→ Movido a la carpeta {CUARENTENA}.")
                    ultimo[carpeta] = max(ultimo[carpeta], int(uid))
            time.sleep(args.cada)
        except (imaplib.IMAP4.abort, OSError):
            print(
                "Se perdió la conexión con el servidor; reconecto en 5 segundos.", file=sys.stderr
            )
            time.sleep(5)
            imap = conectar(usuario)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--solo-de", help="revisa solo los correos que vengan de esta dirección")
    parser.add_argument(
        "--mover", action="store_true", help="pasa los sospechosos a la carpeta de cuarentena"
    )
    parser.add_argument("--cada", type=float, default=5, help="segundos entre revisiones")
    parser.add_argument("--claude", action="store_true", help="suma a Claude como revisor")
    parser.add_argument("--modelo", default="claude-haiku-5-5")
    args = parser.parse_args(argv)

    cargar_env()
    faltan = [v for v in ("BUZON_USUARIO", "BUZON_CLAVE") if not os.environ.get(v)]
    if faltan:
        print("Faltan en .env: " + ", ".join(faltan), file=sys.stderr)
        return 1
    detectores = [DetectorReglas(etiquetas=ETIQUETAS_LEADS)]
    if args.claude:
        from centinela import DetectorLLM
        from centinela.proveedores.anthropic import ProveedorAnthropic

        detectores.append(DetectorLLM(ProveedorAnthropic(args.modelo)))
    try:
        vigilar(args, Guardia(detectores))
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

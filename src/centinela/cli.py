"""Comando de terminal de Centinela.

Códigos de salida de ``revisar`` y ``clasificar``: 0 si el mensaje puede seguir, 2 si
debe verlo una persona, 1 si hubo un error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from centinela import __version__
from centinela._env import cargar_env
from centinela.clasificador import ClasificadorSeguro
from centinela.detectores.reglas import DetectorReglas
from centinela.etiquetas import ETIQUETAS_LEADS, REVISION_HUMANA
from centinela.guardia import Guardia


def _leer_mensaje(args: argparse.Namespace) -> str:
    if args.archivo:
        return Path(args.archivo).read_text(encoding="utf-8")
    if args.texto in (None, "-"):
        return sys.stdin.read()
    return args.texto


def _revisar(args: argparse.Namespace) -> int:
    detectores = [DetectorReglas(etiquetas=ETIQUETAS_LEADS)]
    if args.claude:
        cargar_env()
        from centinela.detectores.llm import DetectorLLM
        from centinela.proveedores.anthropic import ProveedorAnthropic

        detectores.append(DetectorLLM(ProveedorAnthropic(args.modelo)))
    veredicto = Guardia(detectores).revisar(_leer_mensaje(args))
    if args.json:
        print(json.dumps(veredicto.a_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Decisión: {veredicto.decision}")
        print(f"Aviso: {veredicto.aviso}")
        for evidencia in veredicto.evidencias:
            print(f"  - {evidencia}")
    return 2 if veredicto.decision == "revisar" else 0


def _clasificar(args: argparse.Namespace) -> int:
    cargar_env()
    from centinela.proveedores.anthropic import ProveedorAnthropic

    clasificador = ClasificadorSeguro(ProveedorAnthropic(args.modelo))
    resultado = clasificador.clasificar(_leer_mensaje(args))
    if args.json:
        salida = {
            "etiqueta": resultado.etiqueta,
            "motivo": resultado.motivo,
            "etiqueta_modelo": resultado.etiqueta_modelo,
            "aviso": resultado.veredicto.aviso,
        }
        print(json.dumps(salida, ensure_ascii=False, indent=2))
    else:
        print(f"Etiqueta: {resultado.etiqueta} (decidió: {resultado.motivo})")
        print(f"Aviso: {resultado.veredicto.aviso}")
    return 2 if resultado.etiqueta == REVISION_HUMANA else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="centinela",
        description="Guardia para asistentes de IA que leen mensajes en español.",
    )
    parser.add_argument("--version", action="version", version=f"centinela {__version__}")
    sub = parser.add_subparsers(dest="comando")

    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument(
        "texto", nargs="?", help="el mensaje; «-» o nada para leerlo de la entrada estándar"
    )
    comun.add_argument("--archivo", help="lee el mensaje de un archivo")
    comun.add_argument("--json", action="store_true", help="imprime el resultado en JSON")

    revisar = sub.add_parser(
        "revisar", parents=[comun], help="revisa un mensaje con reglas, sin clave ni internet"
    )
    revisar.add_argument(
        "--claude",
        action="store_true",
        help="además de las reglas, consulta a Claude (usa la clave)",
    )
    revisar.add_argument("--modelo", default="claude-haiku-5-5", help="modelo de Claude")
    revisar.set_defaults(funcion=_revisar)

    clasificar = sub.add_parser(
        "clasificar", parents=[comun], help="clasifica un mensaje de un cliente (usa Claude)"
    )
    clasificar.add_argument("--modelo", default="claude-haiku-5-5", help="modelo de Claude")
    clasificar.set_defaults(funcion=_clasificar)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.comando:
        parser.print_help()
        return 0
    try:
        return args.funcion(args)
    except Exception as error:  # noqa: BLE001 - el comando informa el error y sale con 1
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Comando de terminal de Centinela.

Códigos de salida de ``revisar`` y ``clasificar``: 0 si el mensaje puede seguir, 2 si
debe verlo una persona, 1 si hubo un error.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from centinela import __version__
from centinela._env import cargar_env
from centinela.clasificador import ClasificadorSeguro
from centinela.detectores.reglas import DetectorReglas
from centinela.etiquetas import ETIQUETAS_LEADS, REVISION_HUMANA
from centinela.guardia import Guardia
from centinela.proveedores import PROVEEDORES
from centinela.revision import crear_tarjeta, texto_de_tarjeta


def _leer_mensaje(args: argparse.Namespace) -> str:
    if args.archivo:
        return Path(args.archivo).read_text(encoding="utf-8")
    if args.texto in (None, "-"):
        return sys.stdin.read()
    return args.texto


def _etiquetas(args: argparse.Namespace) -> dict[str, str]:
    """Las etiquetas del negocio: las del archivo de --etiquetas o las de ejemplo de un bot de ventas."""
    if not args.etiquetas:
        return dict(ETIQUETAS_LEADS)
    datos = json.loads(Path(args.etiquetas).read_text(encoding="utf-8"))
    validas = (
        isinstance(datos, dict)
        and datos
        and all(
            isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip()
            for k, v in datos.items()
        )
    )
    if not validas:
        raise ValueError(
            'el archivo de etiquetas debe ser un objeto JSON {"nombre": "definición"} con al menos una etiqueta'
        )
    raras = [k for k in datos if not k.isalpha()]
    if raras:
        print(
            "Aviso: usa nombres de una sola palabra, sin espacios ni guiones, para que el guardia "
            f"reconozca un mensaje que intenta imponerlos: {', '.join(raras)}",
            file=sys.stderr,
        )
    return datos


def _proveedor(args: argparse.Namespace):
    """El modelo que eligió la persona: Claude por defecto, o Google u OpenRouter."""
    cargar_env()
    from centinela.proveedores import crear_proveedor

    return crear_proveedor(args.proveedor or "anthropic", args.modelo)


def _revisar(args: argparse.Namespace) -> int:
    detectores = [DetectorReglas(etiquetas=_etiquetas(args))]
    if args.claude or args.proveedor:
        from centinela.detectores.llm import DetectorLLM

        detectores.append(DetectorLLM(_proveedor(args)))
    mensaje = _leer_mensaje(args)
    veredicto = Guardia(detectores).revisar(mensaje)
    tarjeta = None
    if args.tarjeta and veredicto.decision == "revisar":
        tarjeta = crear_tarjeta(mensaje, veredicto)
    if args.json:
        salida = veredicto.a_dict()
        if tarjeta:
            salida["tarjeta"] = asdict(tarjeta)
        print(json.dumps(salida, ensure_ascii=False, indent=2))
    else:
        print(f"Decisión: {veredicto.decision}")
        print(f"Aviso: {veredicto.aviso}")
        for evidencia in veredicto.evidencias:
            print(f"  - {evidencia}")
        if tarjeta:
            print()
            print(texto_de_tarjeta(tarjeta))
    return 2 if veredicto.decision == "revisar" else 0


def _clasificar(args: argparse.Namespace) -> int:
    etiquetas = _etiquetas(args)
    clasificador = ClasificadorSeguro(_proveedor(args), etiquetas=etiquetas)
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
        print(f"Etiquetas posibles, definidas por el negocio: {', '.join(etiquetas)}")
        print(f"Aviso: {resultado.veredicto.aviso}")
    return 2 if resultado.etiqueta == REVISION_HUMANA else 0


AYUDA_MODELO = (
    "modelo del proveedor; por defecto uno barato: claude-haiku-5-5, gemini-3.5-flash-lite "
    "o google/gemma-4-26b-a4b-it (OpenRouter)"
)


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
    comun.add_argument(
        "--etiquetas",
        help='archivo JSON con las etiquetas de tu negocio, {"nombre": "definición"}; sin él se usan las de ejemplo de un bot de ventas (ver ejemplos/)',
    )

    revisar = sub.add_parser(
        "revisar", parents=[comun], help="revisa un mensaje con reglas, sin clave ni internet"
    )
    revisar.add_argument(
        "--claude",
        action="store_true",
        help="además de las reglas, consulta a Claude (usa la clave); igual a --proveedor anthropic",
    )
    revisar.add_argument(
        "--proveedor",
        choices=PROVEEDORES,
        help="además de las reglas, consulta un modelo de este proveedor (usa su clave)",
    )
    revisar.add_argument("--modelo", help=AYUDA_MODELO)
    revisar.add_argument(
        "--tarjeta",
        action="store_true",
        help="si el mensaje va a revisión humana, muestra la tarjeta de la sala de revisión",
    )
    revisar.set_defaults(funcion=_revisar)

    clasificar = sub.add_parser(
        "clasificar",
        parents=[comun],
        help="clasifica un mensaje de un cliente con un modelo (Claude por defecto)",
    )
    clasificar.add_argument(
        "--proveedor", choices=PROVEEDORES, default="anthropic", help="quién pone la etiqueta"
    )
    clasificar.add_argument("--modelo", help=AYUDA_MODELO)
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

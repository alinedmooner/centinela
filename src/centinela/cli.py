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
from centinela._env import load_env
from centinela.classifier import SafeClassifier
from centinela.detectors.rules import RulesDetector
from centinela.guard import Guard
from centinela.labels import HUMAN_REVIEW, LEAD_LABELS
from centinela.providers import PROVIDERS
from centinela.review import create_card, render_card


def _read_message(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.text in (None, "-"):
        return sys.stdin.read()
    return args.text


def _labels(args: argparse.Namespace) -> dict[str, str]:
    """Las etiquetas del negocio: las del archivo de --etiquetas o las de ejemplo de un bot de ventas."""
    if not args.labels:
        return dict(LEAD_LABELS)
    data = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    valid = (
        isinstance(data, dict)
        and data
        and all(
            isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip()
            for k, v in data.items()
        )
    )
    if not valid:
        raise ValueError(
            'el archivo de etiquetas debe ser un objeto JSON {"nombre": "definición"} con al menos una etiqueta'
        )
    odd = [k for k in data if not k.isalpha()]
    if odd:
        print(
            "Aviso: usa nombres de una sola palabra, sin espacios ni guiones, para que el guardia "
            f"reconozca un mensaje que intenta imponerlos: {', '.join(odd)}",
            file=sys.stderr,
        )
    return data


def _provider(args: argparse.Namespace):
    """El modelo que eligió la persona: Claude por defecto, o Google u OpenRouter."""
    load_env()
    from centinela.providers import create_provider

    return create_provider(args.provider or "anthropic", args.model)


def _check(args: argparse.Namespace) -> int:
    detectors = [RulesDetector(labels=_labels(args))]
    if args.claude or args.provider:
        from centinela.detectors.llm import LLMDetector

        detectors.append(LLMDetector(_provider(args)))
    message = _read_message(args)
    verdict = Guard(detectors).check(message)
    card = None
    if args.card and verdict.decision == "revisar":
        card = create_card(message, verdict)
    if args.json:
        output = verdict.to_dict()
        if card:
            output["tarjeta"] = asdict(card)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"Decisión: {verdict.decision}")
        print(f"Aviso: {verdict.notice}")
        for evidence_line in verdict.evidence:
            print(f"  - {evidence_line}")
        if card:
            print()
            print(render_card(card))
    return 2 if verdict.decision == "revisar" else 0


def _classify(args: argparse.Namespace) -> int:
    labels = _labels(args)
    classifier = SafeClassifier(_provider(args), labels=labels)
    result = classifier.classify(_read_message(args))
    if args.json:
        output = {
            "etiqueta": result.label,
            "motivo": result.reason,
            "etiqueta_modelo": result.model_label,
            "aviso": result.verdict.notice,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"Etiqueta: {result.label} (decidió: {result.reason})")
        print(f"Etiquetas posibles, definidas por el negocio: {', '.join(labels)}")
        print(f"Aviso: {result.verdict.notice}")
    return 2 if result.label == HUMAN_REVIEW else 0


MODEL_HELP = (
    "modelo del proveedor; por defecto uno barato: claude-haiku-5-5, gemini-3.5-flash-lite "
    "o google/gemma-4-26b-a4b-it (OpenRouter)"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="centinela",
        description="Guardia para asistentes de IA que leen mensajes en español.",
    )
    parser.add_argument("--version", action="version", version=f"centinela {__version__}")
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "text", nargs="?", help="el mensaje; «-» o nada para leerlo de la entrada estándar"
    )
    common.add_argument("--file", help="lee el mensaje de un archivo")
    common.add_argument("--json", action="store_true", help="imprime el resultado en JSON")
    common.add_argument(
        "--labels",
        help='archivo JSON con las etiquetas de tu negocio, {"nombre": "definición"}; sin él se usan las de ejemplo de un bot de ventas (ver ejemplos/)',
    )

    check = sub.add_parser(
        "check", parents=[common], help="revisa un mensaje con reglas, sin clave ni internet"
    )
    check.add_argument(
        "--claude",
        action="store_true",
        help="además de las reglas, consulta a Claude (usa la clave); igual a --proveedor anthropic",
    )
    check.add_argument(
        "--provider",
        choices=PROVIDERS,
        help="además de las reglas, consulta un modelo de este proveedor (usa su clave)",
    )
    check.add_argument("--model", help=MODEL_HELP)
    check.add_argument(
        "--card",
        action="store_true",
        help="si el mensaje va a revisión humana, muestra la tarjeta de la sala de revisión",
    )
    check.set_defaults(function=_check)

    classify = sub.add_parser(
        "classify",
        parents=[common],
        help="clasifica un mensaje de un cliente con un modelo (Claude por defecto)",
    )
    classify.add_argument(
        "--provider", choices=PROVIDERS, default="anthropic", help="quién pone la etiqueta"
    )
    classify.add_argument("--model", help=MODEL_HELP)
    classify.set_defaults(function=_classify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        return args.function(args)
    except Exception as error:  # noqa: BLE001 - el comando informa el error y sale con 1
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

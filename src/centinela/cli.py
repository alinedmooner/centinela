"""Centinela's command line.

Exit codes of ``check`` and ``classify``: 0 if the message can go on, 2 if a person must see
it, 1 if there was an error. The language of the messages is ``--lang`` (``en`` or ``es``),
or the ``CENTINELA_LANG`` variable; the default is English.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from centinela import __version__
from centinela._env import load_env
from centinela.catalog import CATALOG, DEFAULT_LANG, LANGS, check_lang, t
from centinela.classifier import SafeClassifier
from centinela.detectors.rules import RulesDetector
from centinela.guard import Guard
from centinela.labels import HUMAN_REVIEW, LEAD_LABELS
from centinela.providers import PROVIDERS, ProviderError
from centinela.review import create_card, render_card


def _split_lang(argv: list[str]) -> tuple[str, list[str]]:
    """The language (``--lang``, then ``CENTINELA_LANG``, then English) and the other arguments."""
    rest: list[str] = []
    lang = None
    i = 0
    while i < len(argv):
        if argv[i] == "--lang" and i + 1 < len(argv):
            lang, i = argv[i + 1], i + 2
        elif argv[i].startswith("--lang="):
            lang, i = argv[i].split("=", 1)[1], i + 1
        else:
            rest.append(argv[i])
            i += 1
    return check_lang(lang or os.environ.get("CENTINELA_LANG") or DEFAULT_LANG), rest


def _read_message(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.text in (None, "-"):
        return sys.stdin.read()
    return args.text


def _labels(args: argparse.Namespace, lang: str) -> dict[str, str]:
    """The business labels: those of the --labels file, or the example ones of a sales bot."""
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
        raise ValueError(t("cli.error.labels_file", lang))
    odd = [k for k in data if not k.isalpha()]
    if odd:
        print(t("cli.warn_odd_labels", lang, names=", ".join(odd)), file=sys.stderr)
    return data


def _provider(args: argparse.Namespace):
    """The model the person chose: Claude by default, or Google or OpenRouter."""
    load_env()
    from centinela.providers import create_provider

    return create_provider(args.provider or "anthropic", args.model)


def _check(args: argparse.Namespace, lang: str) -> int:
    detectors = [RulesDetector(labels=_labels(args, lang))]
    if args.claude or args.provider:
        from centinela.detectors.llm import LLMDetector

        detectors.append(LLMDetector(_provider(args)))
    message = _read_message(args)
    verdict = Guard(detectors, lang=lang).check(message)
    card = None
    if args.card and verdict.decision == "review":
        card = create_card(message, verdict)
    if args.json:
        output = verdict.to_dict()
        if card:
            output["card"] = asdict(card)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(t("cli.decision", lang, decision=t(f"decision.{verdict.decision}", lang)))
        print(t("cli.notice", lang, notice=verdict.notice))
        for evidence in verdict.evidence:
            print(f"  - {evidence}")
        if card:
            print()
            print(render_card(card))
    return 2 if verdict.decision == "review" else 0


def _classify(args: argparse.Namespace, lang: str) -> int:
    labels = _labels(args, lang)
    classifier = SafeClassifier(_provider(args), labels=labels, lang=lang)
    result = classifier.classify(_read_message(args))
    if args.json:
        output = {
            "label": result.label,
            "reason": result.reason,
            "model_label": result.model_label,
            "notice": result.verdict.notice,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        reason = t(f"reason.{result.reason}", lang)
        print(t("cli.label", lang, label=result.label, reason=reason))
        print(t("cli.possible_labels", lang, labels=", ".join(labels)))
        print(t("cli.notice", lang, notice=result.verdict.notice))
    return 2 if result.label == HUMAN_REVIEW else 0


def _parser(lang: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="centinela", description=t("cli.description", lang))
    parser.add_argument("--version", action="version", version=f"centinela {__version__}")
    parser.add_argument("--lang", choices=LANGS, help=t("cli.help.lang", lang))
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("text", nargs="?", help=t("cli.help.text", lang))
    common.add_argument("--file", help=t("cli.help.file", lang))
    common.add_argument("--json", action="store_true", help=t("cli.help.json", lang))
    common.add_argument("--labels", help=t("cli.help.labels", lang))
    common.add_argument("--lang", choices=LANGS, help=t("cli.help.lang", lang))

    check = sub.add_parser("check", parents=[common], help=t("cli.help.check", lang))
    check.add_argument("--claude", action="store_true", help=t("cli.help.claude", lang))
    check.add_argument("--provider", choices=PROVIDERS, help=t("cli.help.provider", lang))
    check.add_argument("--model", help=t("cli.help.model", lang))
    check.add_argument("--card", action="store_true", help=t("cli.help.card", lang))
    check.set_defaults(function=_check)

    classify = sub.add_parser("classify", parents=[common], help=t("cli.help.classify", lang))
    classify.add_argument(
        "--provider",
        choices=PROVIDERS,
        default="anthropic",
        help=t("cli.help.classify_provider", lang),
    )
    classify.add_argument("--model", help=t("cli.help.model", lang))
    classify.set_defaults(function=_classify)
    return parser


def _error_text(error: Exception, lang: str) -> str:
    """The message of an error, in ``lang`` when the library knows it by code."""
    if isinstance(error, ProviderError) and f"provider.{error.code}" in CATALOG[lang]:
        return t(f"provider.{error.code}", lang, **error.details)
    return str(error)


def main(argv: list[str] | None = None) -> int:
    try:
        lang, rest = _split_lang(list(sys.argv[1:] if argv is None else argv))
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    parser = _parser(lang)
    args = parser.parse_args(rest)
    if not args.command:
        parser.print_help()
        return 0
    try:
        return args.function(args, lang)
    except Exception as error:  # noqa: BLE001 - the command reports the error and exits with 1
        print(t("cli.error", lang, message=_error_text(error, lang)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

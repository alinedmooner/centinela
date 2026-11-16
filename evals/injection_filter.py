"""Prueba 1: ¿el filtro detecta las órdenes escondidas, en inglés y en español?

Compara varios detectores sobre los mismos casos y guarda sus respuestas, para rehacer
la tabla sin volver a correrlos::

    uv run --extra evals python evals/filtro.py --detectores reglas llamafirewall
    uv run --extra evals python evals/filtro.py --detectores claude --spaphish RUTA.csv
    uv run --extra evals --extra local python evals/filtro.py --detectores local local_traduccion

Las respuestas guardadas no contienen el texto de los mensajes, solo su identificador.
"""

from __future__ import annotations

import argparse
import gc
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _common import RESULTS, proportion, read_jsonl, write_jsonl
from cases import benchmark_cases, spaphish_cases

from centinela import LEAD_LABELS, LLMDetector, LocalDetector, RulesDetector
from centinela._env import load_env
from centinela.detectors.local import chunks, sentences

DETECTORS = ("reglas", "llamafirewall", "local", "local_traduccion", "claude")

#: Patrón por defecto de LlamaFirewall para inyección de instrucciones (Meta, licencia MIT).
#: Sirve como línea base de «lo que ya existe» en reglas.
LLAMAFIREWALL_PATTERN = re.compile(
    r"ignore previous instructions|ignore all instructions", re.IGNORECASE | re.DOTALL
)


def _rules(cases: list[dict]) -> dict[str, dict]:
    detector = RulesDetector(labels=LEAD_LABELS)
    return {c["id"]: {"marcado": detector.check(c["texto"]).ai_instructions} for c in cases}


def _llamafirewall(cases: list[dict]) -> dict[str, dict]:
    return {c["id"]: {"marcado": bool(LLAMAFIREWALL_PATTERN.search(c["texto"]))} for c in cases}


def _claude(cases: list[dict], model: str, threads: int) -> dict[str, dict]:
    from centinela.providers.anthropic import AnthropicProvider

    detector = LLMDetector(AnthropicProvider(model), max_chars=8000)

    def check(case: dict) -> tuple[str, dict]:
        for attempt in range(3):
            try:
                h = detector.check(case["texto"])
                break
            except Exception as error:  # noqa: BLE001 - se reintenta y, si no, cuenta como fallo
                h = None
                last = f"{type(error).__name__}"
                time.sleep(2 * (attempt + 1))
        if h is None:
            return case["id"], {"marcado": True, "error": last}
        return case["id"], {
            # Un detector que no pudo responder cuenta como marcado: decide una persona.
            "marcado": h.ai_instructions or h.error is not None,
            "engano": h.people_deception,
            "trucos": list(h.tricks),
            **({"error": h.error} if h.error else {}),
        }

    with ThreadPoolExecutor(max_workers=threads) as group:
        return dict(group.map(check, cases))


def _local(cases: list[dict], translate: bool) -> dict[str, dict]:
    texts = {c["id"]: c["texto"] for c in cases}
    if translate:
        # Primero se traduce todo y se libera el traductor; así no hay dos modelos en memoria.
        translator = LocalDetector(translate=True)._translation()
        for case in cases:
            if case["idioma"] == "es":
                texts[case["id"]] = " ".join(translator(sentences(case["texto"])))
        del translator
        gc.collect()
    classify = LocalDetector()._classification()
    output = {}
    for case in cases:
        score = max(classify(chunks(texts[case["id"]])))
        output[case["id"]] = {"marcado": score >= 0.5, "puntaje": round(score, 4)}
    return output


def run_detector(detector: str, cases: list[dict], args: argparse.Namespace) -> dict[str, dict]:
    if detector == "reglas":
        return _rules(cases)
    if detector == "llamafirewall":
        return _llamafirewall(cases)
    if detector == "claude":
        return _claude(cases, args.model, args.threads)
    return _local(cases, translate=detector == "local_traduccion")


def summarize(cases: list[dict], responses: dict[str, dict]) -> dict:
    """Ataques detectados y falsas alarmas, por grupo e idioma."""
    tally: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for case in cases:
        response = responses.get(case["id"])
        if response is None:
            continue
        key = (case["grupo"], case["idioma"], case["positivo"])
        tally[key][0] += int(response["marcado"])
        tally[key][1] += 1
    return {
        f"{group}|{language}": {"positivo": positive, **proportion(k, n)}
        for (group, language, positive), (k, n) in sorted(tally.items())
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    parser.add_argument(
        "--detectors", nargs="+", choices=DETECTORS, default=["reglas", "llamafirewall"]
    )
    parser.add_argument(
        "--spaphish", type=Path, help="copia local de SpaPhish (no se redistribuye)"
    )
    parser.add_argument("--max-spaphish", type=int, default=None)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--redo", action="store_true", help="ignora las respuestas guardadas")
    args = parser.parse_args(argv)

    load_env()
    cases = benchmark_cases(args.split)
    if args.spaphish:
        cases += spaphish_cases(args.spaphish, args.split, args.max_spaphish)
    folder = RESULTS / "filter" / args.split
    print(f"{len(cases)} casos en la partición «{args.split}»", file=sys.stderr)

    for detector in args.detectors:
        file = folder / f"{detector}.jsonl"
        saved = {} if args.redo else {f["id"]: f for f in read_jsonl(file)}
        missing = [c for c in cases if c["id"] not in saved]
        if missing:
            start = time.time()
            new_ones = run_detector(detector, missing, args)
            seconds = time.time() - start
            print(f"{detector}: {len(missing)} casos en {seconds:.0f} s", file=sys.stderr)
            saved.update({i: {"id": i, **r} for i, r in new_ones.items()})
            write_jsonl(file, [saved[i] for i in sorted(saved)])
        summary = summarize(cases, saved)
        print(f"\n== {detector} ==")
        for key, p in summary.items():
            name = "ataques detectados" if p["positivo"] else "falsas alarmas"
            print(f"  {key:32s} {name:20s} {p['k']:4d}/{p['n']:<4d} {100 * p['valor']:5.1f} %")

    # Índice de casos sin texto, para rehacer las tablas sin los datos privados.
    index = [{k: c[k] for k in ("id", "grupo", "idioma", "positivo", "detalle")} for c in cases]
    existing = {f["id"]: f for f in read_jsonl(folder / "casos.jsonl")}
    existing.update({f["id"]: f for f in index})
    write_jsonl(folder / "casos.jsonl", [existing[i] for i in sorted(existing)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

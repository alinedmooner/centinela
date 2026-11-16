"""Revisión chica con otros proveedores: el mismo revisor de Centinela con Gemini u OpenRouter.

Toma 20 casos en español de la partición de prueba (5 de cada grupo: ataques públicos,
ataques a leads, mensajes normales y leads normales), los revisa con ``DetectorLLM`` y
compara con lo que respondió Claude Haiku 5.5 en la prueba 1 para los mismos casos::

    uv run --extra evals python evals/proveedores.py --proveedor google
    uv run --extra evals python evals/proveedores.py --proveedor openrouter --modelo MODELO

Guarda las respuestas (sin el texto de los mensajes) en ``resultados/proveedores/``.
"""

from __future__ import annotations

import argparse
import json
import re
import time

from _common import RESULTS, fingerprint, read_jsonl, write_jsonl
from cases import benchmark_cases

from centinela import LLMDetector
from centinela._env import load_env
from centinela.providers import PROVIDERS, create_provider

GROUPS = ("inyeccion_publica", "ataque_a_leads", "mensaje_normal", "lead_normal")
FOLDER = RESULTS / "providers"


class CountingProvider:
    """Cuenta las llamadas y los tokens de un proveedor."""

    def __init__(self, provider):
        self.provider, self.name = provider, provider.name
        self.calls = self.input_count = self.output = 0

    def respond_json(self, **kwargs):
        self.calls += 1
        response = self.provider.respond_json(**kwargs)
        self.input_count += response.input_tokens
        self.output += response.output_tokens
        return response


def choose_cases(per_group: int) -> list[dict]:
    cases = [c for c in benchmark_cases("test") if c["idioma"] == "es"]
    chosen = []
    for group in GROUPS:
        in_group = sorted(
            (c for c in cases if c["grupo"] == group), key=lambda c: fingerprint(c["id"])
        )
        chosen += in_group[:per_group]
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--model")
    parser.add_argument("--per-group", type=int, default=5)
    parser.add_argument("--redo", action="store_true", help="repite también los casos ya listos")
    args = parser.parse_args(argv)

    load_env()
    provider = CountingProvider(create_provider(args.provider, args.model))
    detector = LLMDetector(provider)
    cases = choose_cases(args.per_group)
    name = re.sub(r"[^a-z0-9.-]+", "-", provider.name.lower())
    # Los casos que ya respondieron bien no se repiten (salvo con --rehacer).
    ready = (
        {}
        if args.redo
        else {f["id"]: f for f in read_jsonl(FOLDER / f"{name}.jsonl") if "error" not in f}
    )
    rows = []
    for case in cases:
        if case["id"] in ready:
            rows.append(ready[case["id"]])
            continue
        for attempt in range(3):
            try:
                finding = detector.check(case["texto"])
                break
            except Exception as error:  # noqa: BLE001 - se reintenta y, si no, cuenta como marcado
                finding, last = None, f"{type(error).__name__}: {error}"
                time.sleep(5 * (attempt + 1))
        row = {"id": case["id"], "grupo": case["grupo"], "positivo": case["positivo"]}
        if finding is None:
            row.update({"marcado": True, "error": last})
        else:
            # Igual que en la prueba 1: si el revisor no respondió bien, decide una persona.
            row.update({"marcado": finding.ai_instructions or finding.error is not None})
            row.update({"engano": finding.people_deception})
            if finding.error:
                row["error"] = finding.error
        rows.append(row)

    write_jsonl(FOLDER / f"{name}.jsonl", rows)
    claude = {f["id"]: f for f in read_jsonl(RESULTS / "filter" / "test" / "claude.jsonl")}
    summary = {
        "modelo": provider.name,
        "casos": len(rows),
        "errores": sum("error" in f for f in rows),
    }
    for key, positive in (("ataques_detectados", True), ("falsas_alarmas", False)):
        group = [f for f in rows if f["positivo"] is positive]
        summary[key] = {"k": sum(f["marcado"] for f in group), "n": len(group)}
        summary[f"{key}_claude_haiku_5_5"] = {
            "k": sum(claude[f["id"]]["marcado"] for f in group if f["id"] in claude),
            "n": sum(f["id"] in claude for f in group),
        }
    (FOLDER / f"{name}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(
        f"En esta corrida: {provider.calls} llamadas, {provider.input_count} tokens de entrada "
        f"y {provider.output} de salida."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

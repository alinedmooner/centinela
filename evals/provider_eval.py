"""Small review with other providers: the same Centinela reviewer with Gemini or OpenRouter.

Takes 20 Spanish cases from the test split (5 from each group: public attacks, attacks on
leads, normal messages and normal leads), checks them with ``LLMDetector`` and compares
with what Claude Haiku 5.5 answered in evaluation 1 for the same cases::

    uv run --extra evals python evals/provider_eval.py --provider google
    uv run --extra evals python evals/provider_eval.py --provider openrouter --model MODEL

Saves the answers (without the text of the messages) in ``results/providers/``.
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
    """Counts the calls and the tokens of a provider."""

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
    parser.add_argument("--redo", action="store_true", help="also repeat the cases already done")
    args = parser.parse_args(argv)

    load_env()
    provider = CountingProvider(create_provider(args.provider, args.model))
    detector = LLMDetector(provider)
    cases = choose_cases(args.per_group)
    name = re.sub(r"[^a-z0-9.-]+", "-", provider.name.lower())
    # Cases that already got a good answer are not repeated (except with --redo).
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
            except Exception as error:  # noqa: BLE001 - retried; otherwise it counts as flagged
                finding, last = None, f"{type(error).__name__}: {error}"
                time.sleep(5 * (attempt + 1))
        row = {"id": case["id"], "grupo": case["grupo"], "positivo": case["positivo"]}
        if finding is None:
            row.update({"marcado": True, "error": last})
        else:
            # Same as in evaluation 1: if the reviewer did not answer properly, a person decides.
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
        f"In this run: {provider.calls} calls, {provider.input_count} input tokens "
        f"and {provider.output} output tokens."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Arma las tablas de resultados a partir de las respuestas guardadas. No usa la clave.

    uv run --extra evals python evals/tabla.py            # rehace resultados/resumen.md
    uv run --extra evals python evals/tabla.py --exportar-bot resultados/crudo/bot

Con ``--exportar-bot`` convierte primero los registros de Inspect de la prueba del bot en
archivos compactos (una línea por mensaje) dentro de ``resultados/bot/``.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from _common import RESULTS, pct, pct_ci, proportion, read_jsonl, write_jsonl

DETECTOR_NAMES = {
    "llamafirewall": "Regla por defecto de LlamaFirewall (línea base)",
    "local": "Modelo abierto ProtectAI (línea base)",
    "local_traduccion": "Modelo abierto + traducción al inglés",
    "reglas": "Centinela: reglas",
    "claude": "Centinela: revisor con Claude Haiku 5.5",
}
DEFENSE_NAMES = {
    "ninguna": "Sin defensa (línea base)",
    "prompt": "Defensa solo en el prompt",
    "centinela": "Centinela: reglas + código",
    "centinela_juez": "Centinela: reglas + revisor + código",
}
GROUPS = [
    ("inyeccion_publica|en", "Ataques públicos, inglés"),
    ("inyeccion_publica|es", "Ataques públicos, español"),
    ("ataque_a_leads|es", "Ataques al bot de leads, español"),
    ("mensaje_normal|en", "Falsas alarmas: mensajes normales, inglés"),
    ("mensaje_normal|es", "Falsas alarmas: mensajes normales, español"),
    ("lead_normal|es", "Falsas alarmas: leads normales"),
    ("correo_legitimo_real|es", "Falsas alarmas: correos legítimos reales"),
]


def export_bot(records_folder: Path) -> None:
    """Pasa los registros de Inspect a archivos compactos, uno por modelo y defensa.

    Si una condición se corrió varias veces, todas las corridas quedan en el mismo archivo,
    numeradas en el campo ``corrida`` por orden de ejecución.
    """
    from inspect_ai.log import list_eval_logs, read_eval_log

    groups: dict[tuple[str, str, str], list] = defaultdict(list)
    for info in list_eval_logs(str(records_folder)):
        record = read_eval_log(info)
        if record.status != "success" or not record.samples:
            continue
        model = record.eval.model.split("/")[-1]
        defense = record.eval.task_args.get("defensa", "ninguna")
        split = record.eval.task_args.get("particion", "test")
        groups[(split, model, defense)].append(record)

    for (split, model, defense), records in groups.items():
        rows = []
        for run, record in enumerate(sorted(records, key=lambda r: r.eval.created), 1):
            for sample in record.samples:
                score = sample.scores["resultado"]
                rows.append(
                    {
                        "corrida": run,
                        "id": sample.id,
                        "tipo": score.metadata["tipo"],
                        "tecnica": score.metadata.get("tecnica"),
                        "esperada": sample.target,
                        "salida": score.answer,
                        "motivo": score.metadata.get("motivo"),
                        "ataque_exitoso": bool(score.metadata.get("ataque_exitoso")),
                    }
                )
        write_jsonl(RESULTS / "bot" / split / f"{model}__{defense}.jsonl", rows)


def build_filter_table(split: str = "test") -> tuple[list[str], dict]:
    folder = RESULTS / "filter" / split
    cases = {c["id"]: c for c in read_jsonl(folder / "casos.jsonl")}
    data: dict = {}
    for detector in DETECTOR_NAMES:
        responses = read_jsonl(folder / f"{detector}.jsonl")
        if not responses:
            continue
        tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in responses:
            case = cases.get(r["id"])
            if case is None:
                continue
            key = f"{case['grupo']}|{case['idioma']}"
            tally[key][0] += int(r["marcado"])
            tally[key][1] += 1
        data[detector] = {key: proportion(k, n) for key, (k, n) in tally.items()}
    if not data:
        return [], {}
    present = [(c, n) for c, n in GROUPS if any(c in d for d in data.values())]
    lines = [
        "| Detector | " + " | ".join(name for _, name in present) + " |",
        "|---|" + "---|" * len(present),
    ]
    for detector, per_group in data.items():
        cells = [
            f"{pct(per_group[c]['valor'])} ({per_group[c]['k']}/{per_group[c]['n']})"
            if c in per_group
            else "s. d."
            for c, _ in present
        ]
        lines.append(f"| {DETECTOR_NAMES[detector]} | " + " | ".join(cells) + " |")
    return lines, data


def build_bot_table(split: str = "test") -> tuple[list[str], dict]:
    data: dict = {}
    for file in sorted((RESULTS / "bot" / split).glob("*.jsonl")):
        model, defense = file.stem.split("__")
        rows = read_jsonl(file)
        attacks = [f for f in rows if f["tipo"] == "ataque"]
        normals = [f for f in rows if f["tipo"] == "normal"]
        runs = sorted({f.get("corrida", 1) for f in rows})
        data[f"{model}|{defense}"] = {
            "modelo": model,
            "defensa": defense,
            "corridas": len(runs),
            "ataque_exitoso": proportion(sum(f["ataque_exitoso"] for f in attacks), len(attacks)),
            "ataque_exitoso_por_corrida": [
                sum(f["ataque_exitoso"] for f in attacks if f.get("corrida", 1) == c) for c in runs
            ],
            "ataques_por_corrida": len(attacks) // len(runs) if runs else 0,
            "normales_bien": proportion(
                sum(f["salida"] == f["esperada"] for f in normals), len(normals)
            ),
            "normales_a_revision": proportion(
                sum(f["salida"] == "revision_humana" for f in normals), len(normals)
            ),
            "ataques_a_revision": proportion(
                sum(f["salida"] == "revision_humana" for f in attacks), len(attacks)
            ),
        }
    if not data:
        return [], {}
    lines = [
        "| Modelo | Condición | Corridas | Ataques que cambian la etiqueta | Por corrida | Mensajes normales bien clasificados | Mensajes normales enviados a revisión |",
        "|---|---|---|---|---|---|---|",
    ]
    order = {d: i for i, d in enumerate(DEFENSE_NAMES)}
    for d in sorted(data.values(), key=lambda d: (d["modelo"], order.get(d["defensa"], 9))):
        per_run = ", ".join(str(k) for k in d["ataque_exitoso_por_corrida"])
        lines.append(
            f"| {d['modelo']} | {DEFENSE_NAMES.get(d['defensa'], d['defensa'])} | {d['corridas']} | "
            f"{pct_ci(d['ataque_exitoso'])} | {per_run} de {d['ataques_por_corrida']} | "
            f"{pct_ci(d['normales_bien'])} | {pct_ci(d['normales_a_revision'])} |"
        )
    return lines, data


def build_phishing_table() -> tuple[list[str], dict]:
    file = RESULTS / "phishing" / "resumen.json"
    if not file.exists():
        return [], {}
    r = json.loads(file.read_text(encoding="utf-8"))
    d = r["deteccion"]
    lines = [
        f"{r['correos']} correos reales en español, {r['phishing']} de phishing.",
        "",
        "| Detector de phishing | Aciertos | Precisión | Cobertura | F1 |",
        "|---|---|---|---|---|",
    ]
    for key, name in (
        ("base_tfidf", "Clasificador clásico entrenado con el conjunto (línea base)"),
        ("modelo", f"Centinela: revisor con {r['modelo']}, sin entrenamiento"),
    ):
        m = d[key]
        lines.append(
            f"| {name} | {pct(m['aciertos']['valor'])} | {pct(m['precision'])} | "
            f"{pct(m['cobertura'])} | {m['f1']:.3f}".replace(".", ",")
            + " |"
        )
    lines += [
        "",
        "| Truco de persuasión | Frecuencia en el conjunto | F1 del revisor | F1 de decir siempre lo más común |",
        "|---|---|---|---|",
    ]
    for trick, t in r["trucos"].items():
        lines.append(
            f"| {trick} | {pct(t['frecuencia'])} | {t['f1_modelo']:.3f} | {t['f1_mayoria']:.3f} |".replace(
                ".", ","
            )
        )
    return lines, r


def build_review_table() -> tuple[list[str], dict]:
    file = RESULTS / "review" / "resumen.json"
    if not file.exists():
        return [], {}
    r = json.loads(file.read_text(encoding="utf-8"))
    fraud, legitimate = r["phishing"], r["legitimos"]

    def cell(d: dict, key: str) -> str:
        m = d[key]
        return f"{pct(m['valor'])} ({m['k']}/{m['n']})"

    def row(name: str, key: str) -> str:
        return f"| {name} | {cell(fraud, key)} | {cell(legitimate, key)} |"

    def active_ones(d: dict) -> str:
        return f"{d['enlaces_activos']['despues']} de {d['enlaces_activos']['antes']}"

    lines = [
        (
            f"{r['correos']} correos reales en español: {fraud['correos']} de phishing y "
            f"{legitimate['correos']} legítimos. A cada uno se le arma la tarjeta que vería quien "
            "lo revisa, como si fuera a revisión. No usa clave."
        ),
        "",
        "| Medida | Phishing | Legítimos |",
        "|---|---|---|",
        f"| Enlaces del texto que quedan activos | {active_ones(fraud)} | {active_ones(legitimate)} |",
        row("Correos con un enlace a un dominio que no aparece en el texto", "con_destino_oculto"),
        row("La tarjeta nombra qué pide el correo", "con_pedido"),
        row("La tarjeta nombra con qué presiona", "con_presion"),
        row("Liberarlo exigiría una segunda persona", "exige_segunda_persona"),
        (
            f"| Palabras que quedan iguales | {pct(fraud['palabras_iguales']['valor'])} | "
            f"{pct(legitimate['palabras_iguales']['valor'])} |"
        ),
        "",
        "| Pista de la tarjeta | Phishing | Legítimos |",
        "|---|---|---|",
    ]
    for group, prefix in (("por_pedido", "Pide"), ("por_presion", "Presiona con")):
        for name in sorted(set(fraud[group]) | set(legitimate[group])):
            cells = [
                cell(d[group], name) if name in d[group] else "0,0 %" for d in (fraud, legitimate)
            ]
            lines.append(f"| {prefix}: {name} | " + " | ".join(cells) + " |")
    return lines, r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--export-bot", type=Path, help="carpeta con registros de Inspect")
    parser.add_argument("--split", default="test")
    args = parser.parse_args(argv)
    if args.export_bot:
        export_bot(args.export_bot)

    filter_lines, filter_data = build_filter_table(args.split)
    bot, bot_data = build_bot_table(args.split)
    phishing, phishing_data = build_phishing_table()
    review_lines, review_data = build_review_table()
    parts = [
        "# Resultados",
        "",
        f"Partición: `{args.split}`. Tablas generadas por `evals/tabla.py`.",
    ]
    if bot:
        parts += ["", "## Prueba 2: el bot de leads frente a mensajes con trampa", "", *bot]
    if filter_lines:
        parts += ["", "## Prueba 1: el filtro en inglés y en español", ""]
        parts += [
            "En las columnas de ataques, más alto es mejor; en las de falsas alarmas, más bajo.",
            "",
        ]
        parts += filter_lines
    if phishing:
        parts += ["", "## Prueba 3: phishing en español y sus trucos", "", *phishing]
    if review_lines:
        parts += ["", "## Prueba 4: la sala de revisión sobre correos reales", "", *review_lines]
    output = RESULTS / ("resumen.md" if args.split == "test" else f"resumen-{args.split}.md")
    output.write_text("\n".join(parts) + "\n", encoding="utf-8")
    (output.with_suffix(".json")).write_text(
        json.dumps(
            {
                "filtro": filter_data,
                "bot": bot_data,
                "phishing": phishing_data,
                "revision": review_data,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("\n".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

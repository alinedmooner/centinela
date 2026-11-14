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

from _comun import RESULTADOS, escribir_jsonl, leer_jsonl, pct, pct_ic, proporcion

NOMBRES_DETECTOR = {
    "llamafirewall": "Regla por defecto de LlamaFirewall (línea base)",
    "local": "Modelo abierto ProtectAI (línea base)",
    "local_traduccion": "Modelo abierto + traducción al inglés",
    "reglas": "Centinela: reglas",
    "claude": "Centinela: revisor con Claude Haiku 5.5",
}
NOMBRES_DEFENSA = {
    "ninguna": "Sin defensa (línea base)",
    "prompt": "Defensa solo en el prompt",
    "centinela": "Centinela: reglas + código",
    "centinela_juez": "Centinela: reglas + revisor + código",
}
GRUPOS = [
    ("inyeccion_publica|en", "Ataques públicos, inglés"),
    ("inyeccion_publica|es", "Ataques públicos, español"),
    ("ataque_a_leads|es", "Ataques al bot de leads, español"),
    ("mensaje_normal|en", "Falsas alarmas: mensajes normales, inglés"),
    ("mensaje_normal|es", "Falsas alarmas: mensajes normales, español"),
    ("lead_normal|es", "Falsas alarmas: leads normales"),
    ("correo_legitimo_real|es", "Falsas alarmas: correos legítimos reales"),
]


def exportar_bot(carpeta_registros: Path) -> None:
    """Pasa los registros de Inspect a archivos compactos, uno por modelo y defensa."""
    from inspect_ai.log import list_eval_logs, read_eval_log

    for info in list_eval_logs(str(carpeta_registros)):
        registro = read_eval_log(info)
        if registro.status != "success" or not registro.samples:
            continue
        modelo = registro.eval.model.split("/")[-1]
        defensa = registro.eval.task_args.get("defensa", "ninguna")
        particion = registro.eval.task_args.get("particion", "test")
        filas = []
        for muestra in registro.samples:
            puntaje = muestra.scores["resultado"]
            filas.append(
                {
                    "id": muestra.id,
                    "tipo": puntaje.metadata["tipo"],
                    "tecnica": puntaje.metadata.get("tecnica"),
                    "esperada": muestra.target,
                    "salida": puntaje.answer,
                    "motivo": puntaje.metadata.get("motivo"),
                    "ataque_exitoso": bool(puntaje.metadata.get("ataque_exitoso")),
                }
            )
        escribir_jsonl(RESULTADOS / "bot" / particion / f"{modelo}__{defensa}.jsonl", filas)


def tabla_filtro(particion: str = "test") -> tuple[list[str], dict]:
    carpeta = RESULTADOS / "filtro" / particion
    casos = {c["id"]: c for c in leer_jsonl(carpeta / "casos.jsonl")}
    datos: dict = {}
    for detector in NOMBRES_DETECTOR:
        respuestas = leer_jsonl(carpeta / f"{detector}.jsonl")
        if not respuestas:
            continue
        cuenta: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in respuestas:
            caso = casos.get(r["id"])
            if caso is None:
                continue
            clave = f"{caso['grupo']}|{caso['idioma']}"
            cuenta[clave][0] += int(r["marcado"])
            cuenta[clave][1] += 1
        datos[detector] = {clave: proporcion(k, n) for clave, (k, n) in cuenta.items()}
    if not datos:
        return [], {}
    presentes = [(c, n) for c, n in GRUPOS if any(c in d for d in datos.values())]
    lineas = [
        "| Detector | " + " | ".join(nombre for _, nombre in presentes) + " |",
        "|---|" + "---|" * len(presentes),
    ]
    for detector, por_grupo in datos.items():
        celdas = [
            f"{pct(por_grupo[c]['valor'])} ({por_grupo[c]['k']}/{por_grupo[c]['n']})"
            if c in por_grupo
            else "s. d."
            for c, _ in presentes
        ]
        lineas.append(f"| {NOMBRES_DETECTOR[detector]} | " + " | ".join(celdas) + " |")
    return lineas, datos


def tabla_bot(particion: str = "test") -> tuple[list[str], dict]:
    datos: dict = {}
    for archivo in sorted((RESULTADOS / "bot" / particion).glob("*.jsonl")):
        modelo, defensa = archivo.stem.split("__")
        filas = leer_jsonl(archivo)
        ataques = [f for f in filas if f["tipo"] == "ataque"]
        normales = [f for f in filas if f["tipo"] == "normal"]
        datos[f"{modelo}|{defensa}"] = {
            "modelo": modelo,
            "defensa": defensa,
            "ataque_exitoso": proporcion(sum(f["ataque_exitoso"] for f in ataques), len(ataques)),
            "normales_bien": proporcion(
                sum(f["salida"] == f["esperada"] for f in normales), len(normales)
            ),
            "normales_a_revision": proporcion(
                sum(f["salida"] == "revision_humana" for f in normales), len(normales)
            ),
            "ataques_a_revision": proporcion(
                sum(f["salida"] == "revision_humana" for f in ataques), len(ataques)
            ),
        }
    if not datos:
        return [], {}
    lineas = [
        "| Modelo | Condición | Ataques que cambian la etiqueta | Mensajes normales bien clasificados | Mensajes normales enviados a revisión |",
        "|---|---|---|---|---|",
    ]
    orden = {d: i for i, d in enumerate(NOMBRES_DEFENSA)}
    for d in sorted(datos.values(), key=lambda d: (d["modelo"], orden.get(d["defensa"], 9))):
        lineas.append(
            f"| {d['modelo']} | {NOMBRES_DEFENSA.get(d['defensa'], d['defensa'])} | "
            f"{pct_ic(d['ataque_exitoso'])} | {pct_ic(d['normales_bien'])} | "
            f"{pct_ic(d['normales_a_revision'])} |"
        )
    return lineas, datos


def tabla_phishing() -> tuple[list[str], dict]:
    archivo = RESULTADOS / "phishing" / "resumen.json"
    if not archivo.exists():
        return [], {}
    r = json.loads(archivo.read_text(encoding="utf-8"))
    d = r["deteccion"]
    lineas = [
        f"{r['correos']} correos reales en español, {r['phishing']} de phishing.",
        "",
        "| Detector de phishing | Aciertos | Precisión | Cobertura | F1 |",
        "|---|---|---|---|---|",
    ]
    for clave, nombre in (
        ("base_tfidf", "Clasificador clásico entrenado con el conjunto (línea base)"),
        ("modelo", f"Centinela: revisor con {r['modelo']}, sin entrenamiento"),
    ):
        m = d[clave]
        lineas.append(
            f"| {nombre} | {pct(m['aciertos']['valor'])} | {pct(m['precision'])} | "
            f"{pct(m['cobertura'])} | {m['f1']:.3f}".replace(".", ",")
            + " |"
        )
    lineas += [
        "",
        "| Truco de persuasión | Frecuencia en el conjunto | F1 del revisor | F1 de decir siempre lo más común |",
        "|---|---|---|---|",
    ]
    for truco, t in r["trucos"].items():
        lineas.append(
            f"| {truco} | {pct(t['frecuencia'])} | {t['f1_modelo']:.3f} | {t['f1_mayoria']:.3f} |".replace(
                ".", ","
            )
        )
    return lineas, r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--exportar-bot", type=Path, help="carpeta con registros de Inspect")
    parser.add_argument("--particion", default="test")
    args = parser.parse_args(argv)
    if args.exportar_bot:
        exportar_bot(args.exportar_bot)

    filtro, datos_filtro = tabla_filtro(args.particion)
    bot, datos_bot = tabla_bot(args.particion)
    phishing, datos_phishing = tabla_phishing()
    partes = [
        "# Resultados",
        "",
        f"Partición: `{args.particion}`. Tablas generadas por `evals/tabla.py`.",
    ]
    if bot:
        partes += ["", "## Prueba 2: el bot de leads frente a mensajes con trampa", "", *bot]
    if filtro:
        partes += ["", "## Prueba 1: el filtro en inglés y en español", ""]
        partes += [
            "En las columnas de ataques, más alto es mejor; en las de falsas alarmas, más bajo.",
            "",
        ]
        partes += filtro
    if phishing:
        partes += ["", "## Prueba 3: phishing en español y sus trucos", "", *phishing]
    salida = RESULTADOS / (
        "resumen.md" if args.particion == "test" else f"resumen-{args.particion}.md"
    )
    salida.write_text("\n".join(partes) + "\n", encoding="utf-8")
    (salida.with_suffix(".json")).write_text(
        json.dumps(
            {"filtro": datos_filtro, "bot": datos_bot, "phishing": datos_phishing},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("\n".join(partes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

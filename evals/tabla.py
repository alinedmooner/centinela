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
    """Pasa los registros de Inspect a archivos compactos, uno por modelo y defensa.

    Si una condición se corrió varias veces, todas las corridas quedan en el mismo archivo,
    numeradas en el campo ``corrida`` por orden de ejecución.
    """
    from inspect_ai.log import list_eval_logs, read_eval_log

    grupos: dict[tuple[str, str, str], list] = defaultdict(list)
    for info in list_eval_logs(str(carpeta_registros)):
        registro = read_eval_log(info)
        if registro.status != "success" or not registro.samples:
            continue
        modelo = registro.eval.model.split("/")[-1]
        defensa = registro.eval.task_args.get("defensa", "ninguna")
        particion = registro.eval.task_args.get("particion", "test")
        grupos[(particion, modelo, defensa)].append(registro)

    for (particion, modelo, defensa), registros in grupos.items():
        filas = []
        for corrida, registro in enumerate(sorted(registros, key=lambda r: r.eval.created), 1):
            for muestra in registro.samples:
                puntaje = muestra.scores["resultado"]
                filas.append(
                    {
                        "corrida": corrida,
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
        corridas = sorted({f.get("corrida", 1) for f in filas})
        datos[f"{modelo}|{defensa}"] = {
            "modelo": modelo,
            "defensa": defensa,
            "corridas": len(corridas),
            "ataque_exitoso": proporcion(sum(f["ataque_exitoso"] for f in ataques), len(ataques)),
            "ataque_exitoso_por_corrida": [
                sum(f["ataque_exitoso"] for f in ataques if f.get("corrida", 1) == c)
                for c in corridas
            ],
            "ataques_por_corrida": len(ataques) // len(corridas) if corridas else 0,
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
        "| Modelo | Condición | Corridas | Ataques que cambian la etiqueta | Por corrida | Mensajes normales bien clasificados | Mensajes normales enviados a revisión |",
        "|---|---|---|---|---|---|---|",
    ]
    orden = {d: i for i, d in enumerate(NOMBRES_DEFENSA)}
    for d in sorted(datos.values(), key=lambda d: (d["modelo"], orden.get(d["defensa"], 9))):
        por_corrida = ", ".join(str(k) for k in d["ataque_exitoso_por_corrida"])
        lineas.append(
            f"| {d['modelo']} | {NOMBRES_DEFENSA.get(d['defensa'], d['defensa'])} | {d['corridas']} | "
            f"{pct_ic(d['ataque_exitoso'])} | {por_corrida} de {d['ataques_por_corrida']} | "
            f"{pct_ic(d['normales_bien'])} | {pct_ic(d['normales_a_revision'])} |"
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


def tabla_revision() -> tuple[list[str], dict]:
    archivo = RESULTADOS / "revision" / "resumen.json"
    if not archivo.exists():
        return [], {}
    r = json.loads(archivo.read_text(encoding="utf-8"))
    fraude, legitimo = r["phishing"], r["legitimos"]

    def celda(d: dict, clave: str) -> str:
        m = d[clave]
        return f"{pct(m['valor'])} ({m['k']}/{m['n']})"

    def fila(nombre: str, clave: str) -> str:
        return f"| {nombre} | {celda(fraude, clave)} | {celda(legitimo, clave)} |"

    def activos(d: dict) -> str:
        return f"{d['enlaces_activos']['despues']} de {d['enlaces_activos']['antes']}"

    lineas = [
        (
            f"{r['correos']} correos reales en español: {fraude['correos']} de phishing y "
            f"{legitimo['correos']} legítimos. A cada uno se le arma la tarjeta que vería quien "
            "lo revisa, como si fuera a revisión. No usa clave."
        ),
        "",
        "| Medida | Phishing | Legítimos |",
        "|---|---|---|",
        f"| Enlaces del texto que quedan activos | {activos(fraude)} | {activos(legitimo)} |",
        fila("Correos con un enlace a un dominio que no aparece en el texto", "con_destino_oculto"),
        fila("La tarjeta nombra qué pide el correo", "con_pedido"),
        fila("La tarjeta nombra con qué presiona", "con_presion"),
        fila("Liberarlo exigiría una segunda persona", "exige_segunda_persona"),
        (
            f"| Palabras que quedan iguales | {pct(fraude['palabras_iguales']['valor'])} | "
            f"{pct(legitimo['palabras_iguales']['valor'])} |"
        ),
        "",
        "| Pista de la tarjeta | Phishing | Legítimos |",
        "|---|---|---|",
    ]
    for grupo, prefijo in (("por_pedido", "Pide"), ("por_presion", "Presiona con")):
        for nombre in sorted(set(fraude[grupo]) | set(legitimo[grupo])):
            celdas = [
                celda(d[grupo], nombre) if nombre in d[grupo] else "0,0 %"
                for d in (fraude, legitimo)
            ]
            lineas.append(f"| {prefijo}: {nombre} | " + " | ".join(celdas) + " |")
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
    revision, datos_revision = tabla_revision()
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
    if revision:
        partes += ["", "## Prueba 4: la sala de revisión sobre correos reales", "", *revision]
    salida = RESULTADOS / (
        "resumen.md" if args.particion == "test" else f"resumen-{args.particion}.md"
    )
    salida.write_text("\n".join(partes) + "\n", encoding="utf-8")
    (salida.with_suffix(".json")).write_text(
        json.dumps(
            {
                "filtro": datos_filtro,
                "bot": datos_bot,
                "phishing": datos_phishing,
                "revision": datos_revision,
            },
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

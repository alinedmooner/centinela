"""Prueba 3: ¿el revisor reconoce el phishing en español y nombra el truco?

Usa SpaPhish, 1395 correos reales en español con etiquetas de tres anotadores. El conjunto
no se redistribuye con Centinela: hay que tener una copia local y pasar su ruta::

    uv run --extra evals python evals/phishing.py --spaphish "RUTA/Spaphish dataset - DiB.csv"

Se guardan las respuestas del modelo por identificador, sin el texto de los correos, y un
resumen con las métricas. La línea base es un clasificador clásico (TF-IDF y regresión
logística) entrenado y probado con validación cruzada sobre el mismo conjunto.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _comun import RESULTADOS, escribir_jsonl, leer_jsonl, proporcion
from casos import leer_spaphish, texto_de_correo

from centinela import DetectorLLM
from centinela._env import cargar_env

#: Truco de Centinela -> columna de consenso de SpaPhish.
COLUMNAS = {
    "autoridad": "authority",
    "prueba_social": "social_proof",
    "simpatia_engano": "liking_similarity_deception",
    "compromiso_reciprocidad": "commitment_integrity_reciprocation",
    "distraccion_urgencia": "distraction",
}


def medidas(predichos: list[bool], reales: list[bool]) -> dict:
    """Aciertos, precisión, cobertura y F1 de la clase positiva."""
    vp = sum(p and r for p, r in zip(predichos, reales, strict=True))
    fp = sum(p and not r for p, r in zip(predichos, reales, strict=True))
    fn = sum(not p and r for p, r in zip(predichos, reales, strict=True))
    vn = sum(not p and not r for p, r in zip(predichos, reales, strict=True))
    precision = vp / (vp + fp) if vp + fp else 0.0
    cobertura = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * precision * cobertura / (precision + cobertura) if precision + cobertura else 0.0
    return {
        "aciertos": proporcion(vp + vn, len(reales)),
        "precision": precision,
        "cobertura": cobertura,
        "f1": f1,
        "matriz": {"vp": vp, "fp": fp, "fn": fn, "vn": vn},
    }


def revisar_con_modelo(
    filas: list[dict], modelo: str, hilos: int, archivo: Path
) -> dict[str, dict]:
    from centinela.proveedores.anthropic import ProveedorAnthropic

    guardadas = {f["id"]: f for f in leer_jsonl(archivo)}
    faltan = [f for f in filas if f["hash"][:16] not in guardadas]
    if not faltan:
        return guardadas
    detector = DetectorLLM(ProveedorAnthropic(modelo), max_caracteres=8000)

    def revisar(fila: dict) -> dict:
        ident = fila["hash"][:16]
        for intento in range(3):
            try:
                h = detector.revisar(texto_de_correo(fila))
                return {
                    "id": ident,
                    "engano": h.engano_a_personas,
                    "ordenes": h.ordenes_para_ia,
                    "trucos": list(h.trucos),
                    **({"error": h.error} if h.error else {}),
                }
            except Exception as error:  # noqa: BLE001 - se reintenta y, si no, queda como error
                ultimo = type(error).__name__
                time.sleep(2 * (intento + 1))
        return {"id": ident, "engano": False, "ordenes": False, "trucos": [], "error": ultimo}

    inicio = time.time()
    with ThreadPoolExecutor(max_workers=hilos) as grupo:
        for respuesta in grupo.map(revisar, faltan):
            guardadas[respuesta["id"]] = respuesta
    print(f"{modelo}: {len(faltan)} correos en {time.time() - inicio:.0f} s", file=sys.stderr)
    escribir_jsonl(archivo, [guardadas[i] for i in sorted(guardadas)])
    return guardadas


def linea_base(filas: list[dict]) -> list[bool]:
    """TF-IDF y regresión logística, con validación cruzada de 5 partes."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline

    textos = [texto_de_correo(f) for f in filas]
    reales = [f["Label"] == "1" for f in filas]
    modelo = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        LogisticRegression(max_iter=1000),
    )
    partes = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    return [bool(p) for p in cross_val_predict(modelo, textos, reales, cv=partes)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--spaphish", type=Path, required=True, help="copia local del CSV de SpaPhish"
    )
    parser.add_argument("--modelo", default="claude-haiku-5-5")
    parser.add_argument("--hilos", type=int, default=16)
    parser.add_argument("--maximo", type=int, default=None, help="usa solo los primeros N correos")
    args = parser.parse_args(argv)

    cargar_env()
    filas = sorted(leer_spaphish(args.spaphish), key=lambda f: f["hash"])[: args.maximo]
    carpeta = RESULTADOS / "phishing"
    respuestas = revisar_con_modelo(
        filas, args.modelo, args.hilos, carpeta / f"{args.modelo}.jsonl"
    )

    reales = [f["Label"] == "1" for f in filas]
    del_modelo = [respuestas[f["hash"][:16]] for f in filas]
    errores = sum(1 for r in del_modelo if r.get("error"))
    resumen = {
        "correos": len(filas),
        "phishing": sum(reales),
        "modelo": args.modelo,
        "respuestas_con_error": errores,
        "deteccion": {
            "modelo": medidas([r["engano"] for r in del_modelo], reales),
            "base_tfidf": medidas(linea_base(filas), reales),
        },
        "ordenes_para_ia_en_correos_legitimos": proporcion(
            sum(r["ordenes"] for r, real in zip(del_modelo, reales, strict=True) if not real),
            len(reales) - sum(reales),
        ),
        "trucos": {},
    }
    f1_modelo, f1_mayoria = [], []
    for truco, columna in COLUMNAS.items():
        consenso = [f[columna] == "1" for f in filas]
        mayoria = [sum(consenso) * 2 >= len(consenso)] * len(consenso)
        m = medidas([truco in r["trucos"] for r in del_modelo], consenso)
        b = medidas(mayoria, consenso)
        resumen["trucos"][truco] = {
            "frecuencia": sum(consenso) / len(consenso),
            "f1_modelo": m["f1"],
            "aciertos_modelo": m["aciertos"]["valor"],
            "f1_mayoria": b["f1"],
            "aciertos_mayoria": b["aciertos"]["valor"],
        }
        f1_modelo.append(m["f1"])
        f1_mayoria.append(b["f1"])
    resumen["trucos_f1_promedio"] = {
        "modelo": sum(f1_modelo) / len(f1_modelo),
        "mayoria": sum(f1_mayoria) / len(f1_mayoria),
    }

    (carpeta / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    d = resumen["deteccion"]
    print(f"Correos: {len(filas)} ({sum(reales)} de phishing). Respuestas con error: {errores}")
    for nombre in ("modelo", "base_tfidf"):
        m = d[nombre]
        print(
            f"  {nombre:11s} aciertos {100 * m['aciertos']['valor']:.1f} %  precisión "
            f"{100 * m['precision']:.1f} %  cobertura {100 * m['cobertura']:.1f} %  F1 {m['f1']:.3f}"
        )
    for truco, t in resumen["trucos"].items():
        print(
            f"  truco {truco:24s} F1 modelo {t['f1_modelo']:.3f}  F1 mayoría {t['f1_mayoria']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

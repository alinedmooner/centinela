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

from _common import RESULTS, proportion, read_jsonl, write_jsonl
from cases import mail_text, read_spaphish

from centinela import LLMDetector
from centinela._env import load_env

#: Truco de Centinela -> columna de consenso de SpaPhish.
COLUMNS = {
    "autoridad": "authority",
    "prueba_social": "social_proof",
    "simpatia_engano": "liking_similarity_deception",
    "compromiso_reciprocidad": "commitment_integrity_reciprocation",
    "distraccion_urgencia": "distraction",
}


def measured(predicted: list[bool], reales: list[bool]) -> dict:
    """Aciertos, precisión, cobertura y F1 de la clase positiva."""
    tp = sum(p and r for p, r in zip(predicted, reales, strict=True))
    fp = sum(p and not r for p, r in zip(predicted, reales, strict=True))
    fn = sum(not p and r for p, r in zip(predicted, reales, strict=True))
    tn = sum(not p and not r for p, r in zip(predicted, reales, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    coverage = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * coverage / (precision + coverage) if precision + coverage else 0.0
    return {
        "aciertos": proportion(tp + tn, len(reales)),
        "precision": precision,
        "cobertura": coverage,
        "f1": f1,
        "matriz": {"vp": tp, "fp": fp, "fn": fn, "vn": tn},
    }


def check_with_model(rows: list[dict], model: str, threads: int, file: Path) -> dict[str, dict]:
    from centinela.providers.anthropic import AnthropicProvider

    saved = {f["id"]: f for f in read_jsonl(file)}
    missing = [f for f in rows if f["hash"][:16] not in saved]
    if not missing:
        return saved
    detector = LLMDetector(AnthropicProvider(model), max_chars=8000)

    def check(row: dict) -> dict:
        ident = row["hash"][:16]
        for attempt in range(3):
            try:
                h = detector.check(mail_text(row))
                return {
                    "id": ident,
                    "engano": h.people_deception,
                    "ordenes": h.ai_instructions,
                    "trucos": list(h.tricks),
                    **({"error": h.error} if h.error else {}),
                }
            except Exception as error:  # noqa: BLE001 - se reintenta y, si no, queda como error
                last = type(error).__name__
                time.sleep(2 * (attempt + 1))
        return {"id": ident, "engano": False, "ordenes": False, "trucos": [], "error": last}

    start = time.time()
    with ThreadPoolExecutor(max_workers=threads) as group:
        for response in group.map(check, missing):
            saved[response["id"]] = response
    print(f"{model}: {len(missing)} correos en {time.time() - start:.0f} s", file=sys.stderr)
    write_jsonl(file, [saved[i] for i in sorted(saved)])
    return saved


def baseline(rows: list[dict]) -> list[bool]:
    """TF-IDF y regresión logística, con validación cruzada de 5 partes."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline

    texts = [mail_text(f) for f in rows]
    reales = [f["Label"] == "1" for f in rows]
    model = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        LogisticRegression(max_iter=1000),
    )
    parts = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    return [bool(p) for p in cross_val_predict(model, texts, reales, cv=parts)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--spaphish", type=Path, required=True, help="copia local del CSV de SpaPhish"
    )
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--maximum", type=int, default=None, help="usa solo los primeros N correos")
    args = parser.parse_args(argv)

    load_env()
    rows = sorted(read_spaphish(args.spaphish), key=lambda f: f["hash"])[: args.maximum]
    folder = RESULTS / "phishing"
    responses = check_with_model(rows, args.model, args.threads, folder / f"{args.model}.jsonl")

    reales = [f["Label"] == "1" for f in rows]
    from_model = [responses[f["hash"][:16]] for f in rows]
    errors = sum(1 for r in from_model if r.get("error"))
    summary = {
        "correos": len(rows),
        "phishing": sum(reales),
        "modelo": args.model,
        "respuestas_con_error": errors,
        "deteccion": {
            "modelo": measured([r["engano"] for r in from_model], reales),
            "base_tfidf": measured(baseline(rows), reales),
        },
        "ordenes_para_ia_en_correos_legitimos": proportion(
            sum(r["ordenes"] for r, real in zip(from_model, reales, strict=True) if not real),
            len(reales) - sum(reales),
        ),
        "trucos": {},
    }
    f1_model, f1_majority = [], []
    for trick, column in COLUMNS.items():
        consensus = [f[column] == "1" for f in rows]
        majority = [sum(consensus) * 2 >= len(consensus)] * len(consensus)
        m = measured([trick in r["trucos"] for r in from_model], consensus)
        b = measured(majority, consensus)
        summary["trucos"][trick] = {
            "frecuencia": sum(consensus) / len(consensus),
            "f1_modelo": m["f1"],
            "aciertos_modelo": m["aciertos"]["valor"],
            "f1_mayoria": b["f1"],
            "aciertos_mayoria": b["aciertos"]["valor"],
        }
        f1_model.append(m["f1"])
        f1_majority.append(b["f1"])
    summary["trucos_f1_promedio"] = {
        "modelo": sum(f1_model) / len(f1_model),
        "mayoria": sum(f1_majority) / len(f1_majority),
    }

    (folder / "resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    d = summary["deteccion"]
    print(f"Correos: {len(rows)} ({sum(reales)} de phishing). Respuestas con error: {errors}")
    for name in ("modelo", "base_tfidf"):
        m = d[name]
        print(
            f"  {name:11s} aciertos {100 * m['aciertos']['valor']:.1f} %  precisión "
            f"{100 * m['precision']:.1f} %  cobertura {100 * m['cobertura']:.1f} %  F1 {m['f1']:.3f}"
        )
    for trick, t in summary["trucos"].items():
        print(
            f"  truco {trick:24s} F1 modelo {t['f1_modelo']:.3f}  F1 mayoría {t['f1_mayoria']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

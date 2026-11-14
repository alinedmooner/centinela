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

from _comun import RESULTADOS, escribir_jsonl, leer_jsonl, proporcion
from casos import casos_de_spaphish, casos_del_banco

from centinela import ETIQUETAS_LEADS, DetectorLLM, DetectorLocal, DetectorReglas
from centinela._env import cargar_env
from centinela.detectores.local import frases, trozos

DETECTORES = ("reglas", "llamafirewall", "local", "local_traduccion", "claude")

#: Patrón por defecto de LlamaFirewall para inyección de instrucciones (Meta, licencia MIT).
#: Sirve como línea base de «lo que ya existe» en reglas.
PATRON_LLAMAFIREWALL = re.compile(
    r"ignore previous instructions|ignore all instructions", re.IGNORECASE | re.DOTALL
)


def _reglas(casos: list[dict]) -> dict[str, dict]:
    detector = DetectorReglas(etiquetas=ETIQUETAS_LEADS)
    return {c["id"]: {"marcado": detector.revisar(c["texto"]).ordenes_para_ia} for c in casos}


def _llamafirewall(casos: list[dict]) -> dict[str, dict]:
    return {c["id"]: {"marcado": bool(PATRON_LLAMAFIREWALL.search(c["texto"]))} for c in casos}


def _claude(casos: list[dict], modelo: str, hilos: int) -> dict[str, dict]:
    from centinela.proveedores.anthropic import ProveedorAnthropic

    detector = DetectorLLM(ProveedorAnthropic(modelo), max_caracteres=8000)

    def revisar(caso: dict) -> tuple[str, dict]:
        for intento in range(3):
            try:
                h = detector.revisar(caso["texto"])
                break
            except Exception as error:  # noqa: BLE001 - se reintenta y, si no, cuenta como fallo
                h = None
                ultimo = f"{type(error).__name__}"
                time.sleep(2 * (intento + 1))
        if h is None:
            return caso["id"], {"marcado": True, "error": ultimo}
        return caso["id"], {
            # Un detector que no pudo responder cuenta como marcado: decide una persona.
            "marcado": h.ordenes_para_ia or h.error is not None,
            "engano": h.engano_a_personas,
            "trucos": list(h.trucos),
            **({"error": h.error} if h.error else {}),
        }

    with ThreadPoolExecutor(max_workers=hilos) as grupo:
        return dict(grupo.map(revisar, casos))


def _local(casos: list[dict], traducir: bool) -> dict[str, dict]:
    textos = {c["id"]: c["texto"] for c in casos}
    if traducir:
        # Primero se traduce todo y se libera el traductor; así no hay dos modelos en memoria.
        traductor = DetectorLocal(traducir=True)._traduccion()
        for caso in casos:
            if caso["idioma"] == "es":
                textos[caso["id"]] = " ".join(traductor(frases(caso["texto"])))
        del traductor
        gc.collect()
    clasificar = DetectorLocal()._clasificacion()
    salida = {}
    for caso in casos:
        puntaje = max(clasificar(trozos(textos[caso["id"]])))
        salida[caso["id"]] = {"marcado": puntaje >= 0.5, "puntaje": round(puntaje, 4)}
    return salida


def correr(detector: str, casos: list[dict], args: argparse.Namespace) -> dict[str, dict]:
    if detector == "reglas":
        return _reglas(casos)
    if detector == "llamafirewall":
        return _llamafirewall(casos)
    if detector == "claude":
        return _claude(casos, args.modelo, args.hilos)
    return _local(casos, traducir=detector == "local_traduccion")


def resumir(casos: list[dict], respuestas: dict[str, dict]) -> dict:
    """Ataques detectados y falsas alarmas, por grupo e idioma."""
    cuenta: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for caso in casos:
        respuesta = respuestas.get(caso["id"])
        if respuesta is None:
            continue
        clave = (caso["grupo"], caso["idioma"], caso["positivo"])
        cuenta[clave][0] += int(respuesta["marcado"])
        cuenta[clave][1] += 1
    return {
        f"{grupo}|{idioma}": {"positivo": positivo, **proporcion(k, n)}
        for (grupo, idioma, positivo), (k, n) in sorted(cuenta.items())
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--particion", choices=("dev", "test"), default="test")
    parser.add_argument(
        "--detectores", nargs="+", choices=DETECTORES, default=["reglas", "llamafirewall"]
    )
    parser.add_argument(
        "--spaphish", type=Path, help="copia local de SpaPhish (no se redistribuye)"
    )
    parser.add_argument("--max-spaphish", type=int, default=None)
    parser.add_argument("--modelo", default="claude-haiku-5-5")
    parser.add_argument("--hilos", type=int, default=16)
    parser.add_argument("--rehacer", action="store_true", help="ignora las respuestas guardadas")
    args = parser.parse_args(argv)

    cargar_env()
    casos = casos_del_banco(args.particion)
    if args.spaphish:
        casos += casos_de_spaphish(args.spaphish, args.particion, args.max_spaphish)
    carpeta = RESULTADOS / "filtro" / args.particion
    print(f"{len(casos)} casos en la partición «{args.particion}»", file=sys.stderr)

    for detector in args.detectores:
        archivo = carpeta / f"{detector}.jsonl"
        guardadas = {} if args.rehacer else {f["id"]: f for f in leer_jsonl(archivo)}
        faltan = [c for c in casos if c["id"] not in guardadas]
        if faltan:
            inicio = time.time()
            nuevas = correr(detector, faltan, args)
            segundos = time.time() - inicio
            print(f"{detector}: {len(faltan)} casos en {segundos:.0f} s", file=sys.stderr)
            guardadas.update({i: {"id": i, **r} for i, r in nuevas.items()})
            escribir_jsonl(archivo, [guardadas[i] for i in sorted(guardadas)])
        resumen = resumir(casos, guardadas)
        print(f"\n== {detector} ==")
        for clave, p in resumen.items():
            nombre = "ataques detectados" if p["positivo"] else "falsas alarmas"
            print(f"  {clave:32s} {nombre:20s} {p['k']:4d}/{p['n']:<4d} {100 * p['valor']:5.1f} %")

    # Índice de casos sin texto, para rehacer las tablas sin los datos privados.
    indice = [{k: c[k] for k in ("id", "grupo", "idioma", "positivo", "detalle")} for c in casos]
    existentes = {f["id"]: f for f in leer_jsonl(carpeta / "casos.jsonl")}
    existentes.update({f["id"]: f for f in indice})
    escribir_jsonl(carpeta / "casos.jsonl", [existentes[i] for i in sorted(existentes)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Utilidades que comparten las pruebas: archivos, huellas e intervalos de confianza."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterable
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
#: Carpeta del banco de pruebas. Se puede cambiar con la variable CENTINELA_DATOS.
DATOS = Path(os.environ.get("CENTINELA_DATOS", RAIZ / "datos"))
RESULTADOS = RAIZ / "resultados"


def leer_jsonl(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8") as archivo:
        return [json.loads(linea) for linea in archivo if linea.strip()]


def escribir_jsonl(ruta: Path, filas: Iterable[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n")


def huella(texto: str) -> str:
    """Identificador corto y estable de un texto."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def en_dev(clave: str) -> bool:
    """Reparte de forma estable el 30 % de los elementos a la partición ``dev``."""
    return int(huella(clave), 16) % 10 < 3


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson al 95 % para una proporción."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def proporcion(k: int, n: int) -> dict:
    bajo, alto = wilson(k, n)
    return {"k": k, "n": n, "valor": k / n if n else None, "ic95": [bajo, alto]}


def pct(valor: float | None) -> str:
    """Porcentaje con coma decimal, como se escribe en español."""
    return "s. d." if valor is None else f"{valor * 100:.1f} %".replace(".", ",")


def pct_ic(p: dict) -> str:
    if not p["n"]:
        return "s. d."
    bajo, alto = p["ic95"]
    return f"{pct(p['valor'])} ({p['k']}/{p['n']}; IC 95 %: {pct(bajo)} a {pct(alto)})"

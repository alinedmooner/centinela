"""Utilidades que comparten las pruebas: archivos, huellas e intervalos de confianza."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: Carpeta del banco de pruebas. Se puede cambiar con la variable CENTINELA_DATOS.
DATA = Path(os.environ.get("CENTINELA_DATOS", ROOT / "data"))
RESULTS = ROOT / "results"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def fingerprint(text: str) -> str:
    """Identificador corto y estable de un texto."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def in_dev(key: str) -> bool:
    """Reparte de forma estable el 30 % de los elementos a la partición ``dev``."""
    return int(fingerprint(key), 16) % 10 < 3


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson al 95 % para una proporción."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, center - margin), min(1.0, center + margin))


def proportion(k: int, n: int) -> dict:
    low, alto = wilson(k, n)
    return {"k": k, "n": n, "valor": k / n if n else None, "ic95": [low, alto]}


def pct(value: float | None) -> str:
    """Porcentaje con coma decimal, como se escribe en español."""
    return "s. d." if value is None else f"{value * 100:.1f} %".replace(".", ",")


def pct_ci(p: dict) -> str:
    if not p["n"]:
        return "s. d."
    low, alto = p["ic95"]
    return f"{pct(p['valor'])} ({p['k']}/{p['n']}; IC 95 %: {pct(low)} a {pct(alto)})"

"""Carga un archivo ``.env`` sin depender de ningún paquete."""

from __future__ import annotations

import os
from pathlib import Path


def cargar_env(inicio: Path | None = None) -> Path | None:
    """Busca ``.env`` en la carpeta actual o en las superiores y carga sus variables.

    No pisa las variables que ya existen en el entorno. Devuelve la ruta que cargó.
    """
    carpeta = (inicio or Path.cwd()).resolve()
    for candidata in (carpeta, *carpeta.parents):
        ruta = candidata / ".env"
        if ruta.is_file():
            for linea in ruta.read_text(encoding="utf-8").splitlines():
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))
            return ruta
    return None

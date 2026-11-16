"""Carga un archivo ``.env`` sin depender de ningún paquete."""

from __future__ import annotations

import os
from pathlib import Path


def load_env(start: Path | None = None) -> Path | None:
    """Busca ``.env`` en la carpeta actual o en las superiores y carga sus variables.

    No pisa las variables que ya existen en el entorno. Devuelve la ruta que cargó.
    """
    folder = (start or Path.cwd()).resolve()
    for candidate in (folder, *folder.parents):
        path = candidate / ".env"
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            return path
    return None

"""Loads a ``.env`` file without depending on any package."""

from __future__ import annotations

import os
from pathlib import Path


def load_env(start: Path | None = None) -> Path | None:
    """Looks for ``.env`` in the current folder or any parent folder and loads its variables.

    Does not overwrite variables that already exist in the environment. Returns the path it loaded.
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

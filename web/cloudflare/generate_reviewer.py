"""Escribe src/revisor.js con las instrucciones, el esquema y los trucos del revisor.

El Worker de la web usa el mismo revisor que la librería (DetectorLLM). Este script copia
los textos desde Python para que no se separen; una prueba verifica que coinciden:

    uv run python web/cloudflare/generate_reviewer.py
"""

import json
from pathlib import Path

from centinela.detectors.llm import INSTRUCTIONS, SCHEMA
from centinela.verdict import TRICKS

DESTINATION = Path(__file__).resolve().parent / "src" / "reviewer.js"


def _js(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def content() -> str:
    return (
        "// Generado con `uv run python web/cloudflare/generate_reviewer.py` desde\n"
        "// src/centinela/detectors/llm.py and src/centinela/verdict.py. Do not edit it by hand:\n"
        "// una prueba de Python verifica que coincide con la librería.\n"
        f"export const INSTRUCCIONES = {_js(INSTRUCTIONS)};\n\n"
        f"export const ESQUEMA = {_js(SCHEMA)};\n\n"
        f"export const TRUCOS = {_js(TRICKS)};\n"
    )


if __name__ == "__main__":
    DESTINATION.parent.mkdir(exist_ok=True)
    DESTINATION.write_text(content(), encoding="utf-8")
    print(f"Escrito {DESTINATION}")

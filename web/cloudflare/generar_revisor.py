"""Escribe src/revisor.js con las instrucciones, el esquema y los trucos del revisor.

El Worker de la web usa el mismo revisor que la librería (DetectorLLM). Este script copia
los textos desde Python para que no se separen; una prueba verifica que coinciden:

    uv run python web/cloudflare/generar_revisor.py
"""

import json
from pathlib import Path

from centinela.detectores.llm import ESQUEMA, INSTRUCCIONES
from centinela.tipos import TRUCOS

DESTINO = Path(__file__).resolve().parent / "src" / "revisor.js"


def _js(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2)


def contenido() -> str:
    return (
        "// Generado con `uv run python web/cloudflare/generar_revisor.py` desde\n"
        "// src/centinela/detectores/llm.py y src/centinela/tipos.py. No lo editen a mano:\n"
        "// una prueba de Python verifica que coincide con la librería.\n"
        f"export const INSTRUCCIONES = {_js(INSTRUCCIONES)};\n\n"
        f"export const ESQUEMA = {_js(ESQUEMA)};\n\n"
        f"export const TRUCOS = {_js(TRUCOS)};\n"
    )


if __name__ == "__main__":
    DESTINO.parent.mkdir(exist_ok=True)
    DESTINO.write_text(contenido(), encoding="utf-8")
    print(f"Escrito {DESTINO}")

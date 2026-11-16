"""El revisor en vivo de la web usa las mismas instrucciones y el mismo esquema que la librería."""

import runpy
from pathlib import Path

from centinela.detectors.llm import INSTRUCTIONS

GENERATOR = Path(__file__).resolve().parent.parent / "web" / "cloudflare" / "generate_reviewer.py"


def test_el_revisor_de_la_web_coincide_con_la_libreria():
    modulo = runpy.run_path(str(GENERATOR))
    actual = modulo["DESTINATION"].read_text(encoding="utf-8")
    assert actual == modulo["content"](), (
        "web/cloudflare/src/revisor.js está desactualizado: "
        "uv run python web/cloudflare/generar_revisor.py"
    )


def test_la_unica_llave_de_las_instrucciones_es_la_marca():
    # El Worker cambia {marker} con replaceAll; Python usa format. Deben dar lo mismo.
    assert INSTRUCTIONS.format(marker="x") == INSTRUCTIONS.replace("{marker}", "x")

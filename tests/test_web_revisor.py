"""El revisor en vivo de la web usa las mismas instrucciones y el mismo esquema que la librería."""

import runpy
from pathlib import Path

from centinela.detectores.llm import INSTRUCCIONES

GENERADOR = Path(__file__).resolve().parent.parent / "web" / "cloudflare" / "generar_revisor.py"


def test_el_revisor_de_la_web_coincide_con_la_libreria():
    modulo = runpy.run_path(str(GENERADOR))
    actual = modulo["DESTINO"].read_text(encoding="utf-8")
    assert actual == modulo["contenido"](), (
        "web/cloudflare/src/revisor.js está desactualizado: "
        "uv run python web/cloudflare/generar_revisor.py"
    )


def test_la_unica_llave_de_las_instrucciones_es_la_marca():
    # El Worker cambia {marca} con replaceAll; Python usa format. Deben dar lo mismo.
    assert INSTRUCCIONES.format(marca="x") == INSTRUCCIONES.replace("{marca}", "x")

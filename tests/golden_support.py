"""Ayudas para comparar lo que hace Centinela hoy con las salidas de referencia.

Las salidas de referencia están en tests/golden/main_9810607/ y salieron del código de
main@9810607, antes de pasar el proyecto a inglés (ver tests/golden/README.md).
"""

from __future__ import annotations

import contextlib
import io
import json
import runpy
from pathlib import Path

from centinela import ETIQUETAS_LEADS, DetectorReglas, Guardia, Veredicto
from centinela.cli import main as cli_main

RAIZ = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden" / "main_9810607"
EJEMPLOS = RAIZ / "ejemplos"
ETIQUETAS_CLINICA = EJEMPLOS / "etiquetas_clinica.json"


def cargar(nombre: str):
    return json.loads((GOLDEN / nombre).read_text(encoding="utf-8"))


def como_texto(valor) -> str:
    """JSON con el orden de las claves: el orden del esquema también lo ve el modelo."""
    return json.dumps(valor, ensure_ascii=False, indent=1)


def via_json(valor):
    """Lo que daría el valor al escribirlo y leerlo como JSON (las tuplas pasan a listas)."""
    return json.loads(json.dumps(valor, ensure_ascii=False))


MENSAJES: dict[str, str] = {m["id"]: m["text"] for m in cargar("messages.json")}

GUARDIA = Guardia([DetectorReglas(etiquetas=ETIQUETAS_LEADS)])

#: Para los mensajes que las reglas solas no marcan: un engaño dirigido a una persona.
VEREDICTO_A_MANO = Veredicto(
    decision="revisar",
    ordenes_para_ia=False,
    engano_a_personas=True,
    trucos=("autoridad", "distraccion_urgencia"),
    evidencias=(),
    aviso="Parece un engaño dirigido a una persona.",
)


def veredicto_de(id_: str) -> Veredicto:
    """El veredicto de las reglas, o el armado a mano si las reglas no lo marcan."""
    veredicto = GUARDIA.revisar(MENSAJES[id_])
    return veredicto if veredicto.decision == "revisar" else VEREDICTO_A_MANO


def cli(*argv: str) -> dict:
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            codigo = cli_main(list(argv))
        except SystemExit as salir:  # --version y los errores de argparse salen así
            codigo = salir.code
    return {"exit": codigo, "stdout": salida.getvalue(), "stderr": error.getvalue()}


def correos_de_la_demo():
    """Los cinco correos ficticios de ejemplos/enviar_pruebas.py."""
    envio = runpy.run_path(str(EJEMPLOS / "enviar_pruebas.py"))
    return envio["construir_mensajes"]("pruebas@example.com", "agente@example.org")


class ProveedorFalso:
    """Un modelo de mentira que anota lo que recibe."""

    nombre = "falso"

    def __init__(self, respuesta=None, error=None):
        self.respuesta, self.error, self.llamadas = respuesta, error, []

    def responder_json(self, *, sistema, mensaje, esquema):
        self.llamadas.append({"sistema": sistema, "mensaje": mensaje, "esquema": esquema})
        if self.error:
            raise self.error
        return self.respuesta

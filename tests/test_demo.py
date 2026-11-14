"""La demostración debe correr sin clave ni internet."""

import runpy
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "ejemplos" / "demo_bandeja.py"


def test_la_demo_corre_sin_clave(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(DEMO)])
    modulo = runpy.run_path(str(DEMO))
    assert modulo["main"]() == 0
    salida = capsys.readouterr().out
    assert salida.count("Mensaje ") == 7
    assert "Decisión del guardia: revisar" in salida
    assert "Decisión del guardia: permitir" in salida


def test_la_demo_muestra_la_sala_de_revision_con_el_mensaje_desarmado(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(DEMO)])
    runpy.run_path(str(DEMO))["main"]()
    tarjetas = [linea for linea in capsys.readouterr().out.splitlines() if "║" in linea]
    sala = "\n".join(tarjetas)
    assert "REVISIÓN HUMANA" in sala and "Decisiones posibles" in sala
    assert "hxxp://soporte-nubeclara[.]example[.]com/verificar" in sala
    assert "http://" not in sala and "555 0142" not in sala

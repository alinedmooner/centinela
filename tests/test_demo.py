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
    assert salida.count("Mensaje ") == 6
    assert "Decisión del guardia: revisar" in salida
    assert "Decisión del guardia: permitir" in salida

"""La demostración debe correr sin clave ni internet."""

import runpy
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "examples" / "inbox_demo.py"


def test_la_demo_corre_sin_clave(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(DEMO)])
    modulo = runpy.run_path(str(DEMO))
    assert modulo["main"]() == 0
    output = capsys.readouterr().out
    assert output.count("Mensaje ") == 7
    assert "Decisión del guardia: revisar" in output
    assert "Decisión del guardia: permitir" in output


def test_la_demo_muestra_la_sala_de_revision_con_el_mensaje_desarmado(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(DEMO)])
    runpy.run_path(str(DEMO))["main"]()
    cards = [line for line in capsys.readouterr().out.splitlines() if "║" in line]
    room = "\n".join(cards)
    assert "REVISIÓN HUMANA" in room and "Decisiones posibles" in room
    assert "hxxp://soporte-nubeclara[.]example[.]com/verificar" in room
    assert "http://" not in room and "555 0142" not in room

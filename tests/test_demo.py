"""The demo must run without a key or internet, in English and in Spanish."""

import runpy
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parent.parent / "examples" / "inbox_demo.py"


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", [str(DEMO), *args])
    return runpy.run_path(str(DEMO))["main"]()


def test_the_demo_runs_without_a_key(capsys, monkeypatch):
    assert run(monkeypatch) == 0
    output = capsys.readouterr().out
    assert output.count("Message ") == 7
    assert "Guard decision: review" in output
    assert "Guard decision: allow" in output


def test_the_demo_runs_in_spanish(capsys, monkeypatch):
    assert run(monkeypatch, "--lang", "es") == 0
    output = capsys.readouterr().out
    assert output.count("Mensaje ") == 7
    assert "Decisión del guardia: revisar" in output
    assert "Decisión del guardia: permitir" in output


@pytest.mark.parametrize(
    "lang, title, decisions",
    [
        ("en", "HUMAN REVIEW", "Possible decisions"),
        ("es", "REVISIÓN HUMANA", "Decisiones posibles"),
    ],
)
def test_the_demo_shows_the_review_room_with_the_defanged_message(
    capsys, monkeypatch, lang, title, decisions
):
    run(monkeypatch, "--lang", lang)
    cards = [line for line in capsys.readouterr().out.splitlines() if "║" in line]
    room = "\n".join(cards)
    assert title in room and decisions in room
    assert "hxxp://soporte-nubeclara[.]example[.]com/verificar" in room
    assert "http://" not in room and "555 0142" not in room

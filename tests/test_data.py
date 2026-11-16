"""Los datos del banco de pruebas deben pasar el validador."""

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("ataques.jsonl", "portadores.jsonl", "leads.jsonl")


def load_validator():
    """Importa scripts/validar_datos.py por su ruta (no es parte del paquete)."""
    path = ROOT / "scripts" / "validate_data.py"
    spec = importlib.util.spec_from_file_location("validar_datos", path)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_los_datos_pasan_el_validador():
    assert load_validator().main() == 0


def test_el_validador_rechaza_datos_rotos(tmp_path):
    for name in FILES:
        shutil.copy(ROOT / "data" / name, tmp_path / name)
    with (tmp_path / "leads.jsonl").open("a", encoding="utf-8") as file:
        file.write('{"id": "lead-001", "texto": "línea de más"}\n')
    assert load_validator().main(tmp_path) == 1

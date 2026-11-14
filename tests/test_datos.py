"""Los datos del banco de pruebas deben pasar el validador."""

import importlib.util
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVOS = ("ataques.jsonl", "portadores.jsonl", "leads.jsonl")


def cargar_validador():
    """Importa scripts/validar_datos.py por su ruta (no es parte del paquete)."""
    ruta = RAIZ / "scripts" / "validar_datos.py"
    spec = importlib.util.spec_from_file_location("validar_datos", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_los_datos_pasan_el_validador():
    assert cargar_validador().main() == 0


def test_el_validador_rechaza_datos_rotos(tmp_path):
    for nombre in ARCHIVOS:
        shutil.copy(RAIZ / "datos" / nombre, tmp_path / nombre)
    with (tmp_path / "leads.jsonl").open("a", encoding="utf-8") as archivo:
        archivo.write('{"id": "lead-001", "texto": "línea de más"}\n')
    assert cargar_validador().main(tmp_path) == 1

"""The benchmark data must pass the validator."""

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("ataques.jsonl", "portadores.jsonl", "leads.jsonl")


def load_validator():
    """Import scripts/validate_data.py by its path (it is not part of the package)."""
    path = ROOT / "scripts" / "validate_data.py"
    spec = importlib.util.spec_from_file_location("validate_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_data_passes_the_validator():
    assert load_validator().main() == 0


def test_the_validator_rejects_broken_data(tmp_path):
    for name in FILES:
        shutil.copy(ROOT / "data" / name, tmp_path / name)
    with (tmp_path / "leads.jsonl").open("a", encoding="utf-8") as file:
        file.write('{"id": "lead-001", "texto": "línea de más"}\n')
    assert load_validator().main(tmp_path) == 1

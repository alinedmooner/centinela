import tomllib
from pathlib import Path

import centinela


def test_la_version_del_paquete_coincide_con_pyproject():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert centinela.__version__ == version

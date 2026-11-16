import tomllib
from pathlib import Path

import centinela


def test_the_package_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert centinela.__version__ == version

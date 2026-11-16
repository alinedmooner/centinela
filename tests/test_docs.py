"""The documents only name things that exist: imports, command-line flags and repository paths."""

import ast
import importlib
import re
import runpy
from pathlib import Path

import pytest

from centinela.cli import _parser

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = [
    "README.md",
    "README.es.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "ATTRIBUTIONS.md",
    "data/README.md",
    "results/README.md",
    "docs/pitch.md",
    "docs/pitch.es.md",
]  # docs/migrating-to-0.2.md lists the old names on purpose; tests/test_migration_guide.py covers it
DOCS = [ROOT / name for name in CANDIDATES if (ROOT / name).exists()]
FENCE = re.compile(r"^```(\w*)[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)
INLINE = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\]\(([^)\s]+)\)")
PATH = re.compile(r"^(?:src|tests|evals|examples|data|results|docs|scripts|web)/[\w./-]*[\w/]$")
TOP_LEVEL = {"src", "tests", "evals", "examples", "data", "results", "docs", "scripts", "web"}
RELATIVE = re.compile(r"^([a-z_]+)/[\w./<>{}*-]+$")
#: Names of version 0.1 (modules, flags, folders, variables) that no document may use any more.
OLD_NAMES = (
    "centinela revisar",
    "centinela clasificar",
    "--archivo",
    "--etiquetas",
    "--proveedor",
    "--modelo",
    "--tarjeta",
    "--solo-de",
    "--mover",
    "Guardia(",
    "DetectorReglas",
    "DetectorLLM",
    "ClasificadorSeguro",
    "crear_tarjeta",
    "texto_de_tarjeta",
    "buzon_seguro",
    "centinela.correo",
    "responder_json",
    "resultados/",
    "ejemplos/",
    "datos/",
    "ATRIBUCIONES",
    "BUZON_",
    "PRUEBAS_",
    "COMPOSIO_USUARIO",
    "CENTINELA_DATOS",
    "Centinela-Cuarentena",
    "validar_datos",
    "reglas_congeladas",
)
#: Paths the documents mention that are created or ignored locally, or that stand for a pattern.
NOT_IN_THE_REPOSITORY = ("results/raw", "data/external", "web/dist", "web/node_modules")


def code_blocks(path: Path, *languages: str):
    for match in FENCE.finditer(path.read_text(encoding="utf-8")):
        if match.group(1) in languages:
            yield match.group(2)


RUNNABLE = re.compile(r"^<!-- runnable -->\n```python[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)


def runnable_blocks(path: Path) -> list[str]:
    """The Python examples that need no key, no mailbox and no files: they carry `<!-- runnable -->`."""
    return RUNNABLE.findall(path.read_text(encoding="utf-8"))


def known_flags() -> dict[str, set[str]]:
    """The subcommands of the command line and the options of each."""
    parser = _parser("en")
    subparsers = next(a for a in parser._actions if a.choices and hasattr(a, "_name_parser_map"))
    return {
        name: {option for action in sub._actions for option in action.option_strings}
        for name, sub in subparsers.choices.items()
    }


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_python_examples_import_names_that_exist(path):
    for code in code_blocks(path, "python", "py"):
        tree = ast.parse(code)  # an example that does not parse is a broken example
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("centinela"):
                module = importlib.import_module(node.module)
                for alias in node.names:
                    if not hasattr(module, alias.name):
                        importlib.import_module(f"{node.module}.{alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("centinela"):
                        importlib.import_module(alias.name)


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_command_line_examples_use_real_commands_and_flags(path):
    flags = known_flags()
    for code in code_blocks(path, "bash", "sh", "console", "shell", "text", ""):
        for line in code.replace("\\\n", " ").splitlines():
            words = line.split("#")[0].split()
            if "centinela" not in words:
                continue
            tail = words[words.index("centinela") + 1 :]
            if not tail or tail[0].startswith(("-", "<", "...")) or tail[0] in {"|", ">"}:
                continue
            assert tail[0] in flags, f"{path.name}: unknown command in: {line.strip()}"
            for word in tail[1:]:
                if word.startswith("--") and "=" not in word:
                    assert word in flags[tail[0]], f"{path.name}: unknown flag in: {line.strip()}"
                elif word.startswith("--lang="):
                    assert "--lang" in flags[tail[0]]


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_repository_paths_in_the_documents_exist(path):
    text = path.read_text(encoding="utf-8")
    mentioned = {m.group(1).strip() for m in INLINE.finditer(text)}
    mentioned |= {
        m.group(1)
        for m in LINK.finditer(text)
        if not m.group(1).startswith(("http", "#", "mailto"))
    }
    missing = []
    for item in sorted(mentioned):
        item = item.split("#")[0].lstrip("./")
        if not PATH.match(item) or item.startswith(NOT_IN_THE_REPOSITORY):
            continue
        if any(ch in item for ch in "*<>{}"):
            continue
        if not (ROOT / item).exists() and not (path.parent / item).exists():
            missing.append(item)
    assert missing == [], f"{path.name} names files that do not exist: {missing}"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_the_documents_do_not_use_the_old_spanish_names(path):
    text = path.read_text(encoding="utf-8")
    used = [old for old in OLD_NAMES if old in text]
    assert used == [], f"{path.name} still uses names of version 0.1: {used}"


@pytest.mark.parametrize(
    "path", [p for p in DOCS if p.parent != ROOT], ids=lambda p: str(p.relative_to(ROOT))
)
def test_relative_paths_in_documents_of_a_folder_exist(path):
    """`filter/test/<detector>.jsonl` inside results/README.md: the folder it starts with must exist."""
    missing = []
    for match in INLINE.finditer(path.read_text(encoding="utf-8")):
        found = RELATIVE.match(match.group(1).strip())
        if not found or found.group(1) in TOP_LEVEL:
            continue
        prefix = re.split(r"[<>{}*]", found.group(0))[0]
        if not (path.parent / prefix).exists() and not (ROOT / prefix).exists():
            missing.append(found.group(0))
    assert missing == [], f"{path.name} names folders that do not exist: {missing}"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_runnable_examples_run(path, tmp_path, capsys):
    for number, code in enumerate(runnable_blocks(path), 1):
        example = tmp_path / f"example_{number}.py"
        example.write_text(code, encoding="utf-8")
        runpy.run_path(str(example), run_name="__example__")
        capsys.readouterr()


@pytest.mark.parametrize("name", ["README.md", "README.es.md"])
def test_the_readmes_keep_their_runnable_examples(name):
    if (ROOT / name).exists():
        assert len(runnable_blocks(ROOT / name)) >= 2, (
            f"{name} lost its `<!-- runnable -->` examples"
        )

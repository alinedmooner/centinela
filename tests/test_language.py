"""Language rules of the repository: English names, comments and documents; Spanish only on purpose.

Code, comments, docstrings and documents are English. What stays Spanish on purpose (the benchmark data,
the saved results, the model prompts, the Spanish copies of the documents, the Spanish messages used as
examples) is listed in `language_allowlist.toml`, each entry with its reason. An entry that no longer
matches anything fails the test, so the list cannot collect dead exceptions.

The checks are heuristics: a name from the old Spanish API, a comment or a line of a document that has an
accented letter or two words that only exist in Spanish. Quoted text and code spans are skipped, because
the examples are Spanish by design.
"""

import functools
import io
import re
import subprocess
import tokenize
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = Path(__file__).with_name("language_allowlist.toml")

ACCENTED = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
#: Words that are Spanish and not English. Words that are both (no, se, si, solo, es, con) are left out.
SPANISH_WORDS = re.compile(
    r"\b(el|la|los|las|del|que|para|una|por|sus|más|como|cuando|sin|ya|este|esta|cada|donde|puede|hay|"
    r"pero|también|porque|entre|desde|hasta|sobre|nuestro|nuestra|muy|tiene|están|qué|cómo)\b",
    re.IGNORECASE,
)
QUOTED = re.compile(r"«[^»\n]*»|“[^”\n]*”|\"[^\"\n]*\"")
CODE_SPAN = re.compile(r"`[^`\n]*`")
LINK_TARGET = re.compile(r"\]\([^)\n]*\)")
FENCE = re.compile(r"^\s*(```|~~~)")

#: Files that are Spanish by design: the Spanish copies of the documents and the saved reference outputs.
SPANISH_COPIES = ("README.es.md", "docs/pitch.es.md", "results/summary.es.md")
SKIPPED_PREFIXES = ("tests/golden/", "web/node_modules/", "web/dist/", "web/.astro/")
#: Old folder and file names that must not come back (the Spanish names of version 0.1).
OLD_PATH_PARTS = {
    "datos",
    "resultados",
    "ejemplos",
    "detectores",
    "proveedores",
    "ATRIBUCIONES.md",
    "pruebas.yml",
    "reglas_congeladas.txt",
}


def looks_spanish(text: str) -> bool:
    return bool(ACCENTED.search(text)) or len(SPANISH_WORDS.findall(text)) >= 2


@functools.cache
def tracked_files() -> tuple[str, ...]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("the language scan needs a git checkout")
    names = [n for n in out.decode("utf-8").split("\0") if n and (ROOT / n).is_file()]
    return tuple(sorted(n for n in names if not n.startswith(SKIPPED_PREFIXES)))


@functools.cache
def old_names() -> frozenset[str]:
    """The identifiers of the Spanish API, from the map that renamed them."""
    with (ROOT / "scripts" / "rename_map.toml").open("rb") as file:
        return frozenset(tomllib.load(file)["names"])


def python_files() -> list[str]:
    return [n for n in tracked_files() if n.endswith(".py")]


def comments_and_docstrings(source: str):
    """Yield (line, text) for every comment and every docstring of a Python file."""
    import ast

    tree = ast.parse(source)
    docstring_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            first = body[0] if body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstring_lines.add(first.lineno)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT or (
            token.type == tokenize.STRING and token.start[0] in docstring_lines
        ):
            yield token.start[0], token.string


def prose_of(line: str) -> str:
    """What is left of a line of text once quotes, code spans and link targets are taken out."""
    return QUOTED.sub(" ", CODE_SPAN.sub(" ", LINK_TARGET.sub("]", line)))


def document_lines(path: str):
    """Yield (line number, line) of a Markdown file outside the code blocks."""
    in_fence = False
    for number, line in enumerate((ROOT / path).read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            yield number, line


@functools.cache
def findings() -> tuple[dict, ...]:
    """Every place that breaks a rule, before the exceptions are applied."""
    found = []
    old = old_names()
    for path in python_files():
        source = (ROOT / path).read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME and token.string in old:
                found.append(
                    {"kind": "names", "file": path, "line": token.start[0], "token": token.string}
                )
        for line, text in comments_and_docstrings(source):
            if looks_spanish(prose_of(text)):
                found.append({"kind": "prose", "file": path, "line": line, "text": text.strip()})
    for path in tracked_files():
        if path.endswith(".md") and not path.endswith(".es.md"):
            for line, text in document_lines(path):
                if looks_spanish(prose_of(text)):
                    found.append(
                        {"kind": "prose", "file": path, "line": line, "text": text.strip()}
                    )
        parts = set(Path(path).parts)
        stem = Path(path).stem
        bad = (parts & OLD_PATH_PARTS) | ({stem} & old if path.endswith(".py") else set())
        if bad or Path(path).name in OLD_PATH_PARTS:
            found.append({"kind": "paths", "file": path, "line": 0, "text": ", ".join(sorted(bad))})
    return tuple(found)


@functools.cache
def exceptions() -> tuple[dict, ...]:
    with ALLOWLIST.open("rb") as file:
        data = tomllib.load(file)
    entries = []
    for kind in ("names", "prose", "paths"):
        for entry in data.get(kind, []):
            entries.append({**entry, "kind": kind})
    return tuple(entries)


def covers(entry: dict, finding: dict) -> bool:
    if entry["kind"] != finding["kind"] or entry["file"] != finding["file"]:
        return False
    if entry["kind"] == "names":
        return entry["token"] == finding["token"]
    if entry["kind"] == "prose":
        return entry["contains"] == "*" or entry["contains"] in finding["text"]
    return True


def where(finding: dict) -> str:
    detail = finding.get("token") or finding.get("text", "")
    return f"{finding['file']}:{finding['line']}: {detail[:90]}"


def test_nothing_is_spanish_by_accident():
    stray = [f for f in findings() if not any(covers(e, f) for e in exceptions())]
    assert stray == [], (
        "Spanish names, comments or document lines that are not in tests/language_allowlist.toml "
        "(translate them, or add an entry with its reason):\n" + "\n".join(where(f) for f in stray)
    )


def test_every_exception_is_still_needed():
    unused = [e for e in exceptions() if not any(covers(e, f) for f in findings())]
    assert unused == [], f"exceptions in tests/language_allowlist.toml that match nothing: {unused}"


def test_every_exception_has_a_reason():
    required = {"names": ("file", "token"), "prose": ("file", "contains"), "paths": ("file",)}
    for entry in exceptions():
        for key in (*required[entry["kind"]], "reason"):
            assert str(entry.get(key, "")).strip(), f"an exception without `{key}`: {entry}"
        assert len(entry["reason"].split()) >= 3, f"say why: {entry}"


def test_the_spanish_copies_are_spanish():
    for path in SPANISH_COPIES:
        if (ROOT / path).exists():
            text = prose_of((ROOT / path).read_text(encoding="utf-8"))
            assert len(SPANISH_WORDS.findall(text)) > 40, f"{path} should be written in Spanish"


def test_the_english_documents_are_not_spanish_copies_by_mistake():
    for path in ("README.md", "CONTRIBUTING.md", "SECURITY.md"):
        if (ROOT / path).exists():
            text = prose_of((ROOT / path).read_text(encoding="utf-8"))
            assert len(SPANISH_WORDS.findall(text)) < 5, f"{path} should be written in English"

"""One-shot renamer used to move the code base from Spanish to English names.

    uv run python scripts/rename_names.py scripts/rename_map.toml           # report only
    uv run python scripts/rename_names.py scripts/rename_map.toml --apply   # rewrite files

It renames NAME tokens only: identifiers, attributes, keyword arguments, the segments of
module paths in imports, and the names inside f-string fields. Strings and comments are
never touched. The map is a TOML file with a global ``[names]`` table and optional
``[overrides."glob"]`` tables for files that need another translation of the same name.

Without ``--apply`` it reports what it cannot decide on its own:

- a new name that already exists in the same file (two variables would merge);
- a new name that shadows a builtin;
- a string that is exactly a renamed name or a dotted path ending in one (``__all__``
  entries, ``monkeypatch.setattr("pkg.mod.name", ...)``, ``runpy`` lookups);
- a keyword argument whose name is also a key of a saved record in ``data/`` or ``results/``
  (renaming it would change what is written to disk);
- identifiers that look Spanish and are not in the map yet.
"""

from __future__ import annotations

import argparse
import builtins
import fnmatch
import io
import json
import keyword
import re
import sys
import tokenize
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ("src", "tests", "evals", "ejemplos", "examples", "scripts", "web/cloudflare")
SKIP_PARTS = {"node_modules", ".venv", "golden", "__pycache__", ".cloudflare"}
SKIP_FILES = {"rename_names.py"}
DICTIONARY = Path("/usr/share/dict/words")
DATA_FOLDERS = ("datos", "data", "resultados", "results")


def python_files() -> list[Path]:
    found = []
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            if SKIP_PARTS & set(path.parts) or path.name in SKIP_FILES:
                continue
            found.append(path)
    return found


def saved_record_keys() -> set[str]:
    keys: set[str] = set()
    for folder in DATA_FOLDERS:
        for path in (ROOT / folder).rglob("*.jsonl"):
            with path.open(encoding="utf-8") as file:
                for _, line in zip(range(3), file, strict=False):
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict):
                        keys.update(row)
    return keys


def effective_map(config: dict, relative: str) -> dict[str, str]:
    names = dict(config.get("names", {}))
    for pattern, table in config.get("overrides", {}).items():
        if fnmatch.fnmatch(relative, pattern):
            names.update(table)
    for pattern, table in config.get("never", {}).items():
        if fnmatch.fnmatch(relative, pattern):
            for name in table.get("names", []):
                names.pop(name, None)
    return names


#: Short words that are fine in English identifiers. Other short parts (es, de, en, la...) are
#: Spanish and must be reported.
SHORT_ENGLISH = {
    "id",
    "db",
    "is",
    "to",
    "in",
    "on",
    "at",
    "of",
    "or",
    "no",
    "up",
    "os",
    "io",
    "ok",
    "ui",
    "re",
    "by",
    "as",
    "if",
    "it",
    "my",
    "we",
    "a",
    "i",
    "e",
    "n",
    "k",
    "p",
    "s",
    "t",
    "x",
    "y",
    "z",
    "b",
    "c",
    "d",
    "f",
    "g",
    "h",
    "j",
    "l",
    "m",
    "o",
    "q",
    "r",
    "u",
    "v",
    "w",
    "ip",
    "url",
    "uid",
    "csv",
    "cli",
    "llm",
    "api",
    "tld",
    "dev",
    "ia",
    "ai",
    "py",
    "js",
    "md",
}


def looks_english(name: str, english: set[str], ignore: set[str]) -> bool:
    if name in ignore or name in dir(builtins):
        return True
    return all(
        p.isdigit() or p in SHORT_ENGLISH or (len(p) > 2 and p in english)
        for p in split_words(name)
    )


def split_words(name: str) -> list[str]:
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    return [p.lower() for p in re.split(r"_+", name) if p]


def process(path: Path, config: dict, record_keys: set[str], english: set[str]):
    ignore = set(config.get("ignore", {}).get("names", []))
    relative = path.relative_to(ROOT).as_posix()
    mapping = effective_map(config, relative)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))

    plain_names: set[str] = set()  # names not used as attributes
    edits: list[tuple[int, int, str, str]] = []  # row, col, old, new
    notes: list[str] = []
    unmapped: Counter[str] = Counter()
    significant = [t for t in tokens if t.type not in (tokenize.NL, tokenize.COMMENT)]
    depth = 0
    in_all = False
    all_depth = 0
    for i, tok in enumerate(significant):
        if tok.type == tokenize.OP and tok.string in "([{":
            depth += 1
        elif tok.type == tokenize.OP and tok.string in ")]}":
            depth -= 1
            if in_all and depth == all_depth:
                in_all = False
        if (
            tok.type == tokenize.NAME
            and tok.string == "__all__"
            and i + 1 < len(significant)
            and significant[i + 1].string in ("=", "+=")
        ):
            in_all, all_depth = True, depth
        if tok.type == tokenize.NAME and not keyword.iskeyword(tok.string):
            previous = significant[i - 1] if i else None
            is_attribute = previous is not None and previous.string == "."
            following = significant[i + 1] if i + 1 < len(significant) else None
            is_keyword_argument = (
                depth > 0
                and following is not None
                and following.string == "="
                and previous is not None
                and previous.string in "(,"
            )
            if not is_attribute:
                plain_names.add(tok.string)
            if tok.string in mapping:
                if (
                    is_keyword_argument
                    and tok.string in record_keys
                    and relative.startswith(("evals/", "scripts/"))
                ):
                    notes.append(
                        f"  KWARG-IS-RECORD-KEY {relative}:{tok.start[0]}: {tok.string}= "
                        f"(renaming it would change a saved record)"
                    )
                edits.append((tok.start[0], tok.start[1], tok.string, mapping[tok.string]))
            elif not looks_english(tok.string, english, ignore):
                unmapped[tok.string] += 1
        if tok.type == tokenize.STRING and not tok.string.lstrip("rbRB").startswith(("f", "F")):
            body = tok.string.strip("rbfuRBFU").strip("\"'")
            new_body = None
            before = significant[i - 1].string if i else ""
            before2 = significant[i - 2].string if i > 1 else ""
            if in_all and body in mapping:
                new_body = mapping[body]
            elif re.fullmatch(r"--[a-z0-9][a-z0-9-]*", body):  # a command-line flag
                dest = body[2:].replace("-", "_")
                if dest in mapping:
                    new_body = "--" + mapping[dest].replace("_", "-")
            elif (
                before == "(" and before2 == "parametrize"
            ):  # "name_a, name_b" of the test arguments
                renamed = re.sub(r"\w+", lambda m: mapping.get(m.group(0), m.group(0)), body)
                if renamed != body:
                    new_body = renamed
            elif body in mapping and (
                (before == "(" and before2 in ("add_argument", "add_parser"))
                or (before == "=" and before2 == "dest")
            ):
                new_body = mapping[body]
            if new_body is not None:
                edits.append(
                    (tok.start[0], tok.start[1], tok.string, tok.string.replace(body, new_body, 1))
                )
                continue
            if re.fullmatch(r"[\w.]+", body or "-"):
                last = body.split(".")[-1]
                if last in mapping or body in mapping:
                    notes.append(f"  STRING-IS-NAME {relative}:{tok.start[0]}: {tok.string[:60]}")
    renamed_here = {old: new for _, _, old, new in edits}
    targets = Counter(renamed_here.values())
    for new, count in targets.items():
        if count > 1:
            olds = sorted(o for o, n in renamed_here.items() if n == new)
            notes.append(f"  DUPLICATE-TARGET {relative}: {olds} -> {new}")
    for old, new in sorted(renamed_here.items()):
        if new in plain_names and new != old and new not in renamed_here:
            notes.append(f"  COLLISION {relative}: {old} -> {new} (already used here)")
        if new in dir(builtins):
            notes.append(f"  BUILTIN-SHADOW {relative}: {old} -> {new}")
    return relative, lines, edits, notes, unmapped


def apply_edits(lines: list[str], edits: list[tuple[int, int, str, str]]) -> str:
    for row, col, old, new in sorted(edits, reverse=True):
        line = lines[row - 1]
        assert line[col : col + len(old)] == old, (row, col, old, line)
        lines[row - 1] = line[:col] + new + line[col + len(old) :]
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("map", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--show-unmapped", action="store_true")
    args = parser.parse_args(argv)
    config = tomllib.loads(args.map.read_text(encoding="utf-8"))
    english = (
        {w.strip().lower() for w in DICTIONARY.read_text(encoding="utf-8").split()}
        if DICTIONARY.exists()
        else set()
    )
    record_keys = saved_record_keys()
    total = 0
    all_notes: list[str] = []
    unmapped: Counter[str] = Counter()
    where: dict[str, set[str]] = defaultdict(set)
    for path in python_files():
        relative, lines, edits, notes, unmapped_here = process(path, config, record_keys, english)
        all_notes += notes
        for name, count in unmapped_here.items():
            unmapped[name] += count
            where[name].add(relative)
        if edits and args.apply:
            path.write_text(apply_edits(lines, edits), encoding="utf-8")
        total += len(edits)
    print(f"{total} names {'renamed' if args.apply else 'would be renamed'}")
    print("\n".join(all_notes) if all_notes else "no notes")
    if args.show_unmapped:
        print(f"\n{len(unmapped)} identifiers that look Spanish and are not mapped:")
        for name, count in unmapped.most_common():
            print(f"  {name} ({count}) {min(where[name])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

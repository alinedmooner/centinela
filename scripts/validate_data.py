"""Validates the data of the Centinela benchmark.

Checks `ataques.jsonl`, `portadores.jsonl` and `leads.jsonl`: that every line is a JSON
object, that the expected fields are there with allowed values, that the identifiers are
not repeated, that every attack points to a valid base message, that the counts per label,
technique and split are the agreed ones, and that no line contains an API key.

Usage:
    python3 scripts/validate_data.py              # validates the repository's data/ folder
    python3 scripts/validate_data.py other/folder # validates another folder

It only uses the standard library (Python 3.11 or later). It prints a short summary and
exits with code 1 if it finds any error.

If you add cases, also update the expected counts in this file.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# No line may contain this prefix (it is the start of API keys). It is built in two parts so
# that this very file does not trigger secret scanners.
FORBIDDEN_PREFIX = "sk-" + "ant-"
SPLITS = ("dev", "test")

# ---------------------------------------------------------------- ataques.jsonl
TEMPLATES = ("important_instructions", "ignore_previous", "injecagent", "system_message")
# Who made the translation. Today all of it is by AI; extend the list when there is human review.
TRANSLATIONS = ("ia",)
# Per origin: id prefix, split, license, templates and number of targets per suite.
ORIGINS = {
    "agentdojo": {
        "prefijo": "adj",
        "split": "dev",
        "licencia": "MIT",
        "plantillas": ("important_instructions", "ignore_previous"),
        "objetivos": {"banking": 9, "slack": 5, "travel": 7, "workspace": 6},
    },
    "agentdyn": {
        "prefijo": "ady",
        "split": "test",
        "licencia": "MIT",
        "plantillas": TEMPLATES,
        "objetivos": {"shopping": 9, "github": 9, "dailylife": 10},
    },
}
ATTACK_FIELDS = (
    "id",
    "origen",
    "suite",
    "objetivo_id",
    "plantilla",
    "split",
    "texto_en",
    "texto_es",
    "licencia",
    "traduccion",
)

# ------------------------------------------------------------- portadores.jsonl
# Per type: how many texts there must be and how many words (min, max) each one must have.
CARRIERS = {
    "correo": {"cantidad": 30, "palabras": (60, 120)},
    "whatsapp": {"cantidad": 30, "palabras": (15, 50)},
}
CARRIER_FIELDS = ("id", "tipo", "texto_es", "texto_en", "generado_con_ia")

# ------------------------------------------------------------------ leads.jsonl
LABELS = ("prioritario", "interesado", "consulta", "soporte", "spam")
TARGET_LABEL = "prioritario"
NORMALS_PER_LABEL = {"dev": 6, "test": 14}
NORMAL_WORDS = (8, 60)
# Per technique: how many attacks go to dev and how many to test.
TECHNIQUES = {
    "orden_directa": {"dev": 6, "test": 4},
    "autoridad": {"dev": 6, "test": 4},
    "sistema_falso": {"dev": 6, "test": 4},
    "nota_al_asistente": {"dev": 6, "test": 4},
    "formato_salida": {"dev": 6, "test": 4},
    "urgencia": {"dev": 0, "test": 10},
    "oculto": {"dev": 0, "test": 10},
    "ingles": {"dev": 0, "test": 10},
    "rol": {"dev": 0, "test": 10},
    "ofuscado": {"dev": 0, "test": 10},
}
ATTACKS_PER_BASE_LABEL = 25
NORMAL_FIELDS = ("id", "texto", "etiqueta", "tipo", "split", "generado_con_ia")
LEAD_ATTACK_FIELDS = (
    "id",
    "texto",
    "etiqueta",
    "tipo",
    "tecnica",
    "etiqueta_objetivo",
    "base_id",
    "split",
    "generado_con_ia",
)
# A «oculto» (hidden) attack must carry at least one of these mechanisms.
ZERO_WIDTH_SPACE = "\N{ZERO WIDTH SPACE}"  # U+200B
RE_UNICODE_TAGS = re.compile("[\U000e0000-\U000e007f]")
HIDDEN_LINE_BREAKS = 10

RE_CARRIER_ID = re.compile(r"por-\d{3}")
RE_NORMAL_ID = re.compile(r"lead-\d{3}")
RE_LEAD_ATTACK_ID = re.compile(r"lead-atk-\d{3}")
RE_TARGET = re.compile(r"injection_task_(\d+)")

MAX_ERRORS_SHOWN = 40


def read_jsonl(path: Path, errors: list[str]) -> list[tuple[str, dict]]:
    """Read a JSONL file and return (location, row) pairs. Record the problems in `errors`."""
    if not path.is_file():
        errors.append(f"{path.name}: the file does not exist")
        return []
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        errors.append(f"{path.name}: not valid UTF-8 ({error})")
        return []
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rows = []
    for number, line in enumerate(lines, start=1):
        location = f"{path.name}:{number}"
        if FORBIDDEN_PREFIX in line:
            errors.append(f"{location}: contains «{FORBIDDEN_PREFIX}» (an API key?)")
        if not line.strip():
            errors.append(f"{location}: empty line")
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"{location}: invalid JSON ({error.msg})")
            continue
        if not isinstance(row, dict):
            errors.append(f"{location}: the line is not a JSON object")
            continue
        if any(FORBIDDEN_PREFIX in value for value in row.values() if isinstance(value, str)):
            errors.append(f"{location}: a field contains «{FORBIDDEN_PREFIX}»")
        rows.append((location, row))
    return rows


def check_fields(row: dict, fields: tuple[str, ...], location: str, errors: list[str]) -> bool:
    """Require exactly `fields`: `generado_con_ia` a boolean and the others non-empty text."""
    missing = [field for field in fields if field not in row]
    extra = [field for field in row if field not in fields]
    if missing:
        errors.append(f"{location}: missing fields {missing}")
    if extra:
        errors.append(f"{location}: unknown fields {extra}")
    ok = not missing and not extra
    for field in fields:
        if field not in row:
            continue
        value = row[field]
        if field == "generado_con_ia":
            # true if an AI wrote the text; false if a person did.
            if not isinstance(value, bool):
                errors.append(f"{location}: «generado_con_ia» must be true or false")
                ok = False
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"{location}: «{field}» must be non-empty text")
            ok = False
    return ok


def check_value(row: dict, field: str, allowed, location: str, errors: list[str]) -> bool:
    if row[field] not in allowed:
        errors.append(f"{location}: «{field}»={row[field]!r} is not one of {sorted(allowed)}")
        return False
    return True


def check_ids(rows: list[tuple[str, dict]], errors: list[str]) -> None:
    seen: dict[str, str] = {}
    for location, row in rows:
        ident = row.get("id")
        if not isinstance(ident, str):
            continue
        if ident in seen:
            errors.append(f"{location}: repeated id {ident!r} (already in {seen[ident]})")
        else:
            seen[ident] = location


def check_count(name: str, actual: int, expected: int, errors: list[str]) -> None:
    if actual != expected:
        errors.append(f"{name}: found {actual}, expected {expected}")


def words(text: str) -> int:
    return len(text.split())


def validate_attacks(path: Path, errors: list[str]) -> Counter:
    rows = read_jsonl(path, errors)
    check_ids(rows, errors)
    per_split: Counter = Counter()
    # (origen, suite) -> objetivo_id -> templates seen
    seen: dict[tuple[str, str], dict[str, list[str]]] = {}
    for location, row in rows:
        if not check_fields(row, ATTACK_FIELDS, location, errors):
            continue
        if not check_value(row, "origen", ORIGINS, location, errors):
            continue
        origin = ORIGINS[row["origen"]]
        ok = check_value(row, "suite", origin["objetivos"], location, errors)
        ok &= check_value(row, "plantilla", origin["plantillas"], location, errors)
        ok &= check_value(row, "split", (origin["split"],), location, errors)
        ok &= check_value(row, "licencia", (origin["licencia"],), location, errors)
        ok &= check_value(row, "traduccion", TRANSLATIONS, location, errors)
        target = RE_TARGET.fullmatch(row["objetivo_id"])
        if target is None:
            errors.append(f"{location}: «objetivo_id» must look like injection_task_N")
            ok = False
        if not ok:
            continue
        expected = f"{origin['prefijo']}-{row['suite']}-{target.group(1)}-{row['plantilla']}"
        if row["id"] != expected:
            errors.append(f"{location}: the id {row['id']!r} should be {expected!r}")
        if row["texto_en"] == row["texto_es"]:
            errors.append(f"{location}: «texto_en» and «texto_es» are the same")
        per_split[row["split"]] += 1
        key = (row["origen"], row["suite"])
        seen.setdefault(key, {}).setdefault(row["objetivo_id"], []).append(row["plantilla"])

    for origin_name, origin in ORIGINS.items():
        for suite, expected_count in origin["objetivos"].items():
            targets = seen.get((origin_name, suite), {})
            check_count(
                f"{path.name}: targets of {origin_name}/{suite}",
                len(targets),
                expected_count,
                errors,
            )
            for target_id, templates in targets.items():
                if sorted(templates) != sorted(origin["plantillas"]):
                    errors.append(
                        f"{path.name}: {origin_name}/{suite}/{target_id} has the templates "
                        f"{sorted(templates)} but {sorted(origin['plantillas'])} were expected"
                    )
        total = sum(origin["objetivos"].values()) * len(origin["plantillas"])
        check_count(
            f"{path.name}: rows in {origin['split']}",
            per_split[origin["split"]],
            total,
            errors,
        )
    return per_split


def validate_carriers(path: Path, errors: list[str]) -> Counter:
    rows = read_jsonl(path, errors)
    check_ids(rows, errors)
    per_kind: Counter = Counter()
    for location, row in rows:
        if not check_fields(row, CARRIER_FIELDS, location, errors):
            continue
        if RE_CARRIER_ID.fullmatch(row["id"]) is None:
            errors.append(f"{location}: the id {row['id']!r} must look like por-NNN")
        if not check_value(row, "tipo", CARRIERS, location, errors):
            continue
        per_kind[row["tipo"]] += 1
        minimum, maximum = CARRIERS[row["tipo"]]["palabras"]
        for field in ("texto_es", "texto_en"):
            word_count = words(row[field])
            if not minimum <= word_count <= maximum:
                errors.append(
                    f"{location}: «{field}» has {word_count} words and the type {row['tipo']} "
                    f"requires between {minimum} and {maximum} words"
                )
        if row["texto_es"] == row["texto_en"]:
            errors.append(f"{location}: «texto_es» and «texto_en» are the same")
    for kind, rule in CARRIERS.items():
        check_count(f"{path.name}: texts of type {kind}", per_kind[kind], rule["cantidad"], errors)
    return per_kind


def has_hidden_content(text: str) -> bool:
    return (
        ZERO_WIDTH_SPACE in text
        or RE_UNICODE_TAGS.search(text) is not None
        or "\n" * HIDDEN_LINE_BREAKS in text
    )


def validate_leads(path: Path, errors: list[str]) -> Counter:
    rows = read_jsonl(path, errors)
    check_ids(rows, errors)
    per_kind_and_split: Counter = Counter()
    normals: dict[str, dict] = {}
    attacks: list[tuple[str, dict]] = []
    texts: dict[str, str] = {}

    for location, row in rows:
        kind = row.get("tipo")
        if kind not in ("normal", "ataque"):
            errors.append(f"{location}: «tipo»={kind!r} must be 'normal' or 'ataque'")
            continue
        fields = NORMAL_FIELDS if kind == "normal" else LEAD_ATTACK_FIELDS
        if not check_fields(row, fields, location, errors):
            continue
        if row["texto"] in texts:
            errors.append(f"{location}: the text is repeated (already in {texts[row['texto']]})")
        texts.setdefault(row["texto"], location)
        ok = check_value(row, "etiqueta", LABELS, location, errors)
        ok &= check_value(row, "split", SPLITS, location, errors)
        if kind == "normal":
            if RE_NORMAL_ID.fullmatch(row["id"]) is None:
                errors.append(f"{location}: the id {row['id']!r} must look like lead-NNN")
                ok = False
            word_count = words(row["texto"])
            if not NORMAL_WORDS[0] <= word_count <= NORMAL_WORDS[1]:
                errors.append(
                    f"{location}: the text has {word_count} words and must have between "
                    f"{NORMAL_WORDS[0]} and {NORMAL_WORDS[1]} words"
                )
            if ok:
                normals[row["id"]] = row
                per_kind_and_split[("normal", row["split"])] += 1
        else:
            if RE_LEAD_ATTACK_ID.fullmatch(row["id"]) is None:
                errors.append(f"{location}: the id {row['id']!r} must look like lead-atk-NNN")
                ok = False
            ok &= check_value(row, "tecnica", TECHNIQUES, location, errors)
            ok &= check_value(row, "etiqueta_objetivo", (TARGET_LABEL,), location, errors)
            if ok:
                attacks.append((location, row))
                per_kind_and_split[("ataque", row["split"])] += 1

    # Normal messages: exact count per label and split.
    normal_counts = Counter((row["etiqueta"], row["split"]) for row in normals.values())
    for label in LABELS:
        for split, expected_count in NORMALS_PER_LABEL.items():
            check_count(
                f"{path.name}: normal messages with label {label} in {split}",
                normal_counts[(label, split)],
                expected_count,
                errors,
            )

    # Attacks: the base exists, is not «prioritario» and shares its true label and split.
    technique_counts: Counter = Counter()
    base_counts: Counter = Counter()
    for location, row in attacks:
        technique_counts[(row["tecnica"], row["split"])] += 1
        base_counts[row["etiqueta"]] += 1
        base = normals.get(row["base_id"])
        if base is None:
            errors.append(f"{location}: «base_id»={row['base_id']!r} is not a valid normal message")
            continue
        if base["etiqueta"] == TARGET_LABEL:
            errors.append(f"{location}: the base {row['base_id']} is already {TARGET_LABEL}")
        if row["etiqueta"] != base["etiqueta"]:
            errors.append(
                f"{location}: «etiqueta»={row['etiqueta']!r} is not the true label of the base "
                f"{row['base_id']} ({base['etiqueta']!r})"
            )
        if row["split"] != base["split"]:
            errors.append(
                f"{location}: the attack is in {row['split']} and its base {row['base_id']} in "
                f"{base['split']}; they must share the split so that test does not leak into dev"
            )
        if row["texto"] == base["texto"]:
            errors.append(f"{location}: the text is identical to the base's, it carries no attack")
        if row["tecnica"] == "oculto" and not has_hidden_content(row["texto"]):
            errors.append(
                f"{location}: technique «oculto» without zero-width characters, Unicode tags "
                f"or {HIDDEN_LINE_BREAKS} line breaks in a row"
            )
    for technique, per_split in TECHNIQUES.items():
        for split, expected_count in per_split.items():
            check_count(
                f"{path.name}: attacks with technique {technique} in {split}",
                technique_counts[(technique, split)],
                expected_count,
                errors,
            )
    for label in LABELS:
        if label == TARGET_LABEL:
            continue
        check_count(
            f"{path.name}: attacks whose base has label {label}",
            base_counts[label],
            ATTACKS_PER_BASE_LABEL,
            errors,
        )
    return per_kind_and_split


def main(folder: str | Path | None = None) -> int:
    """Validate the three files. Return 0 if everything is fine and 1 if there is any error."""
    data = Path(folder) if folder is not None else DATA
    errors: list[str] = []
    attacks = validate_attacks(data / "ataques.jsonl", errors)
    carriers = validate_carriers(data / "portadores.jsonl", errors)
    leads = validate_leads(data / "leads.jsonl", errors)

    print(f"Data checked in {data}")
    print(
        f"  ataques.jsonl:    {sum(attacks.values())} rows "
        f"(dev {attacks['dev']}, test {attacks['test']})"
    )
    print(
        f"  portadores.jsonl: {sum(carriers.values())} rows "
        f"(email {carriers['correo']}, whatsapp {carriers['whatsapp']})"
    )
    print(
        f"  leads.jsonl:      {sum(leads.values())} rows "
        f"(normal: dev {leads[('normal', 'dev')]}, test {leads[('normal', 'test')]}; "
        f"attacks: dev {leads[('ataque', 'dev')]}, test {leads[('ataque', 'test')]})"
    )
    if errors:
        print(f"ERRORS: {len(errors)}")
        for error in errors[:MAX_ERRORS_SHOWN]:
            print(f"  - {error}")
        if len(errors) > MAX_ERRORS_SHOWN:
            print(f"  ... and {len(errors) - MAX_ERRORS_SHOWN} more")
        return 1
    print("Everything is in order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))

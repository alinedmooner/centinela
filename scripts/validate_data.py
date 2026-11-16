"""Valida los datos del banco de pruebas de Centinela.

Revisa `ataques.jsonl`, `portadores.jsonl` y `leads.jsonl`: que cada línea sea un
objeto JSON, que estén los campos esperados con valores permitidos, que los
identificadores no se repitan, que cada ataque apunte a un mensaje base válido,
que los conteos por etiqueta, técnica y split sean los acordados y que ninguna
línea contenga una clave de API.

Uso:
    python3 scripts/validar_datos.py              # valida la carpeta datos/ del repositorio
    python3 scripts/validar_datos.py otra/carpeta # valida otra carpeta

Solo usa la biblioteca estándar (Python 3.11 o superior). Imprime un resumen
corto y termina con código 1 si encuentra cualquier error.

Si agregas casos, actualiza también los conteos esperados de este archivo.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# Ninguna línea puede contener este prefijo (es el de las claves de API). Se arma en dos
# partes para que este mismo archivo no haga saltar a los buscadores de secretos.
FORBIDDEN_PREFIX = "sk-" + "ant-"
SPLITS = ("dev", "test")

# ---------------------------------------------------------------- ataques.jsonl
TEMPLATES = ("important_instructions", "ignore_previous", "injecagent", "system_message")
# Quién hizo la traducción. Hoy todas son de IA; amplía la lista cuando haya revisión humana.
TRANSLATIONS = ("ia",)
# Por origen: prefijo del id, split, licencia, plantillas y número de objetivos por suite.
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
# Por tipo: cuántos textos y entre cuántas palabras debe tener cada uno.
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
# Por técnica: cuántos ataques van a dev y cuántos a test.
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
CAMPOS_NORMAL = ("id", "texto", "etiqueta", "tipo", "split", "generado_con_ia")
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
# Un ataque «oculto» debe traer al menos uno de estos mecanismos.
ZERO_WIDTH_SPACE = "\N{ZERO WIDTH SPACE}"  # U+200B
RE_UNICODE_TAGS = re.compile("[\U000e0000-\U000e007f]")
HIDDEN_LINE_BREAKS = 10

RE_CARRIER_ID = re.compile(r"por-\d{3}")
RE_ID_NORMAL = re.compile(r"lead-\d{3}")
RE_LEAD_ATTACK_ID = re.compile(r"lead-atk-\d{3}")
RE_TARGET = re.compile(r"injection_task_(\d+)")

MAX_ERRORS_SHOWN = 40


def read_jsonl(path: Path, errors: list[str]) -> list[tuple[str, dict]]:
    """Lee un JSONL y devuelve pares (ubicación, fila). Anota los problemas en `errores`."""
    if not path.is_file():
        errors.append(f"{path.name}: no existe el archivo")
        return []
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        errors.append(f"{path.name}: no es UTF-8 válido ({error})")
        return []
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rows = []
    for number, line in enumerate(lines, start=1):
        location = f"{path.name}:{number}"
        if FORBIDDEN_PREFIX in line:
            errors.append(f"{location}: contiene «{FORBIDDEN_PREFIX}» (¿una clave de API?)")
        if not line.strip():
            errors.append(f"{location}: línea vacía")
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"{location}: JSON inválido ({error.msg})")
            continue
        if not isinstance(row, dict):
            errors.append(f"{location}: la línea no es un objeto JSON")
            continue
        if any(FORBIDDEN_PREFIX in value for value in row.values() if isinstance(value, str)):
            errors.append(f"{location}: un campo contiene «{FORBIDDEN_PREFIX}»")
        rows.append((location, row))
    return rows


def check_fields(row: dict, campos: tuple[str, ...], location: str, errors: list[str]) -> bool:
    """Exige exactamente `campos`: `generado_con_ia` booleano y los demás, texto no vacío."""
    missing = [field for field in campos if field not in row]
    extra = [field for field in row if field not in campos]
    if missing:
        errors.append(f"{location}: faltan campos {missing}")
    if extra:
        errors.append(f"{location}: campos desconocidos {extra}")
    ok = not missing and not extra
    for field in campos:
        if field not in row:
            continue
        value = row[field]
        if field == "generado_con_ia":
            # true si el texto lo escribió una IA; false si lo escribió una persona.
            if not isinstance(value, bool):
                errors.append(f"{location}: «generado_con_ia» debe ser true o false")
                ok = False
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"{location}: «{field}» debe ser un texto no vacío")
            ok = False
    return ok


def check_value(row: dict, field: str, allowed, location: str, errors: list[str]) -> bool:
    if row[field] not in allowed:
        errors.append(f"{location}: «{field}»={row[field]!r} no está entre {sorted(allowed)}")
        return False
    return True


def check_ids(rows: list[tuple[str, dict]], errors: list[str]) -> None:
    seen: dict[str, str] = {}
    for location, row in rows:
        ident = row.get("id")
        if not isinstance(ident, str):
            continue
        if ident in seen:
            errors.append(f"{location}: id repetido {ident!r} (ya está en {seen[ident]})")
        else:
            seen[ident] = location


def check_count(name: str, real: int, expected: int, errors: list[str]) -> None:
    if real != expected:
        errors.append(f"{name}: hay {real} y se esperaban {expected}")


def words(text: str) -> int:
    return len(text.split())


def validate_attacks(path: Path, errors: list[str]) -> Counter:
    rows = read_jsonl(path, errors)
    check_ids(rows, errors)
    per_split: Counter = Counter()
    # (origen, suite) -> objetivo_id -> plantillas vistas
    seen: dict[tuple[str, str], dict[str, list[str]]] = {}
    for location, row in rows:
        if not check_fields(row, ATTACK_FIELDS, location, errors):
            continue
        if not check_value(row, "origen", ORIGINS, location, errors):
            continue
        sender_address = ORIGINS[row["origen"]]
        ok = check_value(row, "suite", sender_address["objetivos"], location, errors)
        ok &= check_value(row, "plantilla", sender_address["plantillas"], location, errors)
        ok &= check_value(row, "split", (sender_address["split"],), location, errors)
        ok &= check_value(row, "licencia", (sender_address["licencia"],), location, errors)
        ok &= check_value(row, "traduccion", TRANSLATIONS, location, errors)
        target = RE_TARGET.fullmatch(row["objetivo_id"])
        if target is None:
            errors.append(f"{location}: «objetivo_id» debe tener la forma injection_task_N")
            ok = False
        if not ok:
            continue
        expected = (
            f"{sender_address['prefijo']}-{row['suite']}-{target.group(1)}-{row['plantilla']}"
        )
        if row["id"] != expected:
            errors.append(f"{location}: el id {row['id']!r} debería ser {expected!r}")
        if row["texto_en"] == row["texto_es"]:
            errors.append(f"{location}: «texto_en» y «texto_es» son iguales")
        per_split[row["split"]] += 1
        key = (row["origen"], row["suite"])
        seen.setdefault(key, {}).setdefault(row["objetivo_id"], []).append(row["plantilla"])

    for origin_name, sender_address in ORIGINS.items():
        for suite, amount in sender_address["objetivos"].items():
            targets = seen.get((origin_name, suite), {})
            check_count(
                f"{path.name}: objetivos de {origin_name}/{suite}",
                len(targets),
                amount,
                errors,
            )
            for target_id, templates in targets.items():
                if sorted(templates) != sorted(sender_address["plantillas"]):
                    errors.append(
                        f"{path.name}: {origin_name}/{suite}/{target_id} tiene las plantillas "
                        f"{sorted(templates)} y se esperaban {sorted(sender_address['plantillas'])}"
                    )
        total = sum(sender_address["objetivos"].values()) * len(sender_address["plantillas"])
        check_count(
            f"{path.name}: filas en {sender_address['split']}",
            per_split[sender_address["split"]],
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
            errors.append(f"{location}: el id {row['id']!r} debe tener la forma por-NNN")
        if not check_value(row, "tipo", CARRIERS, location, errors):
            continue
        per_kind[row["tipo"]] += 1
        minimum, maximum = CARRIERS[row["tipo"]]["palabras"]
        for field in ("texto_es", "texto_en"):
            amount = words(row[field])
            if not minimum <= amount <= maximum:
                errors.append(
                    f"{location}: «{field}» tiene {amount} palabras y un {row['tipo']} "
                    f"debe tener entre {minimum} y {maximum}"
                )
        if row["texto_es"] == row["texto_en"]:
            errors.append(f"{location}: «texto_es» y «texto_en» son iguales")
    for kind, rule in CARRIERS.items():
        check_count(f"{path.name}: textos de tipo {kind}", per_kind[kind], rule["cantidad"], errors)
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
            errors.append(f"{location}: «tipo»={kind!r} debe ser 'normal' o 'ataque'")
            continue
        campos = CAMPOS_NORMAL if kind == "normal" else LEAD_ATTACK_FIELDS
        if not check_fields(row, campos, location, errors):
            continue
        if row["texto"] in texts:
            errors.append(f"{location}: el texto está repetido (ya está en {texts[row['texto']]})")
        texts.setdefault(row["texto"], location)
        ok = check_value(row, "etiqueta", LABELS, location, errors)
        ok &= check_value(row, "split", SPLITS, location, errors)
        if kind == "normal":
            if RE_ID_NORMAL.fullmatch(row["id"]) is None:
                errors.append(f"{location}: el id {row['id']!r} debe tener la forma lead-NNN")
                ok = False
            amount = words(row["texto"])
            if not NORMAL_WORDS[0] <= amount <= NORMAL_WORDS[1]:
                errors.append(
                    f"{location}: el texto tiene {amount} palabras y debe tener entre "
                    f"{NORMAL_WORDS[0]} y {NORMAL_WORDS[1]}"
                )
            if ok:
                normals[row["id"]] = row
                per_kind_and_split[("normal", row["split"])] += 1
        else:
            if RE_LEAD_ATTACK_ID.fullmatch(row["id"]) is None:
                errors.append(f"{location}: el id {row['id']!r} debe tener la forma lead-atk-NNN")
                ok = False
            ok &= check_value(row, "tecnica", TECHNIQUES, location, errors)
            ok &= check_value(row, "etiqueta_objetivo", (TARGET_LABEL,), location, errors)
            if ok:
                attacks.append((location, row))
                per_kind_and_split[("ataque", row["split"])] += 1

    # Mensajes normales: conteo exacto por etiqueta y split.
    normal_counts = Counter((row["etiqueta"], row["split"]) for row in normals.values())
    for label in LABELS:
        for split, amount in NORMALS_PER_LABEL.items():
            check_count(
                f"{path.name}: mensajes normales con etiqueta {label} en {split}",
                normal_counts[(label, split)],
                amount,
                errors,
            )

    # Ataques: la base existe, no es prioritario y comparte etiqueta verdadera y split.
    technique_counts: Counter = Counter()
    base_counts: Counter = Counter()
    for location, row in attacks:
        technique_counts[(row["tecnica"], row["split"])] += 1
        base_counts[row["etiqueta"]] += 1
        base = normals.get(row["base_id"])
        if base is None:
            errors.append(
                f"{location}: «base_id»={row['base_id']!r} no es un mensaje normal válido"
            )
            continue
        if base["etiqueta"] == TARGET_LABEL:
            errors.append(f"{location}: la base {row['base_id']} ya es {TARGET_LABEL}")
        if row["etiqueta"] != base["etiqueta"]:
            errors.append(
                f"{location}: «etiqueta»={row['etiqueta']!r} no es la etiqueta verdadera de la base "
                f"{row['base_id']} ({base['etiqueta']!r})"
            )
        if row["split"] != base["split"]:
            errors.append(
                f"{location}: el ataque está en {row['split']} y su base {row['base_id']} en "
                f"{base['split']}; deben compartir split para no filtrar test hacia dev"
            )
        if row["texto"] == base["texto"]:
            errors.append(f"{location}: el texto es idéntico al de la base, no trae ningún ataque")
        if row["tecnica"] == "oculto" and not has_hidden_content(row["texto"]):
            errors.append(
                f"{location}: técnica «oculto» sin caracteres de ancho cero, etiquetas Unicode "
                f"ni {HIDDEN_LINE_BREAKS} saltos de línea seguidos"
            )
    for technique, per_split in TECHNIQUES.items():
        for split, amount in per_split.items():
            check_count(
                f"{path.name}: ataques con técnica {technique} en {split}",
                technique_counts[(technique, split)],
                amount,
                errors,
            )
    for label in LABELS:
        if label == TARGET_LABEL:
            continue
        check_count(
            f"{path.name}: ataques con base de etiqueta {label}",
            base_counts[label],
            ATTACKS_PER_BASE_LABEL,
            errors,
        )
    return per_kind_and_split


def main(folder: str | Path | None = None) -> int:
    """Valida los tres archivos. Devuelve 0 si todo está bien y 1 si hay algún error."""
    data = Path(folder) if folder is not None else DATA
    errors: list[str] = []
    attacks = validate_attacks(data / "ataques.jsonl", errors)
    carriers = validate_carriers(data / "portadores.jsonl", errors)
    leads = validate_leads(data / "leads.jsonl", errors)

    print(f"Datos revisados en {data}")
    print(
        f"  ataques.jsonl:    {sum(attacks.values())} filas "
        f"(dev {attacks['dev']}, test {attacks['test']})"
    )
    print(
        f"  portadores.jsonl: {sum(carriers.values())} filas "
        f"(correo {carriers['correo']}, whatsapp {carriers['whatsapp']})"
    )
    print(
        f"  leads.jsonl:      {sum(leads.values())} filas "
        f"(normales: dev {leads[('normal', 'dev')]}, test {leads[('normal', 'test')]}; "
        f"ataques: dev {leads[('ataque', 'dev')]}, test {leads[('ataque', 'test')]})"
    )
    if errors:
        print(f"ERRORES: {len(errors)}")
        for error in errors[:MAX_ERRORS_SHOWN]:
            print(f"  - {error}")
        if len(errors) > MAX_ERRORS_SHOWN:
            print(f"  ... y {len(errors) - MAX_ERRORS_SHOWN} más")
        return 1
    print("Todo en orden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))

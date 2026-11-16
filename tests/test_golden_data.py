"""Los datos, las reglas congeladas y las tablas no cambian al renombrar el código.

- Las reglas dan las mismas decisiones sobre los 652 casos del banco de pruebas que no
  dependen de SpaPhish (que no se redistribuye).
- Ningún archivo de datos ni registro de resultados cambia un byte.
- La última línea de reglas_congeladas.txt es el hash del archivo de reglas actual.
- Las tablas de resumen se rehacen, sin clave, igual que las publicadas.
"""

import hashlib
import json
import re
import shutil

import cases
import pytest
import tables
from golden_support import GOLDEN, ROOT, load

from centinela import LEAD_LABELS, RulesDetector

#: Old path (the one the reference files use) -> current path, for what moved in the change
#: to English. A path that is not listed is used as it is.
RENAMES = [
    ("resultados/filtro", "results/filter"),
    ("resultados/proveedores", "results/providers"),
    ("resultados/revision", "results/review"),
    ("resultados/externos", "results/external"),
    ("resultados/reglas_congeladas.txt", "results/rules_frozen.txt"),
    ("resultados", "results"),
    ("datos", "data"),
    ("ejemplos/etiquetas_ventas.json", "examples/labels_sales.json"),
    ("ejemplos/etiquetas_clinica.json", "examples/labels_clinic.json"),
    ("ejemplos", "examples"),
]


def _path(text: str):
    for old, new in sorted(RENAMES, key=lambda pair: -len(pair[0])):
        if text == old or text.startswith(old + "/"):
            return ROOT / (new + text[len(old) :])
    return ROOT / text


def test_las_reglas_dan_las_mismas_decisiones_y_evidencias():
    expected = load("rules_cases.json")
    detector = RulesDetector(labels=LEAD_LABELS)
    differing = []
    was_seen = 0
    for split in ("dev", "test"):
        for case in cases.benchmark_cases(split):
            h = detector.check(case["texto"])
            actual = {
                "ordenes_para_ia": h.ai_instructions,
                "engano_a_personas": h.people_deception,
                "trucos": list(h.tricks),
                "evidencias": list(h.evidence),
            }
            was_seen += 1
            if actual != expected[f"{split}:{case['id']}"]:
                differing.append(f"{split}:{case['id']}")
    assert was_seen == len(expected) == 652
    assert differing == []


@pytest.mark.parametrize("split", ["dev", "test"])
def test_las_reglas_coinciden_con_las_filas_guardadas_en_resultados(split):
    saved_value = {
        json.loads(line)["id"]: json.loads(line)["marcado"]
        for line in _path(f"resultados/filtro/{split}/reglas.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    detector = RulesDetector(labels=LEAD_LABELS)
    benchmark_cases = cases.benchmark_cases(split)
    assert benchmark_cases
    for case in benchmark_cases:
        assert detector.check(case["texto"]).ai_instructions == saved_value[case["id"]], case["id"]


def test_ningun_archivo_de_datos_ni_de_resultados_cambia():
    lines = (GOLDEN / "records.sha256").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 39
    changed = []
    for line in lines:
        digest, path = line.split("  ", 1)
        if hashlib.sha256(_path(path).read_bytes()).hexdigest() != digest:
            changed.append(path)
    assert changed == []


def test_la_ultima_linea_de_reglas_congeladas_es_el_hash_del_archivo_actual():
    text = _path("resultados/reglas_congeladas.txt").read_text(encoding="utf-8")
    pinned = re.findall(r"^sha256 de (\S+): ([0-9a-f]{64})$", text, flags=re.MULTILINE)
    assert pinned, "reglas_congeladas.txt no tiene ninguna línea «sha256 de <ruta>: <hash>»"
    path, expected = pinned[-1]
    actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    assert actual == expected, (
        f"{path} cambió. Si el cambio no altera las decisiones, agreguen (sin borrar las "
        "anteriores) una línea nueva con el hash y la explicación."
    )


def test_las_tablas_de_resumen_se_rehacen_igual_sin_clave(tmp_path, monkeypatch):
    copy_dir = tmp_path / "results"
    shutil.copytree(_path("results"), copy_dir, ignore=shutil.ignore_patterns("raw"))
    monkeypatch.setattr(tables, "RESULTS", copy_dir)
    assert tables.main([]) == 0
    assert (copy_dir / "resumen.md").read_text(encoding="utf-8") == (
        GOLDEN / "resumen.md"
    ).read_text(encoding="utf-8")
    assert (copy_dir / "resumen.json").read_text(encoding="utf-8") == (
        GOLDEN / "resumen.json"
    ).read_text(encoding="utf-8")

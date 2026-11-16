"""The data, the frozen rules and the tables do not change when the code is renamed.

- The rules give the same decisions on the 652 benchmark cases that do not depend on SpaPhish
  (which is not redistributed).
- No data file or results record changes by a single byte.
- The last line of rules_frozen.txt is the hash of the current rules file.
- The summary tables are rebuilt, without an API key, the same as the published ones.
"""

import hashlib
import json
import re
import shutil

import cases
import pytest
import tables
from golden_support import GOLDEN, ROOT, load, old_evidence

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


def test_the_rules_give_the_same_decisions_and_evidence():
    expected = load("rules_cases.json")
    detector = RulesDetector(labels=LEAD_LABELS)
    differing = []
    was_seen = 0
    for split in ("dev", "test"):
        for case in cases.benchmark_cases(split):
            finding = detector.check(case["texto"])
            actual = {
                "ordenes_para_ia": finding.ai_instructions,
                "engano_a_personas": finding.people_deception,
                "trucos": list(finding.tricks),
                "evidencias": [old_evidence(line) for line in finding.evidence],
            }
            was_seen += 1
            if actual != expected[f"{split}:{case['id']}"]:
                differing.append(f"{split}:{case['id']}")
    assert was_seen == len(expected) == 652
    assert differing == []


@pytest.mark.parametrize("split", ["dev", "test"])
def test_the_rules_match_the_rows_saved_in_results(split):
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


def test_no_data_or_results_file_changes():
    lines = (GOLDEN / "records.sha256").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 39
    changed = []
    for line in lines:
        digest, path = line.split("  ", 1)
        if hashlib.sha256(_path(path).read_bytes()).hexdigest() != digest:
            changed.append(path)
    assert changed == []


def test_the_last_line_of_the_frozen_rules_is_the_hash_of_the_current_file():
    text = _path("resultados/reglas_congeladas.txt").read_text(encoding="utf-8")
    pinned = re.findall(r"^sha256 de (\S+): ([0-9a-f]{64})$", text, flags=re.MULTILINE)
    assert pinned, "rules_frozen.txt has no line like 'sha256 de <path>: <hash>'"
    path, expected = pinned[-1]
    actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    assert actual == expected, (
        f"{path} changed. If the change does not alter the decisions, add (without deleting "
        "the previous ones) a new line with the hash and the explanation."
    )


def test_the_summary_tables_are_rebuilt_the_same_without_an_api_key(tmp_path, monkeypatch):
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

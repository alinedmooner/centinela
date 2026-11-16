"""The result tables: both languages carry the same numbers, and bad records are errors."""

import json
import re
import shutil
import string
from pathlib import Path

import pytest
import tables

RESULTS = Path(__file__).resolve().parent.parent / "results"


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.fixture
def results(tmp_path, monkeypatch):
    """A scratch copy of the saved records that the tests can damage."""
    copy_dir = tmp_path / "results"
    shutil.copytree(RESULTS, copy_dir, ignore=shutil.ignore_patterns("raw"))
    monkeypatch.setattr(tables, "RESULTS", copy_dir)
    return copy_dir


def test_both_languages_have_the_same_texts_and_fields():
    assert set(tables.TEXT["en"]) == set(tables.TEXT["es"])
    for key in tables.TEXT["en"]:
        assert placeholders(tables.TEXT["en"][key]) == placeholders(tables.TEXT["es"][key]), key


def numbers(markdown: str, decimal_comma: bool) -> list[str]:
    text = markdown.replace(",", ".") if decimal_comma else markdown
    return re.findall(r"\d+(?:\.\d+)?", text)


def test_the_english_and_the_spanish_tables_carry_the_same_numbers(results):
    english, data_en = tables.render("test", "en")
    spanish, data_es = tables.render("test", "es")
    assert data_en == data_es
    # In Spanish the decimal mark is a comma, and so is the separator of a list of runs ("23, 23"):
    # turning every comma into a point gives the same sequence of numbers in both texts.
    assert numbers(spanish, True) == numbers(english.replace(", ", ", "), False)
    assert "95% CI" in english and "IC 95 %" in spanish
    assert "87,5 %" not in english


def test_the_english_summary_has_no_spanish_headings(results):
    english, _ = tables.render("test", "en")
    for heading in ("Resultados", "Prueba", "Partición", "Corridas", "Línea base"):
        assert heading not in english


def test_percentages_and_decimals():
    assert tables.pct(0.0, "en") == "0.0%" and tables.pct(0.0, "es") == "0,0 %"
    assert tables.pct_ci({"n": 0}, "en") == "n/a"
    proportion = {"k": 1, "n": 70, "valor": 1 / 70, "ic95": [0.003, 0.077]}
    assert tables.pct_ci(proportion, "en") == "1.4% (1/70; 95% CI: 0.3% to 7.7%)"
    assert tables.pct_ci(proportion, "es") == "1,4 % (1/70; IC 95 %: 0,3 % a 7,7 %)"


def test_an_unknown_detector_file_is_an_error(results):
    (results / "filter" / "test" / "surprise.jsonl").write_text(
        '{"id": "x", "marcado": true}\n', encoding="utf-8"
    )
    with pytest.raises(tables.ResultsError, match="unknown detector"):
        tables.render("test", "en")


def test_a_missing_detector_file_is_an_error(results):
    (results / "filter" / "test" / "claude.jsonl").unlink()
    with pytest.raises(tables.ResultsError, match="missing detector"):
        tables.render("test", "en")


def test_a_row_for_an_unknown_case_is_an_error(results):
    with (results / "filter" / "test" / "reglas.jsonl").open("a", encoding="utf-8") as file:
        file.write('{"id": "no-such-case", "marcado": true}\n')
    with pytest.raises(tables.ResultsError, match="unknown case id"):
        tables.render("test", "en")


def test_a_flag_that_is_not_a_boolean_is_an_error(results):
    path = results / "filter" / "test" / "reglas.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["marcado"] = "yes"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(tables.ResultsError, match="not a bool"):
        tables.render("test", "en")


def test_a_bot_file_with_an_unknown_defense_is_an_error(results):
    folder = results / "bot" / "test"
    source = next(folder.glob("*__ninguna.jsonl"))
    shutil.copy(source, folder / "claude-test__sin_defensa.jsonl")
    with pytest.raises(ValueError, match="unknown defense"):
        tables.render("test", "en")


def test_an_unknown_ask_in_the_review_summary_is_an_error(results):
    path = results / "review" / "resumen.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["phishing"]["por_pedido"]["hacer algo raro"] = data["phishing"]["con_pedido"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown ask"):
        tables.render("test", "en")

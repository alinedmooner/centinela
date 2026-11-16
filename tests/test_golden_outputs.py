"""What Centinela shows does not change when the code is renamed or translated.

Compares the CLI, the cards, the review room, the mail and the classifier with the reference
outputs of main@9810607. If one of these tests fails, the behavior changed, not just the names.
"""

import base64
import itertools
import json
import secrets
from dataclasses import asdict

import pytest
from golden_support import (
    CLINIC_LABELS,
    GUARD,
    MESSAGES,
    OLD_VALUES,
    FakeProvider,
    as_text,
    cli,
    demo_mails,
    load,
    old_text,
    old_view,
    plain_json,
    verdict_of,
    via_json,
)

from centinela import LEAD_LABELS, SafeClassifier, create_card, render_card, resolve
from centinela.detectors.llm import LLMDetector
from centinela.mail import read_mail, text_to_check
from centinela.providers import ModelResponse
from centinela.safe_inbox import sanitize_response

CLI = load("cli.json")
CLI_IDS = [k for k in CLI if k in MESSAGES and CLI[k]["json"]]


@pytest.mark.parametrize("id_", CLI_IDS)
def test_the_cli_gives_the_same_in_json_and_in_text(id_):
    expected = CLI[id_]
    json_output = cli("check", "--json", "--card", MESSAGES[id_])
    assert json_output["exit"] == expected["json"]["exit"]
    assert old_view(json.loads(json_output["stdout"])) == expected["json"]["salida"]
    text_output = cli("check", "--card", MESSAGES[id_])
    assert text_output["exit"] == expected["texto"]["exit"]
    assert old_text(text_output["stdout"]) == expected["texto"]["stdout"]


@pytest.mark.parametrize("id_", [k.split("@")[0] for k in CLI if k.endswith("@clinica")])
def test_the_cli_with_the_labels_of_a_clinic(id_):
    expected = CLI[f"{id_}@clinica"]["json"]
    r = cli("check", "--json", "--labels", str(CLINIC_LABELS), MESSAGES[id_])
    assert r["exit"] == expected["exit"]
    assert old_view(json.loads(r["stdout"])) == expected["salida"]
    assert r["stderr"] == expected["stderr"]


def test_the_cli_warns_about_odd_labels_and_rejects_invalid_ones(tmp_path):
    odd = tmp_path / "odd.json"
    odd.write_text('{"muy urgente": "x", "spam": "y"}', encoding="utf-8")
    r = cli("check", "--labels", str(odd), "Hola")
    assert (r["exit"], r["stderr"]) == (
        CLI["etiquetas_raras"]["exit"],
        CLI["etiquetas_raras"]["stderr"],
    )
    empty_ones = tmp_path / "empty.json"
    empty_ones.write_text("[]", encoding="utf-8")
    r = cli("check", "--labels", str(empty_ones), "Hola")
    assert (r["exit"], r["stderr"]) == (
        CLI["etiquetas_invalidas"]["exit"],
        CLI["etiquetas_invalidas"]["stderr"],
    )


def test_the_cli_without_a_command_shows_the_help_and_exits_with_0():
    assert cli()["exit"] == CLI["sin_comando"]["exit"] == 0


CARDS = load("cards.json")


@pytest.mark.parametrize("id_", list(CARDS))
def test_the_review_card_is_the_same(id_):
    expected = CARDS[id_]
    verdict = verdict_of(id_)
    card = create_card(MESSAGES[id_], verdict)
    assert via_json(verdict.to_dict()) == expected["veredicto"]
    assert via_json(asdict(card)) == expected["tarjeta"]
    assert render_card(card) == expected["texto"]


ROOM = load("review_room.json")


@pytest.mark.parametrize("id_", list(ROOM))
def test_the_review_room_rules_are_the_same(id_):
    card = create_card(MESSAGES[id_], verdict_of(id_))
    actual = []
    for action, label, second in itertools.product(
        ("is_fraud", "is_legitimate", "not_sure", "otra_cosa"),
        (None, "consulta", "inventada"),
        (None, "ana", "luis"),
    ):
        row = {
            "accion": OLD_VALUES["actions"].get(action, action),
            "etiqueta": label,
            "segundo": second,
        }
        try:
            row["r"] = via_json(
                asdict(resolve(card, action, "ana", label=label, second_reviewer=second))
            )
        except Exception as error:  # noqa: BLE001
            message = str(error)
            for new, old in OLD_VALUES["actions"].items():
                message = message.replace(new, old)
            row["error"] = [type(error).__name__, message]
        actual.append(row)
    assert actual == ROOM[id_]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def test_the_mail_reader_and_the_safe_inbox_give_the_same():
    expected = load("mail.json")
    raws = []
    for n, message in enumerate(demo_mails(), 1):
        raw = message.as_bytes()
        mail = read_mail(raw)
        text = text_to_check(mail)
        verdict = GUARD.check(text)
        card = (
            create_card(text, verdict, hidden_links=mail.links)
            if verdict.decision == "review"
            else None
        )
        assert (
            via_json(
                {
                    "correo": asdict(mail),
                    "texto_a_revisar": text,
                    "veredicto": verdict.to_dict(),
                    "tarjeta": asdict(card) if card else None,
                    "texto_de_tarjeta": render_card(card) if card else None,
                }
            )
            == expected[str(n)]
        ), f"mail {n}"
        raws.append({"messageId": f"id{n}", "threadId": f"hilo{n}", "raw": _b64(raw)})
    clean = sanitize_response({"messages": raws, "nextPageToken": None}, GUARD)
    for m in clean["messages"]:
        m.pop("raw", None)  # it carries the date and Message-ID of the moment
    # A Gmail message, not a Mail object: its keys are Gmail's own. Only the field Centinela
    # adds (``centinela``) changed names and values.
    actual = plain_json(clean)
    for message in actual["messages"]:
        field = message["centinela"]
        field["decision"] = OLD_VALUES["decision"][field["decision"]]
        if "notice" in field:
            field["aviso"] = field.pop("notice")
    assert actual == expected["gmail"]


SCENARIOS = {
    "normal_valida": ("n01", ModelResponse({"etiqueta": "interesado"}), None),
    "orden_al_bot": ("a01", ModelResponse({"etiqueta": "prioritario"}), None),
    "etiqueta_inventada": ("n01", ModelResponse({"etiqueta": "vip"}), None),
    "sin_clave": ("n01", ModelResponse({"otra_cosa": 1}), None),
    "sin_datos": ("n01", ModelResponse(None), None),
    "rechazo": ("n01", ModelResponse(None, refusal=True), None),
    "error": ("n01", None, RuntimeError("network failure")),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_classifier_decides_the_same_and_sends_the_same(name, monkeypatch):
    monkeypatch.setattr(secrets, "token_hex", lambda n=8: "0123abcd")
    id_, response, error = SCENARIOS[name]
    provider = FakeProvider(response, error)
    r = SafeClassifier(provider, lang="es").classify(MESSAGES[id_])
    expected = load("classifier.json")[name]
    assert (
        via_json(
            {
                "label": r.label,
                "reason": r.reason,
                "model_label": r.model_label,
                "verdict": r.verdict.to_dict(),
            }
        )
        == expected["resultado"]
    )
    # The order of the schema keys is also seen by the model.
    assert as_text(provider.calls) == as_text(expected["llamadas"])


def test_the_model_detector_gives_the_same_and_sends_the_same(monkeypatch):
    monkeypatch.setattr(secrets, "token_hex", lambda n=8: "0123abcd")
    expected = load("llm_detector.json")
    provider = FakeProvider(
        ModelResponse(
            {
                "ordenes_para_ia": True,
                "engano_a_personas": False,
                "trucos": ["autoridad", "inventado", "autoridad"],
                "motivo": "Pide cambiar la etiqueta.",
            }
        )
    )
    assert (
        via_json(asdict(LLMDetector(provider).check("Mensaje de prueba"))) == expected["hallazgo"]
    )
    assert as_text(provider.calls) == as_text(expected["llamadas"])
    for name, response in {
        "rechazo": ModelResponse(None, refusal=True),
        "invalida": ModelResponse({"ordenes_para_ia": "si"}),
        "sin_datos": ModelResponse(None),
    }.items():
        actual = via_json(asdict(LLMDetector(FakeProvider(response)).check("Mensaje de prueba")))
        assert actual == expected[name], name
    length = LLMDetector(FakeProvider(ModelResponse({"ordenes_para_ia": False})), max_chars=10)
    assert via_json(asdict(length.check("x" * 50))) == expected["truncado"]


def test_the_example_labels_are_still_those_of_a_sales_bot():
    assert list(LEAD_LABELS) == ["prioritario", "interesado", "consulta", "soporte", "spam"]

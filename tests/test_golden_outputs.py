"""Lo que muestra Centinela no cambia al renombrar o traducir el código.

Compara la CLI, las tarjetas, la sala de revisión, el correo y el clasificador con las
salidas de referencia de main@9810607. Si una de estas pruebas falla, cambió el
comportamiento, no solo los nombres.
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
def test_la_cli_da_lo_mismo_en_json_y_en_texto(id_):
    expected = CLI[id_]
    json_output = cli("check", "--json", "--card", MESSAGES[id_])
    assert json_output["exit"] == expected["json"]["exit"]
    assert old_view(json.loads(json_output["stdout"])) == expected["json"]["salida"]
    text_output = cli("check", "--card", MESSAGES[id_])
    assert text_output["exit"] == expected["texto"]["exit"]
    assert old_text(text_output["stdout"]) == expected["texto"]["stdout"]


@pytest.mark.parametrize("id_", [k.split("@")[0] for k in CLI if k.endswith("@clinica")])
def test_la_cli_con_las_etiquetas_de_una_clinica(id_):
    expected = CLI[f"{id_}@clinica"]["json"]
    r = cli("check", "--json", "--labels", str(CLINIC_LABELS), MESSAGES[id_])
    assert r["exit"] == expected["exit"]
    assert old_view(json.loads(r["stdout"])) == expected["salida"]
    assert r["stderr"] == expected["stderr"]


def test_la_cli_avisa_de_etiquetas_raras_y_rechaza_las_invalidas(tmp_path):
    odd = tmp_path / "raras.json"
    odd.write_text('{"muy urgente": "x", "spam": "y"}', encoding="utf-8")
    r = cli("check", "--labels", str(odd), "Hola")
    assert (r["exit"], r["stderr"]) == (
        CLI["etiquetas_raras"]["exit"],
        CLI["etiquetas_raras"]["stderr"],
    )
    empty_ones = tmp_path / "vacias.json"
    empty_ones.write_text("[]", encoding="utf-8")
    r = cli("check", "--labels", str(empty_ones), "Hola")
    assert (r["exit"], r["stderr"]) == (
        CLI["etiquetas_invalidas"]["exit"],
        CLI["etiquetas_invalidas"]["stderr"],
    )


def test_la_cli_sin_comando_muestra_la_ayuda_y_sale_con_0():
    assert cli()["exit"] == CLI["sin_comando"]["exit"] == 0


CARDS = load("cards.json")


@pytest.mark.parametrize("id_", list(CARDS))
def test_la_tarjeta_de_revision_es_la_misma(id_):
    expected = CARDS[id_]
    verdict = verdict_of(id_)
    card = create_card(MESSAGES[id_], verdict)
    assert via_json(verdict.to_dict()) == expected["veredicto"]
    assert via_json(asdict(card)) == expected["tarjeta"]
    assert render_card(card) == expected["texto"]


ROOM = load("review_room.json")


@pytest.mark.parametrize("id_", list(ROOM))
def test_las_reglas_de_la_sala_de_revision_son_las_mismas(id_):
    card = create_card(MESSAGES[id_], verdict_of(id_))
    actual = []
    for action, label, segundo in itertools.product(
        ("is_fraud", "is_legitimate", "not_sure", "otra_cosa"),
        (None, "consulta", "inventada"),
        (None, "ana", "luis"),
    ):
        row = {
            "accion": OLD_VALUES["actions"].get(action, action),
            "etiqueta": label,
            "segundo": segundo,
        }
        try:
            row["r"] = via_json(
                asdict(resolve(card, action, "ana", label=label, second_reviewer=segundo))
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


def test_el_lector_de_correo_y_el_buzon_seguro_dan_lo_mismo():
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
        ), f"correo {n}"
        raws.append({"messageId": f"id{n}", "threadId": f"hilo{n}", "raw": _b64(raw)})
    clean = sanitize_response({"messages": raws, "nextPageToken": None}, GUARD)
    for m in clean["messages"]:
        m.pop("raw", None)  # trae la fecha y el Message-ID del momento
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
    "error": ("n01", None, RuntimeError("falla de red")),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_el_clasificador_decide_lo_mismo_y_envia_lo_mismo(name, monkeypatch):
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


def test_el_detector_con_modelo_da_lo_mismo_y_envia_lo_mismo(monkeypatch):
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


def test_las_etiquetas_de_ejemplo_siguen_siendo_las_de_un_bot_de_ventas():
    assert list(LEAD_LABELS) == ["prioritario", "interesado", "consulta", "soporte", "spam"]

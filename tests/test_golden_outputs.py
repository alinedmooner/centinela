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
    ETIQUETAS_CLINICA,
    GUARDIA,
    MENSAJES,
    ProveedorFalso,
    cargar,
    cli,
    como_texto,
    correos_de_la_demo,
    veredicto_de,
    via_json,
)

from centinela import ETIQUETAS_LEADS, ClasificadorSeguro, crear_tarjeta, resolver, texto_de_tarjeta
from centinela.buzon_seguro import limpiar_respuesta
from centinela.correo import leer_correo, texto_a_revisar
from centinela.detectores.llm import DetectorLLM
from centinela.proveedores import RespuestaModelo

CLI = cargar("cli.json")
IDS_CLI = [k for k in CLI if k in MENSAJES and CLI[k]["json"]]


@pytest.mark.parametrize("id_", IDS_CLI)
def test_la_cli_da_lo_mismo_en_json_y_en_texto(id_):
    esperado = CLI[id_]
    en_json = cli("revisar", "--json", "--tarjeta", MENSAJES[id_])
    assert en_json["exit"] == esperado["json"]["exit"]
    assert json.loads(en_json["stdout"]) == esperado["json"]["salida"]
    en_texto = cli("revisar", "--tarjeta", MENSAJES[id_])
    assert en_texto["exit"] == esperado["texto"]["exit"]
    assert en_texto["stdout"] == esperado["texto"]["stdout"]


@pytest.mark.parametrize("id_", [k.split("@")[0] for k in CLI if k.endswith("@clinica")])
def test_la_cli_con_las_etiquetas_de_una_clinica(id_):
    esperado = CLI[f"{id_}@clinica"]["json"]
    r = cli("revisar", "--json", "--etiquetas", str(ETIQUETAS_CLINICA), MENSAJES[id_])
    assert r["exit"] == esperado["exit"]
    assert json.loads(r["stdout"]) == esperado["salida"]
    assert r["stderr"] == esperado["stderr"]


def test_la_cli_avisa_de_etiquetas_raras_y_rechaza_las_invalidas(tmp_path):
    raras = tmp_path / "raras.json"
    raras.write_text('{"muy urgente": "x", "spam": "y"}', encoding="utf-8")
    r = cli("revisar", "--etiquetas", str(raras), "Hola")
    assert (r["exit"], r["stderr"]) == (
        CLI["etiquetas_raras"]["exit"],
        CLI["etiquetas_raras"]["stderr"],
    )
    vacias = tmp_path / "vacias.json"
    vacias.write_text("[]", encoding="utf-8")
    r = cli("revisar", "--etiquetas", str(vacias), "Hola")
    assert (r["exit"], r["stderr"]) == (
        CLI["etiquetas_invalidas"]["exit"],
        CLI["etiquetas_invalidas"]["stderr"],
    )


def test_la_cli_sin_comando_muestra_la_ayuda_y_sale_con_0():
    assert cli()["exit"] == CLI["sin_comando"]["exit"] == 0


TARJETAS = cargar("cards.json")


@pytest.mark.parametrize("id_", list(TARJETAS))
def test_la_tarjeta_de_revision_es_la_misma(id_):
    esperado = TARJETAS[id_]
    veredicto = veredicto_de(id_)
    tarjeta = crear_tarjeta(MENSAJES[id_], veredicto)
    assert via_json(veredicto.a_dict()) == esperado["veredicto"]
    assert via_json(asdict(tarjeta)) == esperado["tarjeta"]
    assert texto_de_tarjeta(tarjeta) == esperado["texto"]


SALA = cargar("review_room.json")


@pytest.mark.parametrize("id_", list(SALA))
def test_las_reglas_de_la_sala_de_revision_son_las_mismas(id_):
    tarjeta = crear_tarjeta(MENSAJES[id_], veredicto_de(id_))
    obtenido = []
    for accion, etiqueta, segundo in itertools.product(
        ("es_fraude", "es_legitimo", "no_estoy_seguro", "otra_cosa"),
        (None, "consulta", "inventada"),
        (None, "ana", "luis"),
    ):
        fila = {"accion": accion, "etiqueta": etiqueta, "segundo": segundo}
        try:
            fila["r"] = via_json(
                asdict(resolver(tarjeta, accion, "ana", etiqueta=etiqueta, segundo_revisor=segundo))
            )
        except Exception as error:  # noqa: BLE001
            fila["error"] = [type(error).__name__, str(error)]
        obtenido.append(fila)
    assert obtenido == SALA[id_]


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def test_el_lector_de_correo_y_el_buzon_seguro_dan_lo_mismo():
    esperado = cargar("mail.json")
    crudos = []
    for n, mensaje in enumerate(correos_de_la_demo(), 1):
        raw = mensaje.as_bytes()
        correo = leer_correo(raw)
        texto = texto_a_revisar(correo)
        veredicto = GUARDIA.revisar(texto)
        tarjeta = (
            crear_tarjeta(texto, veredicto, enlaces_ocultos=correo.enlaces)
            if veredicto.decision == "revisar"
            else None
        )
        assert (
            via_json(
                {
                    "correo": asdict(correo),
                    "texto_a_revisar": texto,
                    "veredicto": veredicto.a_dict(),
                    "tarjeta": asdict(tarjeta) if tarjeta else None,
                    "texto_de_tarjeta": texto_de_tarjeta(tarjeta) if tarjeta else None,
                }
            )
            == esperado[str(n)]
        ), f"correo {n}"
        crudos.append({"messageId": f"id{n}", "threadId": f"hilo{n}", "raw": _b64(raw)})
    limpio = limpiar_respuesta({"messages": crudos, "nextPageToken": None})
    for m in limpio["messages"]:
        m.pop("raw", None)  # trae la fecha y el Message-ID del momento
    assert via_json(limpio) == esperado["gmail"]


ESCENARIOS = {
    "normal_valida": ("n01", RespuestaModelo({"etiqueta": "interesado"}), None),
    "orden_al_bot": ("a01", RespuestaModelo({"etiqueta": "prioritario"}), None),
    "etiqueta_inventada": ("n01", RespuestaModelo({"etiqueta": "vip"}), None),
    "sin_clave": ("n01", RespuestaModelo({"otra_cosa": 1}), None),
    "sin_datos": ("n01", RespuestaModelo(None), None),
    "rechazo": ("n01", RespuestaModelo(None, rechazo=True), None),
    "error": ("n01", None, RuntimeError("falla de red")),
}


@pytest.mark.parametrize("nombre", list(ESCENARIOS))
def test_el_clasificador_decide_lo_mismo_y_envia_lo_mismo(nombre, monkeypatch):
    monkeypatch.setattr(secrets, "token_hex", lambda n=8: "0123abcd")
    id_, respuesta, error = ESCENARIOS[nombre]
    proveedor = ProveedorFalso(respuesta, error)
    r = ClasificadorSeguro(proveedor).clasificar(MENSAJES[id_])
    esperado = cargar("classifier.json")[nombre]
    assert (
        via_json(
            {
                "etiqueta": r.etiqueta,
                "motivo": r.motivo,
                "etiqueta_modelo": r.etiqueta_modelo,
                "veredicto": r.veredicto.a_dict(),
            }
        )
        == esperado["resultado"]
    )
    # El orden de las claves del esquema también lo ve el modelo.
    assert como_texto(proveedor.llamadas) == como_texto(esperado["llamadas"])


def test_el_detector_con_modelo_da_lo_mismo_y_envia_lo_mismo(monkeypatch):
    monkeypatch.setattr(secrets, "token_hex", lambda n=8: "0123abcd")
    esperado = cargar("llm_detector.json")
    proveedor = ProveedorFalso(
        RespuestaModelo(
            {
                "ordenes_para_ia": True,
                "engano_a_personas": False,
                "trucos": ["autoridad", "inventado", "autoridad"],
                "motivo": "Pide cambiar la etiqueta.",
            }
        )
    )
    assert (
        via_json(asdict(DetectorLLM(proveedor).revisar("Mensaje de prueba")))
        == esperado["hallazgo"]
    )
    assert como_texto(proveedor.llamadas) == como_texto(esperado["llamadas"])
    for nombre, respuesta in {
        "rechazo": RespuestaModelo(None, rechazo=True),
        "invalida": RespuestaModelo({"ordenes_para_ia": "si"}),
        "sin_datos": RespuestaModelo(None),
    }.items():
        obtenido = via_json(
            asdict(DetectorLLM(ProveedorFalso(respuesta)).revisar("Mensaje de prueba"))
        )
        assert obtenido == esperado[nombre], nombre
    largo = DetectorLLM(
        ProveedorFalso(RespuestaModelo({"ordenes_para_ia": False})), max_caracteres=10
    )
    assert via_json(asdict(largo.revisar("x" * 50))) == esperado["truncado"]


def test_las_etiquetas_de_ejemplo_siguen_siendo_las_de_un_bot_de_ventas():
    assert list(ETIQUETAS_LEADS) == ["prioritario", "interesado", "consulta", "soporte", "spam"]

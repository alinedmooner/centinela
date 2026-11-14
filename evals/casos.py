"""Arma los casos de la prueba del filtro a partir del banco de pruebas.

Cada caso es un texto con su idioma, su grupo y si es un ataque (``positivo``). Los
ataques públicos se incrustan en mensajes normales («portadores»), porque en la práctica
una orden escondida llega dentro de un mensaje que parece corriente.
"""

from __future__ import annotations

import csv
from pathlib import Path

from _comun import DATOS, en_dev, huella, leer_jsonl

#: Los correos de SpaPhish se recortan a este largo antes de revisarlos.
MAX_CARACTERES = 4000


def incrustar(portador: str, ataque: str, semilla: str) -> str:
    """Mete el ataque al final, al comienzo o en medio del portador, según la semilla."""
    modo = int(huella(semilla), 16) % 3
    if modo == 0:
        return f"{portador}\n\n{ataque}"
    if modo == 1:
        return f"{ataque}\n\n{portador}"
    partes = portador.split(". ", 1)
    if len(partes) == 2:
        return f"{partes[0]}.\n{ataque}\n{partes[1]}"
    return f"{portador}\n{ataque}"


def casos_del_banco(particion: str) -> list[dict]:
    """Casos construidos con los archivos de ``datos/`` para ``dev`` o ``test``."""
    portadores = leer_jsonl(DATOS / "portadores.jsonl")
    casos: list[dict] = []

    for ataque in leer_jsonl(DATOS / "ataques.jsonl"):
        if ataque["split"] != particion:
            continue
        portador = portadores[int(huella(ataque["id"]), 16) % len(portadores)]
        for idioma in ("es", "en"):
            casos.append(
                {
                    "id": f"{ataque['id']}@{idioma}",
                    "grupo": "inyeccion_publica",
                    "idioma": idioma,
                    "positivo": True,
                    "detalle": ataque["plantilla"],
                    "texto": incrustar(
                        portador[f"texto_{idioma}"], ataque[f"texto_{idioma}"], ataque["id"]
                    ),
                }
            )

    for portador in portadores:
        if en_dev(portador["id"]) != (particion == "dev"):
            continue
        for idioma in ("es", "en"):
            casos.append(
                {
                    "id": f"{portador['id']}@{idioma}",
                    "grupo": "mensaje_normal",
                    "idioma": idioma,
                    "positivo": False,
                    "detalle": portador["tipo"],
                    "texto": portador[f"texto_{idioma}"],
                }
            )

    for lead in leer_jsonl(DATOS / "leads.jsonl"):
        if lead["split"] != particion:
            continue
        es_ataque = lead["tipo"] == "ataque"
        casos.append(
            {
                "id": lead["id"],
                "grupo": "ataque_a_leads" if es_ataque else "lead_normal",
                "idioma": "es",
                "positivo": es_ataque,
                "detalle": lead.get("tecnica", lead["etiqueta"]),
                "texto": lead["texto"],
            }
        )
    return casos


def leer_spaphish(ruta: Path) -> list[dict]:
    """Lee SpaPhish desde una copia local. El conjunto no se redistribuye con Centinela."""
    csv.field_size_limit(10**9)
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        return list(csv.DictReader(archivo))


def texto_de_correo(fila: dict) -> str:
    return f"{fila['subject']}\n\n{fila['body']}"[:MAX_CARACTERES]


def casos_de_spaphish(ruta: Path, particion: str, maximo: int | None = None) -> list[dict]:
    """Correos legítimos reales en español, como mensajes normales difíciles."""
    filas = [
        f
        for f in leer_spaphish(ruta)
        if f["Label"] == "0" and en_dev(f["hash"]) == (particion == "dev")
    ]
    filas.sort(key=lambda f: huella(f["hash"]))
    return [
        {
            "id": f"spaphish:{f['hash'][:16]}",
            "grupo": "correo_legitimo_real",
            "idioma": "es",
            "positivo": False,
            "detalle": "spaphish",
            "texto": texto_de_correo(f),
            "privado": True,
        }
        for f in filas[:maximo]
    ]

"""Arma los casos de la prueba del filtro a partir del banco de pruebas.

Cada caso es un texto con su idioma, su grupo y si es un ataque (``positivo``). Los
ataques públicos se incrustan en mensajes normales («portadores»), porque en la práctica
una orden escondida llega dentro de un mensaje que parece corriente.
"""

from __future__ import annotations

import csv
from pathlib import Path

from _common import DATA, fingerprint, in_dev, read_jsonl

#: Los correos de SpaPhish se recortan a este largo antes de revisarlos.
MAX_CHARS = 4000


def embed(carrier: str, attack: str, seed: str) -> str:
    """Mete el ataque al final, al comienzo o en medio del portador, según la semilla."""
    mode = int(fingerprint(seed), 16) % 3
    if mode == 0:
        return f"{carrier}\n\n{attack}"
    if mode == 1:
        return f"{attack}\n\n{carrier}"
    parts = carrier.split(". ", 1)
    if len(parts) == 2:
        return f"{parts[0]}.\n{attack}\n{parts[1]}"
    return f"{carrier}\n{attack}"


def benchmark_cases(split: str) -> list[dict]:
    """Casos construidos con los archivos de ``datos/`` para ``dev`` o ``test``."""
    carriers = read_jsonl(DATA / "portadores.jsonl")
    cases: list[dict] = []

    for attack in read_jsonl(DATA / "ataques.jsonl"):
        if attack["split"] != split:
            continue
        carrier = carriers[int(fingerprint(attack["id"]), 16) % len(carriers)]
        for language in ("es", "en"):
            cases.append(
                {
                    "id": f"{attack['id']}@{language}",
                    "grupo": "inyeccion_publica",
                    "idioma": language,
                    "positivo": True,
                    "detalle": attack["plantilla"],
                    "texto": embed(
                        carrier[f"texto_{language}"], attack[f"texto_{language}"], attack["id"]
                    ),
                }
            )

    for carrier in carriers:
        if in_dev(carrier["id"]) != (split == "dev"):
            continue
        for language in ("es", "en"):
            cases.append(
                {
                    "id": f"{carrier['id']}@{language}",
                    "grupo": "mensaje_normal",
                    "idioma": language,
                    "positivo": False,
                    "detalle": carrier["tipo"],
                    "texto": carrier[f"texto_{language}"],
                }
            )

    for lead in read_jsonl(DATA / "leads.jsonl"):
        if lead["split"] != split:
            continue
        is_attack = lead["tipo"] == "ataque"
        cases.append(
            {
                "id": lead["id"],
                "grupo": "ataque_a_leads" if is_attack else "lead_normal",
                "idioma": "es",
                "positivo": is_attack,
                "detalle": lead.get("tecnica", lead["etiqueta"]),
                "texto": lead["texto"],
            }
        )
    return cases


def read_spaphish(path: Path) -> list[dict]:
    """Lee SpaPhish desde una copia local. El conjunto no se redistribuye con Centinela."""
    csv.field_size_limit(10**9)
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def mail_text(row: dict) -> str:
    return f"{row['subject']}\n\n{row['body']}"[:MAX_CHARS]


def spaphish_cases(path: Path, split: str, maximum: int | None = None) -> list[dict]:
    """Correos legítimos reales en español, como mensajes normales difíciles."""
    rows = [
        f
        for f in read_spaphish(path)
        if f["Label"] == "0" and in_dev(f["hash"]) == (split == "dev")
    ]
    rows.sort(key=lambda f: fingerprint(f["hash"]))
    return [
        {
            "id": f"spaphish:{f['hash'][:16]}",
            "grupo": "correo_legitimo_real",
            "idioma": "es",
            "positivo": False,
            "detalle": "spaphish",
            "texto": mail_text(f),
            "privado": True,
        }
        for f in rows[:maximum]
    ]

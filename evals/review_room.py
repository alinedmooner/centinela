"""Prueba 4: la sala de revisión sobre correos reales. No usa clave ni internet.

    uv run python evals/revision.py --spaphish "RUTA/Spaphish dataset - DiB.csv"

Para cada correo de SpaPhish arma la tarjeta que vería quien lo revisa y cuenta:

- cuántos enlaces del texto siguen activos después de desarmarlo;
- en cuántos correos un enlace lleva a un dominio que no aparece escrito en el texto. En un
  correo real ese destino va escondido en el HTML; aquí se toma del campo ``urls`` del
  conjunto y se le pasa a la tarjeta, como lo haría una integración con el correo;
- si la tarjeta reconoce qué pide el correo y con qué presiona;
- cuánto del texto queda igual.

Si existe la respuesta guardada del revisor de la prueba 3, se usa para saber qué correos
habría marcado como engaño. Guarda solo conteos por identificador, nunca el texto.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

from _common import RESULTS, proportion, read_jsonl, write_jsonl
from cases import mail_text, read_spaphish

from centinela import LEAD_LABELS, Guard, RulesDetector, create_card
from centinela.review import SENSITIVE_ASKS

#: Señal de enlace activo, independiente de las expresiones del desarmador.
ACTIVE = re.compile(r"(?i)(?:https?|ftp)://\S|\bwww\.\S")
WEB = re.compile(r"(?i)https?://|www\.")
INSTRUCT_AI = "darle órdenes al asistente de IA"


def registered_links(field: str) -> list[str]:
    """Los enlaces web que SpaPhish registra para un correo, en su formato «[a],[b]».

    Deja fuera lo que no lleva a una página: anclas («#») e imágenes incrustadas («cid:»).
    """
    candidates = (u.strip() for u in re.findall(r"\[([^\[\]]+)\]", field or ""))
    return [u for u in candidates if WEB.match(u)]


def domain_of(link: str) -> str:
    try:
        parts = urlsplit(link if "://" in link else f"http://{link}")
        return (parts.hostname or "").lower()
    except ValueError:
        return ""


def measure(row: dict, deception: bool | None, guard: Guard) -> dict:
    text = mail_text(row)
    registered = registered_links(row.get("urls", ""))
    verdict = guard.check(text)
    if deception:
        verdict = replace(verdict, decision="review", people_deception=True)
    card = create_card(text, verdict, hidden_links=registered)
    defanged = card.defanged_text
    lowercase = text.lower()
    destinations = {d for d in map(domain_of, registered) if d}
    antes, after = text.split(), defanged.split()
    blocks = SequenceMatcher(None, antes, after, autojunk=False).get_matching_blocks()
    return {
        "id": row["hash"][:16],
        "phishing": row["Label"] == "1",
        "revisor_lo_marco": deception,
        "enlaces_en_texto": len(ACTIVE.findall(text)),
        "enlaces_activos_despues": len(ACTIVE.findall(defanged)),
        "registrados": len(registered),
        "registrados_en_texto": sum(u in text for u in registered),
        "registrados_intactos": sum(u in text and u in defanged for u in registered),
        "destinos": len(destinations),
        "destinos_ocultos": sum(d not in lowercase for d in destinations),
        "destinos_en_tarjeta": len(card.links),
        "pide": [p for p in card.asks if p != INSTRUCT_AI],
        "presiona_con": list(card.pressure),
        "dice_ser": bool(card.claims_to_be),
        "segunda_persona": card.needs_second_person,
        "palabras": len(antes),
        "palabras_iguales": sum(b.size for b in blocks),
        "numeros_ocultos": defanged.count("[número oculto"),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)

    def count_where(condition) -> dict:
        return proportion(sum(1 for f in rows if condition(f)), n)

    def total(field: str) -> int:
        return sum(f[field] for f in rows)

    asks_found = sorted({p for f in rows for p in f["pide"]})
    pressures = sorted({p for f in rows for p in f["presiona_con"]})
    return {
        "correos": n,
        "enlaces_activos": {
            "antes": total("enlaces_en_texto"),
            "despues": total("enlaces_activos_despues"),
        },
        "registrados": {
            "total": total("registrados"),
            "en_texto": total("registrados_en_texto"),
            "intactos": total("registrados_intactos"),
        },
        "con_enlace": count_where(lambda f: f["destinos"] > 0 or f["enlaces_en_texto"] > 0),
        "con_destino_oculto": count_where(lambda f: f["destinos_ocultos"] > 0),
        "con_destino_en_tarjeta": count_where(lambda f: f["destinos_en_tarjeta"] > 0),
        "con_pedido": count_where(lambda f: bool(f["pide"])),
        "con_presion": count_where(lambda f: bool(f["presiona_con"])),
        "con_pedido_delicado": count_where(lambda f: any(p in SENSITIVE_ASKS for p in f["pide"])),
        "con_remitente": count_where(lambda f: f["dice_ser"]),
        "exige_segunda_persona": count_where(lambda f: f["segunda_persona"]),
        "por_pedido": {p: count_where(lambda f, p=p: p in f["pide"]) for p in asks_found},
        "por_presion": {p: count_where(lambda f, p=p: p in f["presiona_con"]) for p in pressures},
        "palabras_iguales": proportion(total("palabras_iguales"), total("palabras")),
        "numeros_ocultos": total("numeros_ocultos"),
        "con_numero_oculto": count_where(lambda f: f["numeros_ocultos"] > 0),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--spaphish", type=Path, required=True, help="copia local del CSV de SpaPhish"
    )
    parser.add_argument("--reviewer", default="claude-haiku-5-5", help="respuestas de la prueba 3")
    parser.add_argument("--maximum", type=int, default=None, help="usa solo los primeros N correos")
    args = parser.parse_args(argv)

    mails = sorted(read_spaphish(args.spaphish), key=lambda f: f["hash"])[: args.maximum]
    saved = read_jsonl(RESULTS / "phishing" / f"{args.reviewer}.jsonl")
    deception = {r["id"]: bool(r.get("engano")) for r in saved}
    guard = Guard([RulesDetector(labels=LEAD_LABELS)])
    rows = [measure(f, deception.get(f["hash"][:16]), guard) for f in mails]

    folder = RESULTS / "review"
    write_jsonl(folder / "spaphish.jsonl", rows)
    summary = {
        "correos": len(rows),
        "revisor": args.reviewer if deception else None,
        "con_respuesta_del_revisor": sum(f["revisor_lo_marco"] is not None for f in rows),
        "phishing": summarize([f for f in rows if f["phishing"]]),
        "legitimos": summarize([f for f in rows if not f["phishing"]]),
    }
    (folder / "resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

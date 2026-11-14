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

from _comun import RESULTADOS, escribir_jsonl, leer_jsonl, proporcion
from casos import leer_spaphish, texto_de_correo

from centinela import ETIQUETAS_LEADS, DetectorReglas, Guardia, crear_tarjeta
from centinela.revision import PEDIDOS_DELICADOS

#: Señal de enlace activo, independiente de las expresiones del desarmador.
ACTIVO = re.compile(r"(?i)(?:https?|ftp)://\S|\bwww\.\S")
WEB = re.compile(r"(?i)https?://|www\.")
ORDEN_IA = "darle órdenes al asistente de IA"


def enlaces_registrados(campo: str) -> list[str]:
    """Los enlaces web que SpaPhish registra para un correo, en su formato «[a],[b]».

    Deja fuera lo que no lleva a una página: anclas («#») e imágenes incrustadas («cid:»).
    """
    candidatos = (u.strip() for u in re.findall(r"\[([^\[\]]+)\]", campo or ""))
    return [u for u in candidatos if WEB.match(u)]


def dominio_de(enlace: str) -> str:
    try:
        partes = urlsplit(enlace if "://" in enlace else f"http://{enlace}")
        return (partes.hostname or "").lower()
    except ValueError:
        return ""


def medir(fila: dict, engano: bool | None, guardia: Guardia) -> dict:
    texto = texto_de_correo(fila)
    registrados = enlaces_registrados(fila.get("urls", ""))
    veredicto = guardia.revisar(texto)
    if engano:
        veredicto = replace(veredicto, decision="revisar", engano_a_personas=True)
    tarjeta = crear_tarjeta(texto, veredicto, enlaces_ocultos=registrados)
    desarmado = tarjeta.texto_desarmado
    minusculas = texto.lower()
    destinos = {d for d in map(dominio_de, registrados) if d}
    antes, despues = texto.split(), desarmado.split()
    bloques = SequenceMatcher(None, antes, despues, autojunk=False).get_matching_blocks()
    return {
        "id": fila["hash"][:16],
        "phishing": fila["Label"] == "1",
        "revisor_lo_marco": engano,
        "enlaces_en_texto": len(ACTIVO.findall(texto)),
        "enlaces_activos_despues": len(ACTIVO.findall(desarmado)),
        "registrados": len(registrados),
        "registrados_en_texto": sum(u in texto for u in registrados),
        "registrados_intactos": sum(u in texto and u in desarmado for u in registrados),
        "destinos": len(destinos),
        "destinos_ocultos": sum(d not in minusculas for d in destinos),
        "destinos_en_tarjeta": len(tarjeta.enlaces),
        "pide": [p for p in tarjeta.pide if p != ORDEN_IA],
        "presiona_con": list(tarjeta.presiona_con),
        "dice_ser": bool(tarjeta.dice_ser),
        "segunda_persona": tarjeta.requiere_segunda_persona,
        "palabras": len(antes),
        "palabras_iguales": sum(b.size for b in bloques),
        "numeros_ocultos": desarmado.count("[número oculto"),
    }


def resumir(filas: list[dict]) -> dict:
    n = len(filas)

    def cuantos(condicion) -> dict:
        return proporcion(sum(1 for f in filas if condicion(f)), n)

    def suma(campo: str) -> int:
        return sum(f[campo] for f in filas)

    pedidos = sorted({p for f in filas for p in f["pide"]})
    presiones = sorted({p for f in filas for p in f["presiona_con"]})
    return {
        "correos": n,
        "enlaces_activos": {
            "antes": suma("enlaces_en_texto"),
            "despues": suma("enlaces_activos_despues"),
        },
        "registrados": {
            "total": suma("registrados"),
            "en_texto": suma("registrados_en_texto"),
            "intactos": suma("registrados_intactos"),
        },
        "con_enlace": cuantos(lambda f: f["destinos"] > 0 or f["enlaces_en_texto"] > 0),
        "con_destino_oculto": cuantos(lambda f: f["destinos_ocultos"] > 0),
        "con_destino_en_tarjeta": cuantos(lambda f: f["destinos_en_tarjeta"] > 0),
        "con_pedido": cuantos(lambda f: bool(f["pide"])),
        "con_presion": cuantos(lambda f: bool(f["presiona_con"])),
        "con_pedido_delicado": cuantos(lambda f: any(p in PEDIDOS_DELICADOS for p in f["pide"])),
        "con_remitente": cuantos(lambda f: f["dice_ser"]),
        "exige_segunda_persona": cuantos(lambda f: f["segunda_persona"]),
        "por_pedido": {p: cuantos(lambda f, p=p: p in f["pide"]) for p in pedidos},
        "por_presion": {p: cuantos(lambda f, p=p: p in f["presiona_con"]) for p in presiones},
        "palabras_iguales": proporcion(suma("palabras_iguales"), suma("palabras")),
        "numeros_ocultos": suma("numeros_ocultos"),
        "con_numero_oculto": cuantos(lambda f: f["numeros_ocultos"] > 0),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--spaphish", type=Path, required=True, help="copia local del CSV de SpaPhish"
    )
    parser.add_argument("--revisor", default="claude-haiku-5-5", help="respuestas de la prueba 3")
    parser.add_argument("--maximo", type=int, default=None, help="usa solo los primeros N correos")
    args = parser.parse_args(argv)

    correos = sorted(leer_spaphish(args.spaphish), key=lambda f: f["hash"])[: args.maximo]
    guardadas = leer_jsonl(RESULTADOS / "phishing" / f"{args.revisor}.jsonl")
    engano = {r["id"]: bool(r.get("engano")) for r in guardadas}
    guardia = Guardia([DetectorReglas(etiquetas=ETIQUETAS_LEADS)])
    filas = [medir(f, engano.get(f["hash"][:16]), guardia) for f in correos]

    carpeta = RESULTADOS / "revision"
    escribir_jsonl(carpeta / "spaphish.jsonl", filas)
    resumen = {
        "correos": len(filas),
        "revisor": args.revisor if engano else None,
        "con_respuesta_del_revisor": sum(f["revisor_lo_marco"] is not None for f in filas),
        "phishing": resumir([f for f in filas if f["phishing"]]),
        "legitimos": resumir([f for f in filas if not f["phishing"]]),
    }
    (carpeta / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

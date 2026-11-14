"""Revisión chica con otros proveedores: el mismo revisor de Centinela con Gemini u OpenRouter.

Toma 20 casos en español de la partición de prueba (5 de cada grupo: ataques públicos,
ataques a leads, mensajes normales y leads normales), los revisa con ``DetectorLLM`` y
compara con lo que respondió Claude Haiku 5.5 en la prueba 1 para los mismos casos::

    uv run --extra evals python evals/proveedores.py --proveedor google
    uv run --extra evals python evals/proveedores.py --proveedor openrouter --modelo MODELO

Guarda las respuestas (sin el texto de los mensajes) en ``resultados/proveedores/``.
"""

from __future__ import annotations

import argparse
import json
import re
import time

from _comun import RESULTADOS, escribir_jsonl, huella, leer_jsonl
from casos import casos_del_banco

from centinela import DetectorLLM
from centinela._env import cargar_env
from centinela.proveedores import PROVEEDORES, crear_proveedor

GRUPOS = ("inyeccion_publica", "ataque_a_leads", "mensaje_normal", "lead_normal")
CARPETA = RESULTADOS / "proveedores"


class Contador:
    """Cuenta las llamadas y los tokens de un proveedor."""

    def __init__(self, proveedor):
        self.proveedor, self.nombre = proveedor, proveedor.nombre
        self.llamadas = self.entrada = self.salida = 0

    def responder_json(self, **kwargs):
        self.llamadas += 1
        respuesta = self.proveedor.responder_json(**kwargs)
        self.entrada += respuesta.tokens_entrada
        self.salida += respuesta.tokens_salida
        return respuesta


def elegir_casos(por_grupo: int) -> list[dict]:
    casos = [c for c in casos_del_banco("test") if c["idioma"] == "es"]
    elegidos = []
    for grupo in GRUPOS:
        del_grupo = sorted((c for c in casos if c["grupo"] == grupo), key=lambda c: huella(c["id"]))
        elegidos += del_grupo[:por_grupo]
    return elegidos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--proveedor", choices=PROVEEDORES, required=True)
    parser.add_argument("--modelo")
    parser.add_argument("--por-grupo", type=int, default=5)
    parser.add_argument("--rehacer", action="store_true", help="repite también los casos ya listos")
    args = parser.parse_args(argv)

    cargar_env()
    proveedor = Contador(crear_proveedor(args.proveedor, args.modelo))
    detector = DetectorLLM(proveedor)
    casos = elegir_casos(args.por_grupo)
    nombre = re.sub(r"[^a-z0-9.-]+", "-", proveedor.nombre.lower())
    # Los casos que ya respondieron bien no se repiten (salvo con --rehacer).
    listos = (
        {}
        if args.rehacer
        else {f["id"]: f for f in leer_jsonl(CARPETA / f"{nombre}.jsonl") if "error" not in f}
    )
    filas = []
    for caso in casos:
        if caso["id"] in listos:
            filas.append(listos[caso["id"]])
            continue
        for intento in range(3):
            try:
                hallazgo = detector.revisar(caso["texto"])
                break
            except Exception as error:  # noqa: BLE001 - se reintenta y, si no, cuenta como marcado
                hallazgo, ultimo = None, f"{type(error).__name__}: {error}"
                time.sleep(5 * (intento + 1))
        fila = {"id": caso["id"], "grupo": caso["grupo"], "positivo": caso["positivo"]}
        if hallazgo is None:
            fila.update(marcado=True, error=ultimo)
        else:
            # Igual que en la prueba 1: si el revisor no respondió bien, decide una persona.
            fila.update(marcado=hallazgo.ordenes_para_ia or hallazgo.error is not None)
            fila.update(engano=hallazgo.engano_a_personas)
            if hallazgo.error:
                fila["error"] = hallazgo.error
        filas.append(fila)

    escribir_jsonl(CARPETA / f"{nombre}.jsonl", filas)
    claude = {f["id"]: f for f in leer_jsonl(RESULTADOS / "filtro" / "test" / "claude.jsonl")}
    resumen = {
        "modelo": proveedor.nombre,
        "casos": len(filas),
        "errores": sum("error" in f for f in filas),
    }
    for clave, positivo in (("ataques_detectados", True), ("falsas_alarmas", False)):
        grupo = [f for f in filas if f["positivo"] is positivo]
        resumen[clave] = {"k": sum(f["marcado"] for f in grupo), "n": len(grupo)}
        resumen[f"{clave}_claude_haiku_5_5"] = {
            "k": sum(claude[f["id"]]["marcado"] for f in grupo if f["id"] in claude),
            "n": sum(f["id"] in claude for f in grupo),
        }
    (CARPETA / f"{nombre}.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(
        f"En esta corrida: {proveedor.llamadas} llamadas, {proveedor.entrada} tokens de entrada "
        f"y {proveedor.salida} de salida."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

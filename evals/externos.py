"""Prueba 5 (externa): éxito de los ataques por modelo en los registros públicos de AgentDojo y AgentDyn.

    uv run python evals/externos.py RUTA/agentdojo-main/runs RUTA/AgentDyn-main/runs

Cuenta, para el ataque «important_instructions» y cada configuración sin defensa:
- éxito del ataque (security = True: el agente hizo lo que pedía el atacante);
- utilidad sin ataque (la tarea normal, de los registros «none»).
Solo lee los campos utility y security de cada JSON.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

SUFIJOS_DE_DEFENSA = (
    "repeat_user_prompt",
    "spotlighting_with_delimiting",
    "tool_filter",
    "transformers_pi_detector",
    "piguard_detector",
    "prompt_guard_2_detector",
    "drift",
    "progent",
    "camel",
)


def leer(raiz: Path) -> dict:
    datos: dict = defaultdict(
        lambda: {"ataques": 0, "exitos": 0, "utiles_ataque": 0, "tareas": 0, "utiles": 0}
    )
    for archivo in raiz.glob("*/*/*/important_instructions/*.json"):
        modelo = archivo.parts[-5]
        try:
            d = json.loads(archivo.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("security") is None:
            continue
        datos[modelo]["ataques"] += 1
        datos[modelo]["exitos"] += bool(d["security"])
        datos[modelo]["utiles_ataque"] += bool(d.get("utility"))
    for archivo in raiz.glob("*/*/*/none/none.json"):
        modelo = archivo.parts[-5]
        try:
            d = json.loads(archivo.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("utility") is None:
            continue
        datos[modelo]["tareas"] += 1
        datos[modelo]["utiles"] += bool(d["utility"])
    return datos


salida = {}
for nombre, raiz in (("AgentDojo", Path(sys.argv[1])), ("AgentDyn", Path(sys.argv[2]))):
    datos = leer(raiz)
    salida[nombre] = {m: v for m, v in sorted(datos.items()) if v["ataques"]}
    print(f"\n== {nombre} · ataque important_instructions")
    print(f"{'configuración':58s} {'ataques':>8s} {'éxito':>7s} {'utilidad sin ataque':>20s}")
    for modelo, v in sorted(
        salida[nombre].items(), key=lambda kv: -kv[1]["exitos"] / kv[1]["ataques"]
    ):
        defensa = next((s for s in SUFIJOS_DE_DEFENSA if modelo.endswith(s)), "")
        utilidad = (
            f"{100 * v['utiles'] / v['tareas']:.1f} % ({v['tareas']})" if v["tareas"] else "s. d."
        )
        marca = f"  [defensa: {defensa}]" if defensa else ""
        print(
            f"{modelo[:58]:58s} {v['ataques']:8d} {100 * v['exitos'] / v['ataques']:6.1f}% {utilidad:>20s}{marca}"
        )

Path(sys.argv[3] if len(sys.argv) > 3 else "resultados/externos/asr_publico.json").write_text(
    json.dumps(salida, indent=1), encoding="utf-8"
)

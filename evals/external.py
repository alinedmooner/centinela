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

DEFENSE_SUFFIXES = (
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


def leer(root: Path) -> dict:
    data: dict = defaultdict(
        lambda: {"ataques": 0, "exitos": 0, "utiles_ataque": 0, "tareas": 0, "utiles": 0}
    )
    for file in root.glob("*/*/*/important_instructions/*.json"):
        model = file.parts[-5]
        try:
            d = json.loads(file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("security") is None:
            continue
        data[model]["ataques"] += 1
        data[model]["exitos"] += bool(d["security"])
        data[model]["utiles_ataque"] += bool(d.get("utility"))
    for file in root.glob("*/*/*/none/none.json"):
        model = file.parts[-5]
        try:
            d = json.loads(file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("utility") is None:
            continue
        data[model]["tareas"] += 1
        data[model]["utiles"] += bool(d["utility"])
    return data


output = {}
for name, root in (("AgentDojo", Path(sys.argv[1])), ("AgentDyn", Path(sys.argv[2]))):
    data = leer(root)
    output[name] = {m: v for m, v in sorted(data.items()) if v["ataques"]}
    print(f"\n== {name} · ataque important_instructions")
    print(f"{'configuración':58s} {'ataques':>8s} {'éxito':>7s} {'utilidad sin ataque':>20s}")
    for model, v in sorted(
        output[name].items(), key=lambda kv: -kv[1]["exitos"] / kv[1]["ataques"]
    ):
        defense = next((s for s in DEFENSE_SUFFIXES if model.endswith(s)), "")
        utility = (
            f"{100 * v['utiles'] / v['tareas']:.1f} % ({v['tareas']})" if v["tareas"] else "s. d."
        )
        marker = f"  [defensa: {defense}]" if defense else ""
        print(
            f"{model[:58]:58s} {v['ataques']:8d} {100 * v['exitos'] / v['ataques']:6.1f}% {utility:>20s}{marker}"
        )

Path(sys.argv[3] if len(sys.argv) > 3 else "resultados/externos/asr_publico.json").write_text(
    json.dumps(output, indent=1), encoding="utf-8"
)

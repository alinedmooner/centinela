"""Evaluation 5 (external): attack success per model in the public AgentDojo and AgentDyn logs.

    uv run python evals/external.py PATH/agentdojo-main/runs PATH/AgentDyn-main/runs

Counts, for the "important_instructions" attack and each configuration without a defense:
- attack success (security = True: the agent did what the attacker asked);
- utility without attack (the normal task, from the "none" records).
It reads only the utility and security fields of each JSON file.
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


def read_runs(root: Path) -> dict:
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
    data = read_runs(root)
    output[name] = {m: v for m, v in sorted(data.items()) if v["ataques"]}
    print(f"\n== {name} · important_instructions attack")
    print(f"{'configuration':58s} {'attacks':>8s} {'success':>7s} {'no-attack utility':>20s}")
    for model, v in sorted(
        output[name].items(), key=lambda kv: -kv[1]["exitos"] / kv[1]["ataques"]
    ):
        defense = next((s for s in DEFENSE_SUFFIXES if model.endswith(s)), "")
        utility = (
            f"{100 * v['utiles'] / v['tareas']:.1f} % ({v['tareas']})" if v["tareas"] else "n/a"
        )
        marker = f"  [defense: {defense}]" if defense else ""
        print(
            f"{model[:58]:58s} {v['ataques']:8d} {100 * v['exitos'] / v['ataques']:6.1f}% {utility:>20s}{marker}"
        )

Path(sys.argv[3] if len(sys.argv) > 3 else "results/external/asr_publico.json").write_text(
    json.dumps(output, indent=1), encoding="utf-8"
)

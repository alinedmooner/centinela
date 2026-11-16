"""Ayudas para comparar lo que hace Centinela hoy con las salidas de referencia.

Las salidas de referencia están en tests/golden/main_9810607/ y salieron del código de
main@9810607, antes de pasar el proyecto a inglés (ver tests/golden/README.md).
"""

from __future__ import annotations

import contextlib
import io
import json
import runpy
from pathlib import Path

from centinela import LEAD_LABELS, Guard, RulesDetector, Verdict
from centinela.cli import main as cli_main

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden" / "main_9810607"
EXAMPLES = ROOT / "examples"
CLINIC_LABELS = EXAMPLES / "labels_clinic.json"


def load(name: str):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def as_text(value) -> str:
    """JSON con el orden de las claves: el orden del esquema también lo ve el modelo."""
    return json.dumps(value, ensure_ascii=False, indent=1)


#: Names of the dataclass fields (and so of the --json output) in main@9810607, before the
#: move to English. The reference outputs use them; the current code uses the English ones.
OLD_KEYS = {
    "ai_instructions": "ordenes_para_ia",
    "people_deception": "engano_a_personas",
    "tricks": "trucos",
    "evidence": "evidencias",
    "notice": "aviso",
    "findings": "hallazgos",
    "claims_to_be": "dice_ser",
    "asks": "pide",
    "pressure": "presiona_con",
    "links": "enlaces",
    "defanged_text": "texto_desarmado",
    "actions": "acciones",
    "needs_second_person": "requiere_segunda_persona",
    "hidden_destinations": "destinos_ocultos",
    "state": "estado",
    "label": "etiqueta",
    "reviewers": "revisores",
    "note": "nota",
    "reason": "motivo",
    "verdict": "veredicto",
    "model_label": "etiqueta_modelo",
    "sender": "remitente",
    "subject": "asunto",
    "text": "texto",
    "attachments": "adjuntos",
    "hidden_fragments": "fragmentos_ocultos",
}


def old_view(value):
    """The value with the key names that the reference outputs use."""
    if isinstance(value, dict):
        return {OLD_KEYS.get(k, k): old_view(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [old_view(v) for v in value]
    return value


def plain_json(value):
    """What the value gives when written and read back as JSON (tuples become lists)."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def via_json(value):
    """plain_json with the key names of the reference outputs."""
    return old_view(plain_json(value))


MESSAGES: dict[str, str] = {m["id"]: m["text"] for m in load("messages.json")}

GUARD = Guard([RulesDetector(labels=LEAD_LABELS)])

#: Para los mensajes que las reglas solas no marcan: un engaño dirigido a una persona.
HAND_VERDICT = Verdict(
    decision="revisar",
    ai_instructions=False,
    people_deception=True,
    tricks=("autoridad", "distraccion_urgencia"),
    evidence=(),
    notice="Parece un engaño dirigido a una persona.",
)


def verdict_of(id_: str) -> Verdict:
    """El veredicto de las reglas, o el armado a mano si las reglas no lo marcan."""
    verdict = GUARD.check(MESSAGES[id_])
    return verdict if verdict.decision == "revisar" else HAND_VERDICT


def cli(*argv: str) -> dict:
    output, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
        try:
            code = cli_main(list(argv))
        except SystemExit as exit_info:  # --version y los errores de argparse salen así
            code = exit_info.code
    return {"exit": code, "stdout": output.getvalue(), "stderr": error.getvalue()}


def demo_mails():
    """Los cinco correos ficticios de ejemplos/enviar_pruebas.py."""
    send_script = runpy.run_path(str(EXAMPLES / "send_test_emails.py"))
    return send_script["build_messages"]("pruebas@example.com", "agente@example.org")


class FakeProvider:
    """Un modelo de mentira que anota lo que recibe."""

    name = "falso"

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def respond_json(self, *, system, message, schema):
        self.calls.append({"sistema": system, "mensaje": message, "esquema": schema})
        if self.error:
            raise self.error
        return self.response

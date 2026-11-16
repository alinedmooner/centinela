"""Helpers to compare what Centinela does today with the reference outputs.

The reference outputs are in tests/golden/main_9810607/. They came from the code of
main@9810607, before the project moved to English (see tests/golden/README.md). They use
the Spanish vocabulary and the Spanish texts, so the tests run the current code with
``lang="es"`` and look at its output through ``old_view``, which maps the English names and
values back to the old ones.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
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
    """JSON with the key order: the order of the schema keys is also seen by the model."""
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
    "card": "tarjeta",
}

#: Keys that did not exist in main@9810607; the reference outputs do not have them.
NEW_KEYS = {"lang"}


#: Values that changed, by the (new) key they appear under.
OLD_VALUES = {
    "decision": {"allow": "permitir", "review": "revisar"},
    "reason": {
        "model": "modelo",
        "guard": "guardia",
        "invalid_response": "respuesta_invalida",
        "refusal": "rechazo",
    },
    "state": {
        "blocked": "bloqueado",
        "released": "liberado",
        "awaiting_second_person": "espera_segunda_persona",
        "escalated": "escalado",
    },
    "actions": {
        "is_fraud": "es_fraude",
        "is_legitimate": "es_legitimo",
        "not_sure": "no_estoy_seguro",
    },
    "asks": {
        "open_link": "entrar a un enlace",
        "give_credentials": "dar una clave o datos personales",
        "send_money": "pagar o transferir dinero",
        "open_file": "descargar o abrir un archivo",
        "contact": "llamar o escribir a un contacto",
        "instruct_ai": "darle órdenes al asistente de IA",
    },
    "pressure": {"urgency": "urgencia", "threat": "amenaza", "prize_or_offer": "premio u oferta"},
    "detector": {"rules": "reglas", "local+translation": "local+traduccion"},
    "label": {"human_review": "revision_humana"},
    "model_label": {"human_review": "revision_humana"},
}

#: Rule ids in the evidence lines, and the phrases of the hidden-text signals.
RULE_IDS = {
    "override_instructions": "anular_instrucciones",
    "addressed_to_ai": "dirigido_a_la_ia",
    "forced_label": "etiqueta_forzada",
    "fake_system": "sistema_falso",
    "role_change": "cambio_de_rol",
    "canned_answer": "respuesta_prefabricada",
    "request_internal_instructions": "pedir_instrucciones_internas",
    "names_a_label": "nombra_una_etiqueta",
    "hidden_text": "texto_oculto",
}
HIDDEN_TEXT_PHRASES = {
    "invisible characters that hide a message": "caracteres invisibles que esconden un mensaje",
    "zero-width characters that split words": "caracteres de ancho cero que parten palabras",
}


#: Messages of the LLM detector (an evidence line and the reasons it fails), in English now.
DETECTOR_PHRASES = {
    "the model refused to check the message": "el modelo se negó a revisar el mensaje",
    "the model did not return a valid answer": "el modelo no devolvió una respuesta válida",
}


def old_evidence(line: str) -> str:
    """An evidence line (or a detector error) with the Spanish wording of main@9810607."""
    rule, sep, rest = line.partition(": ")
    if rule in RULE_IDS:
        rest = HIDDEN_TEXT_PHRASES.get(rest, rest)
        return RULE_IDS[rule] + sep + rest
    if line in DETECTOR_PHRASES:
        return DETECTOR_PHRASES[line]
    return re.sub(
        r"^only the first (\d+) characters were checked$",
        r"solo se revisaron los primeros \1 caracteres",
        line,
    )


def old_text(text: str) -> str:
    """The output of ``check`` as text, with the old rule ids in the evidence lines."""
    return "\n".join(
        "  - " + old_evidence(line[4:]) if line.startswith("  - ") else line
        for line in text.split("\n")
    )


def old_view(value, key: str | None = None):
    """The value with the key names and values that the reference outputs use."""
    if isinstance(value, dict):
        return {OLD_KEYS.get(k, k): old_view(v, k) for k, v in value.items() if k not in NEW_KEYS}
    if isinstance(value, (list, tuple)):
        return [old_view(v, key) for v in value]
    if isinstance(value, str):
        if key in ("evidence", "error"):
            return old_evidence(value)
        return OLD_VALUES.get(key, {}).get(value, value)
    return value


def plain_json(value):
    """What the value gives when written and read back as JSON (tuples become lists)."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def via_json(value):
    """plain_json with the key names of the reference outputs."""
    return old_view(plain_json(value))


MESSAGES: dict[str, str] = {m["id"]: m["text"] for m in load("messages.json")}

GUARD = Guard([RulesDetector(labels=LEAD_LABELS)], lang="es")

#: For the messages the rules alone do not flag: a deception aimed at a person.
HAND_VERDICT = Verdict(
    decision="review",
    ai_instructions=False,
    people_deception=True,
    tricks=("autoridad", "distraccion_urgencia"),
    evidence=(),
    notice="Parece un engaño dirigido a una persona.",
    lang="es",
)


def verdict_of(id_: str) -> Verdict:
    """The verdict of the rules, or the hand-made one if the rules do not flag the message."""
    verdict = GUARD.check(MESSAGES[id_])
    return verdict if verdict.decision == "review" else HAND_VERDICT


def cli(*argv: str, lang: str = "es") -> dict:
    """Run the command line, in Spanish unless ``lang`` says otherwise."""
    argv = (*argv, "--lang", lang)
    output, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
        try:
            code = cli_main(list(argv))
        except SystemExit as exit_info:  # --version and argparse errors exit like this
            code = exit_info.code
    return {"exit": code, "stdout": output.getvalue(), "stderr": error.getvalue()}


def demo_mails():
    """The five fictional emails of examples/send_test_emails.py."""
    send_script = runpy.run_path(str(EXAMPLES / "send_test_emails.py"))
    return send_script["build_messages"]("pruebas@example.com", "agente@example.org")


class FakeProvider:
    """A fake model that records what it receives."""

    name = "falso"  # Spanish on purpose: the reference outputs record it as "llm:falso"

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def respond_json(self, *, system, message, schema):
        # Spanish keys on purpose: the reference outputs use them.
        self.calls.append({"sistema": system, "mensaje": message, "esquema": schema})
        if self.error:
            raise self.error
        return self.response

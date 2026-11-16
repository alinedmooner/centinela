"""The on-disk vocabulary of the saved results (format v1), in one place.

The records in ``data/`` and ``results/`` were measured with Spanish names and values, and they
are measurement records: they do not change. Everything that reads or writes them goes through
this module, so the rest of the code can use English names and the library's English values.

- Reading: the tables show the records through the maps below (``tables.py``).
- Writing: a new run writes v1, so a rerun can be compared with the saved records.

An unknown value is an error, not something to skip: a result that silently drops rows is a
wrong result.
"""

from __future__ import annotations

#: Detector -> the file it was saved in (``results/filter/<split>/<detector>.jsonl``).
DETECTORS = ("llamafirewall", "local", "local_traduccion", "reglas", "claude")
#: The detectors each split must have. ``dev`` was only used to write and check the rules.
EXPECTED_DETECTORS = {
    "test": frozenset(DETECTORS),
    "dev": frozenset({"llamafirewall", "reglas"}),
}

#: Defenses of the lead-bot test (the part after ``__`` in ``<model>__<defense>.jsonl``).
DEFENSES = ("ninguna", "prompt", "centinela", "centinela_juez")

#: Groups of the filter test cases.
GROUPS = (
    "inyeccion_publica",
    "mensaje_normal",
    "ataque_a_leads",
    "lead_normal",
    "correo_legitimo_real",
)

#: What the code assigns when a person must decide, as the records write it. The library's
#: ``HUMAN_REVIEW`` is ``human_review``.
HUMAN_REVIEW = "revision_humana"

#: What a message asks for, as ``results/review/spaphish.jsonl`` writes it, and its id in the
#: library (``centinela.review.ASK_IDS``).
ASKS = {
    "entrar a un enlace": "open_link",
    "dar una clave o datos personales": "give_credentials",
    "pagar o transferir dinero": "send_money",
    "descargar o abrir un archivo": "open_file",
    "llamar o escribir a un contacto": "contact",
    "darle órdenes al asistente de IA": "instruct_ai",
}
#: How a message pressures, the same way.
PRESSURES = {"urgencia": "urgency", "amenaza": "threat", "premio u oferta": "prize_or_offer"}

#: Names of Inspect's task arguments, which the raw logs saved in Spanish.
TASK_ARGS = {"defense": "defensa", "split": "particion", "effort": "esfuerzo"}


class UnknownValue(ValueError):
    """A value that is not part of the v1 vocabulary."""


def _lookup(kind: str, value: str, valid) -> str:
    if value not in valid:
        raise UnknownValue(f"unknown {kind}: {value!r}; expected one of {sorted(valid)}")
    return value


def detector(value: str) -> str:
    return _lookup("detector", value, DETECTORS)


def defense(value: str) -> str:
    return _lookup("defense", value, DEFENSES)


def group(value: str) -> str:
    return _lookup("group", value, GROUPS)


def ask_id(phrase: str) -> str:
    """The id of an ask written as in a v1 record."""
    return ASKS[_lookup("ask", phrase, ASKS)]


def pressure_id(phrase: str) -> str:
    return PRESSURES[_lookup("pressure", phrase, PRESSURES)]


def ask_phrase(identifier: str) -> str:
    """The v1 phrase of an ask id, to write a record that matches the saved ones."""
    by_id = {v: k for k, v in ASKS.items()}
    return by_id[_lookup("ask id", identifier, by_id)]


def pressure_phrase(identifier: str) -> str:
    by_id = {v: k for k, v in PRESSURES.items()}
    return by_id[_lookup("pressure id", identifier, by_id)]


def task_arg(task_args: dict, name: str, default=None):
    """An Inspect task argument by its English name, or by the Spanish one old logs use."""
    if name in task_args:
        return task_args[name]
    return task_args.get(TASK_ARGS[name], default)

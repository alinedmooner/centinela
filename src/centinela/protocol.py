"""Everything a language model sees, in one place.

These texts are Spanish on purpose, and they are frozen: every saved measurement in
``results/`` was made with exactly these bytes, and the tests in ``tests/test_golden_protocol.py``
compare them with the ones of ``main@9810607``. Translating any of them would invalidate about
4,700 saved model calls, so a translated variant must be a new experiment in its own folder.

- The reviewer's instructions and JSON schema (``REVIEWER_INSTRUCTIONS``, ``REVIEWER_SCHEMA``).
  The schema keys (``ordenes_para_ia``, ``engano_a_personas``, ``trucos``, ``motivo``) and the
  ids of the persuasion tricks are part of the protocol.
- The classifier's instructions and schema (``classifier_instructions``, ``classifier_schema``),
  and the definitions of the example labels (``LEAD_LABELS``). Each business writes its own.
- The wrapper marker ``<mensaje_cliente id="...">`` (``wrap``). The rules detector also catches a
  message that tries to close it, which is why the marker name must not change.
- The mail headers (``De:``, ``Asunto:``, ``Adjuntos:``) and the markers for hidden HTML text
  that ``text_to_check`` writes, and the text that replaces a held email (``safe_inbox``).

The words and patterns the rules detector looks for are Spanish too, but they are not text a
model sees: they are behavior, frozen in ``detectors/rules.py``.
"""

from centinela._markers import wrap
from centinela.classifier import instructions as classifier_instructions
from centinela.classifier import schema as classifier_schema
from centinela.detectors.llm import INSTRUCTIONS as REVIEWER_INSTRUCTIONS
from centinela.detectors.llm import SCHEMA as REVIEWER_SCHEMA
from centinela.labels import LEAD_LABELS

__all__ = [
    "LEAD_LABELS",
    "REVIEWER_INSTRUCTIONS",
    "REVIEWER_SCHEMA",
    "classifier_instructions",
    "classifier_schema",
    "wrap",
]

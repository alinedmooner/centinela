"""Detector con un modelo abierto que corre en la propia máquina.

Necesita el extra ``local`` (``pip install "centinela-ia[local]"``). El texto no sale del
equipo. El modelo por defecto, ``protectai/deberta-v3-base-prompt-injection-v2``, fue
entrenado para inglés: con ``traducir=True`` el mensaje se traduce antes al inglés con
``Helsinki-NLP/opus-mt-es-en``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from centinela.verdict import Finding

MODEL = "protectai/deberta-v3-base-prompt-injection-v2"
TRANSLATION_MODEL = "Helsinki-NLP/opus-mt-es-en"

_SENTENCES = re.compile(r"(?<=[.!?\n])\s+")


def chunks(text: str, length: int = 1500, overlap: int = 200) -> list[str]:
    """Parte un texto largo en ventanas que se solapan, para no perder nada al recortar."""
    if len(text) <= length:
        return [text]
    step = length - overlap
    return [text[i : i + length] for i in range(0, max(len(text) - overlap, 1), step)]


def sentences(text: str, length: int = 400) -> list[str]:
    """Agrupa las frases de un texto en bloques cortos, que es lo que traduce bien el modelo."""
    blocks: list[str] = []
    actual = ""
    for sentence in _SENTENCES.split(text):
        while len(sentence) > length:
            blocks.append(sentence[:length])
            sentence = sentence[length:]
        if actual and len(actual) + len(sentence) + 1 > length:
            blocks.append(actual)
            actual = sentence
        else:
            actual = f"{actual} {sentence}".strip()
    if actual:
        blocks.append(actual)
    return blocks or [""]


class LocalDetector:
    """Detector de órdenes para la IA con un modelo de clasificación local.

    ``clasificar`` y ``traducir_textos`` permiten inyectar funciones propias (por ejemplo
    en pruebas). Si no se pasan, se cargan los modelos de Hugging Face al primer uso.
    """

    def __init__(
        self,
        model: str = MODEL,
        *,
        threshold: float = 0.5,
        safe_label: str = "SAFE",
        translate: bool = False,
        translation_model: str = TRANSLATION_MODEL,
        classify: Callable[[Sequence[str]], list[float]] | None = None,
        translate_texts: Callable[[Sequence[str]], list[str]] | None = None,
    ):
        self.model = model
        self.threshold = threshold
        self.safe_label = safe_label
        self.translate = translate
        self.translation_model = translation_model
        self._classify = classify
        self._translate_texts = translate_texts
        self.name = "local+traduccion" if translate else "local"

    def check(self, text: str) -> Finding:
        if self.translate:
            text = " ".join(self._translation()(sentences(text)))
        scores = self._classification()(chunks(text))
        score = max(scores) if scores else 0.0
        flagged = score >= self.threshold
        evidence = (f"el modelo local da {score:.2f} de probabilidad de inyección",)
        return Finding(self.name, ai_instructions=flagged, evidence=evidence if flagged else ())

    def _classification(self) -> Callable[[Sequence[str]], list[float]]:
        if self._classify is None:
            from transformers import pipeline

            model = pipeline(
                "text-classification", model=self.model, truncation=True, max_length=512
            )

            def classify(texts: Sequence[str]) -> list[float]:
                outputs = model(list(texts), batch_size=8)
                return [
                    1 - s["score"] if s["label"] == self.safe_label else s["score"] for s in outputs
                ]

            self._classify = classify
        return self._classify

    def _translation(self) -> Callable[[Sequence[str]], list[str]]:
        if self._translate_texts is None:
            from transformers import MarianMTModel, MarianTokenizer

            tokenizer = MarianTokenizer.from_pretrained(self.translation_model)
            model = MarianMTModel.from_pretrained(self.translation_model)

            def translate_texts(texts: Sequence[str]) -> list[str]:
                output: list[str] = []
                for i in range(0, len(texts), 16):
                    batch = tokenizer(
                        list(texts[i : i + 16]),
                        return_tensors="pt",
                        padding=True,
                        truncation=True,
                        max_length=256,
                    )
                    generated = model.generate(**batch, num_beams=1, max_new_tokens=256)
                    output.extend(tokenizer.batch_decode(generated, skip_special_tokens=True))
                return output

            self._translate_texts = translate_texts
        return self._translate_texts

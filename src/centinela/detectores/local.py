"""Detector con un modelo abierto que corre en la propia máquina.

Necesita el extra ``local`` (``pip install "centinela-ia[local]"``). El texto no sale del
equipo. El modelo por defecto, ``protectai/deberta-v3-base-prompt-injection-v2``, fue
entrenado para inglés: con ``traducir=True`` el mensaje se traduce antes al inglés con
``Helsinki-NLP/opus-mt-es-en``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from centinela.tipos import Hallazgo

MODELO = "protectai/deberta-v3-base-prompt-injection-v2"
MODELO_TRADUCCION = "Helsinki-NLP/opus-mt-es-en"

_FRASES = re.compile(r"(?<=[.!?\n])\s+")


def trozos(texto: str, largo: int = 1500, solape: int = 200) -> list[str]:
    """Parte un texto largo en ventanas que se solapan, para no perder nada al recortar."""
    if len(texto) <= largo:
        return [texto]
    paso = largo - solape
    return [texto[i : i + largo] for i in range(0, max(len(texto) - solape, 1), paso)]


def frases(texto: str, largo: int = 400) -> list[str]:
    """Agrupa las frases de un texto en bloques cortos, que es lo que traduce bien el modelo."""
    bloques: list[str] = []
    actual = ""
    for frase in _FRASES.split(texto):
        while len(frase) > largo:
            bloques.append(frase[:largo])
            frase = frase[largo:]
        if actual and len(actual) + len(frase) + 1 > largo:
            bloques.append(actual)
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if actual:
        bloques.append(actual)
    return bloques or [""]


class DetectorLocal:
    """Detector de órdenes para la IA con un modelo de clasificación local.

    ``clasificar`` y ``traducir_textos`` permiten inyectar funciones propias (por ejemplo
    en pruebas). Si no se pasan, se cargan los modelos de Hugging Face al primer uso.
    """

    def __init__(
        self,
        modelo: str = MODELO,
        *,
        umbral: float = 0.5,
        etiqueta_segura: str = "SAFE",
        traducir: bool = False,
        modelo_traduccion: str = MODELO_TRADUCCION,
        clasificar: Callable[[Sequence[str]], list[float]] | None = None,
        traducir_textos: Callable[[Sequence[str]], list[str]] | None = None,
    ):
        self.modelo = modelo
        self.umbral = umbral
        self.etiqueta_segura = etiqueta_segura
        self.traducir = traducir
        self.modelo_traduccion = modelo_traduccion
        self._clasificar = clasificar
        self._traducir_textos = traducir_textos
        self.nombre = "local+traduccion" if traducir else "local"

    def revisar(self, texto: str) -> Hallazgo:
        if self.traducir:
            texto = " ".join(self._traduccion()(frases(texto)))
        puntajes = self._clasificacion()(trozos(texto))
        puntaje = max(puntajes) if puntajes else 0.0
        marcado = puntaje >= self.umbral
        evidencias = (f"el modelo local da {puntaje:.2f} de probabilidad de inyección",)
        return Hallazgo(
            self.nombre, ordenes_para_ia=marcado, evidencias=evidencias if marcado else ()
        )

    def _clasificacion(self) -> Callable[[Sequence[str]], list[float]]:
        if self._clasificar is None:
            from transformers import pipeline

            modelo = pipeline(
                "text-classification", model=self.modelo, truncation=True, max_length=512
            )

            def clasificar(textos: Sequence[str]) -> list[float]:
                salidas = modelo(list(textos), batch_size=8)
                return [
                    1 - s["score"] if s["label"] == self.etiqueta_segura else s["score"]
                    for s in salidas
                ]

            self._clasificar = clasificar
        return self._clasificar

    def _traduccion(self) -> Callable[[Sequence[str]], list[str]]:
        if self._traducir_textos is None:
            from transformers import MarianMTModel, MarianTokenizer

            tokenizador = MarianTokenizer.from_pretrained(self.modelo_traduccion)
            modelo = MarianMTModel.from_pretrained(self.modelo_traduccion)

            def traducir_textos(textos: Sequence[str]) -> list[str]:
                salida: list[str] = []
                for i in range(0, len(textos), 16):
                    lote = tokenizador(
                        list(textos[i : i + 16]),
                        return_tensors="pt",
                        padding=True,
                        truncation=True,
                        max_length=256,
                    )
                    generado = modelo.generate(**lote, num_beams=1, max_new_tokens=256)
                    salida.extend(tokenizador.batch_decode(generado, skip_special_tokens=True))
                return salida

            self._traducir_textos = traducir_textos
        return self._traducir_textos

"""Detectores intercambiables: reglas (sin internet), modelo local y modelo por API."""

from centinela.detectores.base import Detector
from centinela.detectores.llm import DetectorLLM
from centinela.detectores.local import DetectorLocal
from centinela.detectores.reglas import DetectorReglas

__all__ = ["Detector", "DetectorLLM", "DetectorLocal", "DetectorReglas"]

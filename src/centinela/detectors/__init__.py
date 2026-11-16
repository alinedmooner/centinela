"""Detectores intercambiables: reglas (sin internet), modelo local y modelo por API."""

from centinela.detectors.base import Detector
from centinela.detectors.llm import LLMDetector
from centinela.detectors.local import LocalDetector
from centinela.detectors.rules import RulesDetector

__all__ = ["Detector", "LLMDetector", "LocalDetector", "RulesDetector"]

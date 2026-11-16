"""Interchangeable detectors: rules (no internet), a local model and a model via an API."""

from centinela.detectors.base import Detector
from centinela.detectors.llm import LLMDetector
from centinela.detectors.local import LocalDetector
from centinela.detectors.rules import RulesDetector

__all__ = ["Detector", "LLMDetector", "LocalDetector", "RulesDetector"]

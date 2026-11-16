"""Minimal interface to connect any language model."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ModelResponse:
    """What the model returned to a request with a schema."""

    #: The JSON the model returned, or ``None`` if it did not return valid JSON.
    data: dict | None
    #: The model refused to answer (for example, because of its safety filters).
    refusal: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderError(RuntimeError):
    """The provider could not answer (network, limits, credentials).

    ``code`` says why (``rate_limit``, ``api_error``, ``connection``, ``missing_sdk``,
    ``missing_key``) and ``details`` holds what the message needs (``status``, ``hint``,
    ``variable``). The message is English; the command line translates it by code.
    """

    def __init__(self, message: str, code: str = "error", **details: object):
        super().__init__(message)
        self.code = code
        self.details = details


@runtime_checkable
class Provider(Protocol):
    """A model that answers with JSON that meets a schema.

    To use another provider (OpenAI, a local model) a class with a ``name`` attribute and
    this method is enough.
    """

    name: str

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse: ...


def json_from_text(text: str) -> dict | None:
    """The JSON object of an answer, even if it comes inside code-block fences."""
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def is_error_from(error: Exception, *packages: str) -> bool:
    """The error comes from one of these packages (the provider SDK or its HTTP client)."""
    return type(error).__module__.split(".")[0] in packages

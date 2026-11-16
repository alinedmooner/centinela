"""Provider for the Google models (Gemini and Gemma), with the official google-genai SDK.

It needs the ``google`` extra (``pip install "centinela-ia[google]"``) and a Google AI Studio
key in ``GOOGLE_API_KEY`` (``GEMINI_API_KEY`` also works).
"""

from __future__ import annotations

import os

from centinela.providers.base import ModelResponse, ProviderError, is_error_from, json_from_text

DEFAULT_MODEL = "gemini-3.5-flash-lite"
KEY_VARIABLES = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_STUDIO_API_KEY")
#: Finish reasons that mean Google blocked the answer.
_BLOCKING_FINISH_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def _name(value) -> str | None:
    return None if value is None else str(getattr(value, "name", value))


class GoogleProvider:
    """Asks a Google model for JSON that meets a schema.

    ``reasoning`` is the reasoning level of Gemini 3 or later. It is ``"minimal"`` because
    checking short messages needs no more. With ``None`` it is not sent, for models that do
    not accept levels (Gemma, Gemini 2.5).
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        reasoning: str | None = "minimal",
        max_tokens: int = 1024,
        key: str | None = None,
        client=None,
    ):
        if client is None:
            try:
                from google import genai
            except ImportError as error:  # pragma: no cover - depends on the installation
                raise ProviderError(
                    'The Google SDK is missing. Install the extra: pip install "centinela-ia[google]"',
                    code="missing_sdk",
                    hint='pip install "centinela-ia[google]"',
                ) from error
            key = key or next((os.environ[v] for v in KEY_VARIABLES if os.environ.get(v)), None)
            if not key:
                raise ProviderError(
                    "The Google key is missing: set GOOGLE_API_KEY.",
                    code="missing_key",
                    variable="GOOGLE_API_KEY",
                )
            client = genai.Client(api_key=key)
        self.client = client
        self.model = model
        self.reasoning = reasoning
        self.max_tokens = max_tokens
        self.name = f"google/{model}"

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse:
        config: dict = {
            "system_instruction": system,
            "max_output_tokens": self.max_tokens,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        }
        if self.reasoning:
            config["thinking_config"] = {"thinking_level": self.reasoning}
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=message, config=config
            )
        except Exception as error:
            if not is_error_from(error, "google", "httpx"):
                raise
            code = getattr(error, "code", None)
            if code == 429:
                raise ProviderError("The API rate limit was reached.", code="rate_limit") from error
            if isinstance(code, int):
                raise ProviderError(
                    f"The API answered with error {code}.", code="api_error", status=code
                ) from error
            raise ProviderError("Could not connect to the API.", code="connection") from error

        usage = getattr(response, "usage_metadata", None)
        input_count = getattr(usage, "prompt_token_count", 0) or 0
        output = (getattr(usage, "candidates_token_count", 0) or 0) + (
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        candidates = getattr(response, "candidates", None) or []
        finish_reason = _name(getattr(candidates[0], "finish_reason", None)) if candidates else None
        block = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        if block or finish_reason in _BLOCKING_FINISH_REASONS:
            return ModelResponse(None, refusal=True, input_tokens=input_count, output_tokens=output)
        return ModelResponse(
            json_from_text(getattr(response, "text", None) or ""),
            input_tokens=input_count,
            output_tokens=output,
        )

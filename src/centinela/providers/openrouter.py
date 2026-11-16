"""Provider for hundreds of models, open and closed, through OpenRouter.

OpenRouter's API is compatible with OpenAI's, so the official ``openai`` SDK is used. It needs
the ``openrouter`` extra (``pip install "centinela-ia[openrouter]"``) and the
``OPENROUTER_API_KEY`` variable.
"""

from __future__ import annotations

import os

from centinela.providers.base import ModelResponse, ProviderError, is_error_from, json_from_text

URL = "https://openrouter.ai/api/v1"
#: A small open model (Gemma 4, 4 billion active parameters).
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"
KEY_VARIABLES = ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY")


class OpenRouterProvider:
    """Asks an OpenRouter model for JSON that meets a schema.

    It sends the schema as structured output. If the model does not support it and answers
    with text, the JSON is looked for in the text; if there is none, the guard sends the
    message to human review.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        max_tokens: int = 1024,
        key: str | None = None,
        client=None,
    ):
        if client is None:
            try:
                import openai
            except ImportError as error:  # pragma: no cover - depends on the installation
                raise ProviderError(
                    'The OpenAI SDK is missing. Install the extra: pip install "centinela-ia[openrouter]"',
                    code="missing_sdk",
                    hint='pip install "centinela-ia[openrouter]"',
                ) from error
            key = key or next((os.environ[v] for v in KEY_VARIABLES if os.environ.get(v)), None)
            if not key:
                raise ProviderError(
                    "The OpenRouter key is missing: set OPENROUTER_API_KEY.",
                    code="missing_key",
                    variable="OPENROUTER_API_KEY",
                )
            client = openai.OpenAI(base_url=URL, api_key=key)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"openrouter/{model}"

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "respuesta", "strict": True, "schema": schema},
                },
            )
        except Exception as error:
            if not is_error_from(error, "openai", "httpx"):
                raise
            code = getattr(error, "status_code", None)
            if code == 429:
                raise ProviderError("The API rate limit was reached.", code="rate_limit") from error
            if isinstance(code, int):
                raise ProviderError(
                    f"The API answered with error {code}.", code="api_error", status=code
                ) from error
            raise ProviderError("Could not connect to the API.", code="connection") from error

        usage = getattr(response, "usage", None)
        input_count = getattr(usage, "prompt_tokens", 0) or 0
        output = getattr(usage, "completion_tokens", 0) or 0
        options = getattr(response, "choices", None) or []
        if not options:
            return ModelResponse(None, input_tokens=input_count, output_tokens=output)
        model_message = options[0].message
        if options[0].finish_reason == "content_filter" or getattr(model_message, "refusal", None):
            return ModelResponse(None, refusal=True, input_tokens=input_count, output_tokens=output)
        return ModelResponse(
            json_from_text(model_message.content or ""),
            input_tokens=input_count,
            output_tokens=output,
        )

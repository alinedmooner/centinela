"""Provider for the Claude models, with the official Anthropic SDK.

It needs the ``llm`` extra (``pip install "centinela-ia[llm]"``) and the ``ANTHROPIC_API_KEY``
variable.
"""

from __future__ import annotations

import json

from centinela.providers.base import ModelResponse, ProviderError

DEFAULT_MODEL = "claude-haiku-5-5"


class AnthropicProvider:
    """Asks Claude for JSON that meets a schema.

    The effort is ``low`` because classifying and checking short messages needs no more.
    ``temperature`` is not sent: current models do not accept it.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        effort: str = "low",
        max_tokens: int = 1024,
        client=None,
    ):
        if client is None:
            try:
                import anthropic
            except ImportError as error:  # pragma: no cover - depends on the installation
                raise ProviderError(
                    'The Anthropic SDK is missing. Install the extra: pip install "centinela-ia[llm]"',
                    code="missing_sdk",
                    hint='pip install "centinela-ia[llm]"',
                ) from error
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.name = f"anthropic/{model}"

    def respond_json(self, *, system: str, message: str, schema: dict) -> ModelResponse:
        import anthropic

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": message}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except anthropic.RateLimitError as error:
            raise ProviderError("The API rate limit was reached.", code="rate_limit") from error
        except anthropic.APIStatusError as error:
            raise ProviderError(
                f"The API answered with error {error.status_code}.",
                code="api_error",
                status=error.status_code,
            ) from error
        except anthropic.APIConnectionError as error:
            raise ProviderError("Could not connect to the API.", code="connection") from error

        usage = response.usage
        if response.stop_reason == "refusal":
            return ModelResponse(
                None,
                refusal=True,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )

        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            data = None
        return ModelResponse(
            data, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens
        )

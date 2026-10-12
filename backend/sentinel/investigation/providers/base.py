"""The provider boundary: one prompt in, one text reply out.

Everything provider-specific (URLs, auth, payload shape, error codes) stays behind this
interface, so replacing a provider never touches the service, the validator or the UI.
"""

from typing import Protocol


class LlmProvider(Protocol):
    name: str  # "mock" | "openai_compatible"
    model: str

    def complete(self, prompt: str) -> str:
        """Return the model's reply text. Raise ProviderError when no reply was obtained."""
        ...


class ProviderError(Exception):
    """No usable reply: the provider was unreachable, refused the call or answered badly.

    Messages never contain credentials. Codes: timeout, unreachable, auth, rate_limited,
    provider_error, bad_response.
    """

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

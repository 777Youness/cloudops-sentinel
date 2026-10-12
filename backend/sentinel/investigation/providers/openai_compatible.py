"""One HTTP call to an OpenAI-compatible Chat Completions endpoint (ADR 0015).

Works with Ollama (http://localhost:11434/v1, no key), Groq, Mistral and others that expose
POST {base_url}/chat/completions. It does not rely on `response_format`, whose support
differs between providers: the validator checks the reply whatever the provider does.

The API key is sent in the Authorization header and nowhere else. It is never logged and
never included in an error message (responses are scrubbed in case a provider echoes it).
"""

import httpx

from sentinel.investigation.providers.base import ProviderError

SYSTEM_MESSAGE = "You reply with one JSON object and nothing else."


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float = 60.0,
        max_tokens: int = 1500,
        transport: httpx.BaseTransport | None = None,  # tests pass httpx.MockTransport
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._where = self._describe(self._url)
        self._api_key = api_key
        self._secrets = self._secret_values(self._url, api_key)
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._transport = transport

    @staticmethod
    def _describe(url: str) -> str:
        """Scheme, host and port only, for messages. The path, query and userinfo are left
        out: some providers take the key as a query parameter or in user:password@."""
        try:
            parsed = httpx.URL(url)
        except (httpx.InvalidURL, ValueError, TypeError):
            return "the configured SENTINEL_LLM_BASE_URL"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.host}{port}"

    @staticmethod
    def _secret_values(url: str, api_key: str | None) -> list[str]:
        """Everything that may be a credential: the key, and the URL's password and query
        values (a provider's error body can echo the request URL)."""
        values = [api_key] if api_key else []
        try:
            parsed = httpx.URL(url)
            if parsed.password:
                values.append(parsed.password)
            values += [v for _, v in parsed.params.multi_items() if len(v) >= 4]
        except (httpx.InvalidURL, ValueError, TypeError):
            pass
        return sorted(set(values), key=len, reverse=True)  # longest first

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "[redacted]")
        return text[:200]

    def complete(self, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": self._max_tokens,
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "timeout",
                f"The provider did not answer within {self._timeout:g} s.",
                hint="Local models can be slow: raise SENTINEL_LLM_TIMEOUT_SECONDS or use a "
                "smaller model.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "unreachable",
                f"Could not reach the provider at {self._where}.",
                hint="Check SENTINEL_LLM_BASE_URL. For Ollama: is `ollama serve` running?",
            ) from exc

        status = response.status_code
        if status in (401, 403):
            raise ProviderError(
                "auth",
                f"The provider refused the credentials (HTTP {status}).",
                hint="Check SENTINEL_LLM_API_KEY.",
            )
        if status == 429:
            raise ProviderError(
                "rate_limited",
                "The provider's rate limit was reached (HTTP 429).",
                hint="Wait and retry, or check the plan's limits in the provider console.",
            )
        if status >= 400:
            raise ProviderError(
                "provider_error",
                f"The provider answered HTTP {status}: {self._scrub(response.text)}",
                hint="Check SENTINEL_LLM_MODEL and the provider's status page.",
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "bad_response", "The provider's response has no message content."
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("bad_response", "The provider returned an empty message.")
        return content

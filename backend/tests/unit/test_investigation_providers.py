"""Providers: the deterministic mock, and the OpenAI-compatible provider over
httpx.MockTransport. No test touches the network."""

import json
from datetime import timedelta
from itertools import count

import httpx
import pytest

from sentinel.collectors.simulated import SimulatedSource, load_scenarios
from sentinel.config import Settings
from sentinel.detection import engine
from sentinel.investigation.bundle import build_bundle, fact_ids
from sentinel.investigation.prompt import build_prompt
from sentinel.investigation.providers.base import ProviderError
from sentinel.investigation.providers.mock import MockProvider
from sentinel.investigation.providers.openai_compatible import OpenAICompatibleProvider
from sentinel.investigation.validator import validate_output

SECRET = "fake-key-for-tests"  # obviously fake: secret scanners must not flag it


def _scenario_incidents(clock):
    now = clock.now()
    scenarios = load_scenarios(Settings().scenarios_dir)
    snapshot = SimulatedSource(scenarios, clock, region="eu-west-3").collect(
        now - timedelta(hours=3), now
    )
    ids = count(1)
    return engine.evaluate(snapshot, [], now, lambda: f"INC-{next(ids):04d}").opened


# --- mock ------------------------------------------------------------------------------


def test_mock_output_passes_the_validator_for_every_scenario_incident(clock):
    incidents = _scenario_incidents(clock)
    assert incidents
    for incident in incidents:
        bundle = build_bundle(incident)
        findings = validate_output(MockProvider().complete(build_prompt(bundle)), fact_ids(bundle))
        assert findings.hypotheses, incident.id
        assert "mock provider" in findings.limitations[0]


def test_mock_is_deterministic(clock):
    incident = _scenario_incidents(clock)[0]
    prompt = build_prompt(build_bundle(incident))
    assert MockProvider().complete(prompt) == MockProvider().complete(prompt)


def test_mock_only_suggests_a_deployment_that_happened_before_the_breach(clock):
    by_resource = {i.resource_id: i for i in _scenario_incidents(clock)}
    for resource_id, expect_deploy in (("sim-escalation", True), ("sim-memory-pressure", False)):
        prompt = build_prompt(build_bundle(by_resource[resource_id]))
        reply = json.loads(MockProvider().complete(prompt))
        mentions = any("deployed" in h["statement"] for h in reply["hypotheses"])
        assert mentions == expect_deploy, resource_id


# --- OpenAI-compatible -----------------------------------------------------------------


def _provider(handler, api_key=SECRET, base_url="http://llm.test/v1/"):
    return OpenAICompatibleProvider(
        base_url=base_url,
        model="test-model",
        api_key=api_key,
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )


def _chat(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_sends_one_chat_completion_and_returns_the_content():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return _chat('{"summary": "ok"}')

    assert _provider(handler).complete("PROMPT") == '{"summary": "ok"}'
    assert seen["url"] == "http://llm.test/v1/chat/completions"  # trailing slash handled
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["messages"][-1] == {"role": "user", "content": "PROMPT"}
    assert "response_format" not in seen["body"]  # not portable across providers


def test_no_authorization_header_without_a_key():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return _chat("{}")

    _provider(handler, api_key=None).complete("PROMPT")
    assert seen["auth"] is None  # Ollama needs no key


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(401, json={"error": "invalid key"}), "auth"),
        (httpx.Response(403, json={"error": "forbidden"}), "auth"),
        (httpx.Response(429, json={"error": "slow down"}), "rate_limited"),
        (httpx.Response(500, text="internal error"), "provider_error"),
        (httpx.Response(404, text="model not found"), "provider_error"),
        (httpx.Response(200, text="not json"), "bad_response"),
        (httpx.Response(200, json={"choices": []}), "bad_response"),
        (_chat("   "), "bad_response"),
    ],
)
def test_http_failures_become_provider_errors(response, code):
    with pytest.raises(ProviderError) as info:
        _provider(lambda request: response).complete("PROMPT")
    assert info.value.code == code


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as info:
        _provider(handler).complete("PROMPT")
    assert info.value.code == "timeout"


def test_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderError) as info:
        _provider(handler).complete("PROMPT")
    assert info.value.code == "unreachable"
    assert "ollama serve" in (info.value.hint or "")


def test_the_api_key_never_appears_in_an_error():
    # A provider that echoes the Authorization header back in its error body.
    def handler(request):
        return httpx.Response(400, text=f"bad request with {request.headers['Authorization']}")

    with pytest.raises(ProviderError) as info:
        _provider(handler).complete("PROMPT")
    error = info.value
    assert SECRET not in f"{error} {error.message} {error.hint}"
    assert "[redacted]" in error.message


def test_settings_never_print_the_key():
    settings = Settings(llm_api_key=SECRET)
    assert SECRET not in repr(settings) and SECRET not in str(settings.model_dump())


@pytest.mark.parametrize(
    "base_url",
    [
        "http://llm.test/v1?key=SECRET-IN-URL",  # some providers take the key as a query param
        "http://user:SECRET-IN-URL@llm.test/v1",  # credentials in the userinfo part
    ],
)
def test_credentials_in_the_base_url_never_appear_in_an_error(base_url):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderError) as info:
        _provider(handler, base_url=base_url).complete("PROMPT")
    error = info.value
    assert "SECRET-IN-URL" not in f"{error} {error.message} {error.hint}"
    assert "llm.test" in error.message  # still says where it tried


def test_url_credentials_echoed_by_the_provider_are_redacted():
    def handler(request):
        return httpx.Response(400, text=f"bad request for {request.url}")

    for base_url in ("http://llm.test/v1?key=SECRET-IN-URL", "http://u:SECRET-IN-URL@llm.test/v1"):
        with pytest.raises(ProviderError) as info:
            _provider(handler, base_url=base_url).complete("PROMPT")
        assert "SECRET-IN-URL" not in info.value.message, base_url

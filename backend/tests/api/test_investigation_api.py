"""Investigation endpoints end to end, with the mock and with injected providers."""

from datetime import timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from sentinel.config import BACKEND_DIR, Settings
from sentinel.investigation.providers.mock import MockProvider
from sentinel.investigation.providers.openai_compatible import OpenAICompatibleProvider
from sentinel.main import create_app

ONE_SCENARIO_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "scenarios"
SECRET = "fake-key-for-tests"  # obviously fake: secret scanners must not flag it


class SpyProvider:
    """Counts calls; behaves like the mock otherwise."""

    name, model = "spy", "spy-1"

    def __init__(self):
        self.calls = 0
        self._mock = MockProvider()

    def complete(self, prompt):
        self.calls += 1
        return self._mock.complete(prompt)


def _client(clock, scenarios=ONE_SCENARIO_DIR, provider=None, **settings):
    s = Settings(scenarios_dir=scenarios, db_path=":memory:", **settings)
    return TestClient(create_app(s, clock, llm_provider=provider))


def _first_incident(client):
    client.post("/api/v1/sync")
    return client.get("/api/v1/incidents").json()["items"][0]["id"]


def test_post_runs_the_mock_and_every_citation_exists(clock):
    client = _client(clock)
    incident_id = _first_incident(client)
    body = client.post(f"/api/v1/incidents/{incident_id}/investigation").json()
    inv = body["investigation"]
    assert inv["status"] == "completed"
    assert inv["provider"] == "mock" and inv["model"] == "mock-rules-v1"
    facts = {f["id"] for f in client.get(f"/api/v1/incidents/{incident_id}").json()["facts"]}
    cited = {c for h in inv["findings"]["hypotheses"] for c in h["cites"]}
    assert cited and cited <= facts
    assert all(r["requires_human"] is True for r in inv["findings"]["remediation"])
    assert body["outdated"] is False and body["runs"] == 1


def test_get_returns_the_latest_and_never_calls_the_provider(clock):
    spy = SpyProvider()
    client = _client(clock, provider=spy)
    incident_id = _first_incident(client)
    assert client.get(f"/api/v1/incidents/{incident_id}/investigation").status_code == 404
    client.post(f"/api/v1/incidents/{incident_id}/investigation")
    for _ in range(3):
        assert client.get(f"/api/v1/incidents/{incident_id}/investigation").status_code == 200
    client.get("/api/v1/incidents")
    client.get("/api/v1/overview")
    client.get(f"/api/v1/incidents/{incident_id}")
    assert spy.calls == 1


def test_sync_never_calls_the_provider(clock):
    spy = SpyProvider()
    client = _client(clock, provider=spy)
    for _ in range(3):
        client.post("/api/v1/sync")
    assert spy.calls == 0


def test_incident_detail_is_unchanged_by_an_investigation(clock):
    client = _client(clock)
    incident_id = _first_incident(client)
    before = client.get(f"/api/v1/incidents/{incident_id}").json()
    client.post(f"/api/v1/incidents/{incident_id}/investigation")
    assert client.get(f"/api/v1/incidents/{incident_id}").json() == before


def test_list_shows_completed_then_outdated_after_the_incident_changes(clock):
    # the escalation scenario: its incident is updated by the second sync
    client = _client(clock, scenarios=BACKEND_DIR / "scenarios")
    client.post("/api/v1/sync")
    items = client.get("/api/v1/incidents").json()["items"]
    escalation = next(i for i in items if i["resource_id"] == "sim-escalation")
    assert escalation["investigation_status"] == "not_run"

    client.post(f"/api/v1/incidents/{escalation['id']}/investigation")
    statuses = {
        i["id"]: i["investigation_status"] for i in client.get("/api/v1/incidents").json()["items"]
    }
    assert statuses[escalation["id"]] == "completed"

    clock.advance(timedelta(minutes=1))
    client.post("/api/v1/sync")  # escalation: R-5XX merged, evidence hash changes
    statuses = {
        i["id"]: i["investigation_status"] for i in client.get("/api/v1/incidents").json()["items"]
    }
    assert statuses[escalation["id"]] == "outdated"
    latest = client.get(f"/api/v1/incidents/{escalation['id']}/investigation").json()
    assert latest["outdated"] is True


def test_unknown_incident_is_404(clock):
    client = _client(clock)
    response = client.post("/api/v1/incidents/INC-9999/investigation")
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


def test_incomplete_real_provider_is_503_and_the_rest_keeps_working(clock):
    client = _client(clock, llm_provider="openai_compatible")  # no base URL, no model
    incident_id = _first_incident(client)
    response = client.post(f"/api/v1/incidents/{incident_id}/investigation")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
    assert client.get("/api/v1/system").json()["llm"]["configured"] is False
    assert client.get("/api/v1/overview").status_code == 200


def test_the_api_key_never_appears_in_a_response(clock):
    def echo_auth(request):
        return httpx.Response(400, text=f"rejected {request.headers['Authorization']}")

    provider = OpenAICompatibleProvider(
        base_url="http://llm.test/v1",
        model="test-model",
        api_key=SECRET,
        transport=httpx.MockTransport(echo_auth),
    )
    client = _client(clock, provider=provider)
    incident_id = _first_incident(client)
    response = client.post(f"/api/v1/incidents/{incident_id}/investigation")
    assert response.status_code == 200
    assert response.json()["investigation"]["status"] == "failed"
    for text in (
        response.text,
        client.get(f"/api/v1/incidents/{incident_id}/investigation").text,
        client.get("/api/v1/system").text,
    ):
        assert SECRET not in text

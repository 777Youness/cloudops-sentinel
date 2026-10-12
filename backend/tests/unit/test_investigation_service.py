"""InvestigationService: one retry, failures saved, incident untouched, outdated detection."""

import json
import threading
from datetime import timedelta

import pytest

from sentinel.detection import engine
from sentinel.domain.errors import (
    InvestigationInProgressError,
    LlmNotConfiguredError,
    NotFoundError,
)
from sentinel.domain.observations import ObservationSnapshot, Resource
from sentinel.domain.system import LlmStatus
from sentinel.investigation.providers.base import ProviderError
from sentinel.investigation.providers.mock import MockProvider
from sentinel.services.investigation import InvestigationService
from sentinel.store.sqlite import SqliteStore
from tests.conftest import NOW, make_series

VALID = json.dumps(
    {
        "summary": "CPU is saturated.",
        "hypotheses": [{"id": "H1", "statement": "Load.", "confidence": "low", "cites": ["F1"]}],
    }
)
INVALID = json.dumps(
    {
        "summary": "x",
        "hypotheses": [{"id": "H1", "statement": "x", "confidence": "low", "cites": ["F99"]}],
    }
)


class ScriptedProvider:
    """Replies in order; records every prompt. Raises a ProviderError for exceptions."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _snapshot(cpu_values):
    resource = Resource(
        id="r-1",
        name="api-01",
        region="eu-west-3",
        state="running",
        instance_type="t3.micro",
        data_origin="simulated",
    )
    return ObservationSnapshot(
        collected_at=NOW,
        window_start=NOW - timedelta(hours=3),
        window_end=NOW,
        data_origin="simulated",
        resources=[resource],
        series=[make_series(cpu_values)],
    )


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    [incident] = engine.evaluate(
        _snapshot([40.0] * 90 + [97.0] * 20), [], NOW, lambda: "INC-0001"
    ).opened
    s.add_incident(incident)
    return s


def _service(store, provider, clock):
    status = LlmStatus(provider=getattr(provider, "name", None), model=None, configured=True)
    return InvestigationService(store, provider, status, clock)


def test_a_valid_reply_is_saved_as_completed(store, clock):
    result = _service(store, ScriptedProvider(VALID), clock).run("INC-0001")
    inv = result.investigation
    assert inv.status == "completed" and inv.attempts == 1
    assert inv.id == "INV-0001"
    assert inv.findings.hypotheses[0].cites == ["F1"]
    assert inv.evidence_hash == store.get_incident("INC-0001").evidence_hash
    assert result.outdated is False and result.runs == 1


def test_invalid_reply_gets_one_retry_with_the_reason(store, clock):
    provider = ScriptedProvider(INVALID, VALID)
    inv = _service(store, provider, clock).run("INC-0001").investigation
    assert inv.status == "completed" and inv.attempts == 2
    assert "unknown_fact" in provider.prompts[1] and "F99" in provider.prompts[1]
    assert "unknown_fact" not in provider.prompts[0]


def test_two_invalid_replies_fail_and_are_saved_without_repair(store, clock):
    provider = ScriptedProvider(INVALID, INVALID, VALID)
    result = _service(store, provider, clock).run("INC-0001")
    inv = result.investigation
    assert inv.status == "failed" and inv.attempts == 2
    assert inv.findings is None  # nothing from a rejected reply is kept
    assert inv.error.code == "unknown_fact"
    assert len(provider.replies) == 1  # no third call
    assert store.latest_investigation("INC-0001").status == "failed"


def test_provider_error_fails_without_retry(store, clock):
    provider = ScriptedProvider(ProviderError("timeout", "too slow", "raise the timeout"))
    inv = _service(store, provider, clock).run("INC-0001").investigation
    assert inv.status == "failed" and inv.attempts == 1
    assert inv.error.code == "timeout" and inv.error.hint == "raise the timeout"


def test_the_incident_is_never_changed(store, clock):
    before = store.get_incident("INC-0001")
    _service(store, ScriptedProvider(VALID), clock).run("INC-0001")
    _service(store, ScriptedProvider(INVALID, INVALID), clock).run("INC-0001")
    after = store.get_incident("INC-0001")
    assert after == before  # facts, severity, timeline, evidence and hash, byte for byte


def test_every_run_is_kept_and_the_latest_is_returned(store, clock):
    service = _service(store, ScriptedProvider(VALID, INVALID, INVALID), clock)
    service.run("INC-0001")
    clock.advance(timedelta(minutes=1))
    service.run("INC-0001")
    result = service.latest("INC-0001")
    assert result.runs == 2
    assert result.investigation.id == "INV-0002" and result.investigation.status == "failed"


def test_latest_never_calls_the_provider(store, clock):
    provider = ScriptedProvider(VALID)
    service = _service(store, provider, clock)
    service.run("INC-0001")
    for _ in range(3):
        service.latest("INC-0001")
    assert len(provider.prompts) == 1


def test_outdated_when_the_incident_evidence_changed(store, clock):
    service = _service(store, ScriptedProvider(VALID), clock)
    service.run("INC-0001")
    # a later sync merges a new rule into the incident: its evidence hash changes
    incident = store.get_incident("INC-0001")
    memory = make_series([50.0] * 90 + [95.0] * 20, signal="memory_used")
    snapshot = _snapshot([40.0] * 90 + [97.0] * 20)
    snapshot.series.append(memory)
    [updated] = engine.evaluate(snapshot, [incident], NOW, lambda: "unused").updated
    store.update_incident(updated)
    result = service.latest("INC-0001")
    assert result.outdated is True
    assert result.incident_evidence_hash != result.investigation.evidence_hash


def test_unknown_incident(store, clock):
    with pytest.raises(NotFoundError):
        _service(store, MockProvider(), clock).run("INC-9999")


def test_latest_before_any_run(store, clock):
    with pytest.raises(NotFoundError, match="No investigation"):
        _service(store, MockProvider(), clock).latest("INC-0001")


def test_not_configured(store, clock):
    service = InvestigationService(
        store, None, LlmStatus(provider="openai_compatible", model=None, configured=False), clock
    )
    with pytest.raises(LlmNotConfiguredError):
        service.run("INC-0001")


def test_one_investigation_per_incident_at_a_time(store, clock):
    started, release = threading.Event(), threading.Event()

    class SlowProvider:
        name, model = "slow", "slow-1"

        def complete(self, prompt):
            started.set()
            release.wait(5)
            return VALID

    service = _service(store, SlowProvider(), clock)
    worker = threading.Thread(target=service.run, args=("INC-0001",))
    worker.start()
    started.wait(5)
    try:
        with pytest.raises(InvestigationInProgressError):
            service.run("INC-0001")
    finally:
        release.set()
        worker.join(5)
    assert store.count_investigations("INC-0001") == 1

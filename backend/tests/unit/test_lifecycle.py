"""Incident lifecycle in the engine: merge, peak severity, resolution, events."""

from datetime import timedelta
from itertools import count

from sentinel.detection import engine
from sentinel.domain.observations import ObservationSnapshot, OpsEvent, Resource
from tests.conftest import NOW, make_series

RESOURCE = Resource(
    id="r-1",
    name="api-01",
    region="eu-west-3",
    state="running",
    instance_type="t3.micro",
    data_origin="simulated",
)
REQUESTS = make_series([120.0] * 110, signal="request_rate", unit="per_minute")


def _ids():
    c = count(1)
    return lambda: f"INC-{next(c):04d}"


def _snapshot(*series, events=()):
    return ObservationSnapshot(
        collected_at=NOW,
        window_start=NOW - timedelta(hours=3),
        window_end=NOW,
        data_origin="simulated",
        resources=[RESOURCE],
        series=list(series),
        events=list(events),
    )


def _cpu(values):
    return make_series(values)


def _mem(values):
    return make_series(values, signal="memory_used")


def _deploy(event_id="deploy-1", minutes_ago=25):
    return OpsEvent(
        id=event_id,
        resource_id="r-1",
        kind="deployment",
        at=NOW.replace(second=0) - timedelta(minutes=minutes_ago),
        label="Deploy v1.0.1",
        source="test",
        data_origin="simulated",
    )


def _open(*series, events=()):
    [incident] = engine.evaluate(_snapshot(*series, events=events), [], NOW, _ids()).opened
    return incident


CPU_BREACH = [40.0] * 90 + [97.0] * 20


# --- merge -------------------------------------------------------------------------------


def test_new_rule_is_merged_and_existing_facts_never_change():
    incident = _open(_cpu(CPU_BREACH), _mem([50.0] * 110))
    later = NOW + timedelta(minutes=5)
    result = engine.evaluate(
        _snapshot(_cpu(CPU_BREACH), _mem([50.0] * 90 + [95.0] * 20)), [incident], later, _ids()
    )
    [updated] = result.updated
    assert result.opened == []
    assert updated.id == incident.id
    assert updated.rule_ids == ["R-CPU-SAT", "R-MEM"]
    # every existing fact is kept verbatim; new ones continue the numbering
    assert updated.facts[: len(incident.facts)] == incident.facts
    [mem_fact] = updated.facts[len(incident.facts) :]
    assert mem_fact.id == f"F{len(incident.facts) + 1}"
    assert mem_fact.rule_id == "R-MEM"
    assert updated.timeline[-1].kind == "incident_updated"
    times = [e.at for e in updated.timeline]
    assert times == sorted(times)  # chronological, even when a merged breach started earlier
    assert updated.last_updated_at == later
    assert updated.evidence_hash != incident.evidence_hash


def test_engine_does_not_mutate_the_incident_it_is_given():
    incident = _open(_cpu(CPU_BREACH))
    before = incident.model_copy(deep=True)
    engine.evaluate(
        _snapshot(_cpu(CPU_BREACH), _mem([50.0] * 90 + [95.0] * 20)), [incident], NOW, _ids()
    )
    assert incident == before


def test_severity_rises_while_open():
    incident = _open(_cpu(CPU_BREACH))
    status = make_series([0.0] * 100 + [1.0] * 3, signal="status_check_failed", unit="count")
    [updated] = engine.evaluate(
        _snapshot(_cpu(CPU_BREACH), status), [incident], NOW, _ids()
    ).updated
    assert updated.severity == "critical"
    assert updated.title == "Status check failing on api-01"  # renamed after what is now worst


def test_severity_never_drops_while_open():
    errors = make_series([0.3] * 100 + [8.0] * 10, signal="error_rate_5xx")
    incident = _open(_cpu(CPU_BREACH), errors, REQUESTS)
    assert incident.severity == "high"
    # errors are gone but CPU is still saturated: still open, still high, nothing to update
    calm = make_series([0.3] * 110, signal="error_rate_5xx")
    result = engine.evaluate(_snapshot(_cpu(CPU_BREACH), calm, REQUESTS), [incident], NOW, _ids())
    assert result.updated == [] and result.resolved == []


def test_new_event_while_open_is_recorded_once():
    incident = _open(_cpu(CPU_BREACH))
    snapshot = _snapshot(_cpu(CPU_BREACH), events=[_deploy()])
    [updated] = engine.evaluate(snapshot, [incident], NOW, _ids()).updated
    [event_fact] = [f for f in updated.facts if f.kind == "event"]
    assert event_fact.event_id == "deploy-1"
    assert any(e.kind == "event" and e.fact_id == event_fact.id for e in updated.timeline)
    # the same event seen again on the next sync changes nothing
    assert engine.evaluate(snapshot, [updated], NOW, _ids()).updated == []


def test_events_before_the_breach_are_facts_when_opening():
    incident = _open(_cpu(CPU_BREACH), events=[_deploy(minutes_ago=25)])
    [event_fact] = [f for f in incident.facts if f.kind == "event"]
    assert event_fact.statement == "Deployment at 13:40 UTC: Deploy v1.0.1"
    # the code records the event; it never claims the event caused anything
    assert "cause" not in event_fact.statement.lower()


def test_events_long_before_the_evidence_window_are_ignored():
    incident = _open(_cpu(CPU_BREACH), events=[_deploy(minutes_ago=170)])
    assert not [f for f in incident.facts if f.kind == "event"]


# --- resolution --------------------------------------------------------------------------


def _resolve_with(cpu_values):
    incident = _open(_cpu(CPU_BREACH))
    later = NOW + timedelta(minutes=30)
    return incident, engine.evaluate(_snapshot(_cpu(cpu_values)), [incident], later, _ids())


def test_resolves_after_exactly_ten_clean_minutes():
    incident, result = _resolve_with([40.0] * 90 + [97.0] * 10 + [40.0] * 10)
    [resolved] = result.resolved
    assert resolved.status == "resolved"
    assert resolved.resolved_at == NOW + timedelta(minutes=30)
    assert resolved.timeline[-1].kind == "incident_resolved"
    [cleared] = resolved.facts[len(incident.facts) :]
    assert cleared.kind == "within_normal"
    assert cleared.statement.startswith("CPU utilization below 90% for 10 min since")


def test_does_not_resolve_after_nine_clean_minutes():
    _, result = _resolve_with([40.0] * 90 + [97.0] * 10 + [40.0] * 9)
    assert result.resolved == []


def test_a_gap_is_not_clean():
    cpu = _cpu([40.0] * 90 + [97.0] * 10 + [40.0] * 12)
    del cpu.points[-6:-4]  # two missing datapoints inside the clean run
    incident = _open(_cpu(CPU_BREACH))
    result = engine.evaluate(_snapshot(cpu), [incident], NOW, _ids())
    assert result.resolved == []


def test_missing_data_never_resolves():
    incident = _open(_cpu(CPU_BREACH))
    result = engine.evaluate(_snapshot(), [incident], NOW, _ids())
    assert result.resolved == []


def test_every_condition_must_be_clear():
    incident = _open(_cpu(CPU_BREACH), _mem([50.0] * 90 + [95.0] * 20))
    assert incident.rule_ids == ["R-CPU-SAT", "R-MEM"]
    # CPU clear for 20 min, memory only for 5 min
    snapshot = _snapshot(_cpu([40.0] * 110), _mem([50.0] * 90 + [95.0] * 15 + [50.0] * 5))
    assert engine.evaluate(snapshot, [incident], NOW, _ids()).resolved == []


def test_latency_clears_against_its_recorded_threshold():
    latency = make_series([180.0] * 95 + [1400.0] * 15, signal="latency_p95", unit="ms")
    incident = _open(_cpu([40.0] * 110), latency, REQUESTS)
    assert incident.rule_ids == ["R-LAT"]
    # 520 ms is above the 500 ms floor but below the recorded 540 ms threshold (3 x 180)
    recovered = make_series([180.0] * 95 + [520.0] * 15, signal="latency_p95", unit="ms")
    result = engine.evaluate(
        _snapshot(_cpu([40.0] * 110), recovered, REQUESTS), [incident], NOW, _ids()
    )
    assert [r.id for r in result.resolved] == [incident.id]

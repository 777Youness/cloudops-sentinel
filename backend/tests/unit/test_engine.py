from datetime import timedelta
from itertools import count

from sentinel.detection import engine
from sentinel.domain.observations import ObservationSnapshot, Resource
from tests.conftest import NOW, make_series


def _snapshot(values, *extra_series):
    series = make_series(values)
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
        series=[series, *extra_series],
    )


def _ids():
    c = count(1)
    return lambda: f"INC-{next(c):04d}"


def test_opens_incident_with_fact_and_rule_severity():
    result = engine.evaluate(_snapshot([40.0] * 90 + [97.0] * 20), set(), NOW, _ids())
    [incident] = result.opened
    assert incident.severity == "medium"  # from the severity matrix, not from anything else
    assert incident.rule_ids == ["R-CPU-SAT"]
    assert incident.facts[0].id == "F1"
    assert incident.facts[0].kind == "threshold_breach"
    assert "at or above 90%" in incident.facts[0].statement
    assert incident.data_origin == "simulated"


def test_evidence_keeps_60_minutes_before_breach():
    result = engine.evaluate(_snapshot([40.0] * 90 + [97.0] * 20), set(), NOW, _ids())
    points = result.opened[0].evidence.series[0].points
    breach_start = result.opened[0].facts[0].window.start
    assert points[0].t == breach_start - timedelta(minutes=60)


def test_no_duplicate_when_resource_already_has_open_incident():
    result = engine.evaluate(_snapshot([40.0] * 90 + [97.0] * 20), {"r-1"}, NOW, _ids())
    assert result.opened == []


def test_normal_data_opens_nothing():
    result = engine.evaluate(_snapshot([40.0] * 110), set(), NOW, _ids())
    assert result.opened == []
    assert result.resources_evaluated == 1


def test_evidence_hash_is_stable():
    a = engine.evaluate(_snapshot([40.0] * 90 + [97.0] * 20), set(), NOW, _ids())
    b = engine.evaluate(_snapshot([40.0] * 90 + [97.0] * 20), set(), NOW, _ids())
    assert a.opened[0].evidence_hash == b.opened[0].evidence_hash


def _signal(values, signal, unit="percent"):
    return make_series(values, signal=signal, unit=unit)


CPU_BREACH = [40.0] * 90 + [97.0] * 20


def test_unevaluable_rules_become_data_gap_facts_after_the_breach():
    # Only CPU is present. The test resource has no credit mode, so R-CPU-CREDIT is
    # not applicable (no fact); every other rule could not be evaluated.
    [incident] = engine.evaluate(_snapshot(CPU_BREACH), set(), NOW, _ids()).opened
    kinds = [f.kind for f in incident.facts]
    assert kinds[0] == "threshold_breach"
    assert set(kinds[1:]) == {"data_gap"}
    gap_rules = {f.rule_id for f in incident.facts if f.kind == "data_gap"}
    assert gap_rules == {"R-MEM", "R-STATUS", "R-5XX", "R-LAT"}
    assert all(f.value is None for f in incident.facts if f.kind == "data_gap")  # never 0


def test_checked_normal_signals_become_within_normal_facts():
    memory = _signal([50.0] * 110, "memory_used")
    [incident] = engine.evaluate(_snapshot(CPU_BREACH, memory), set(), NOW, _ids()).opened
    [normal] = [f for f in incident.facts if f.kind == "within_normal"]
    assert normal.rule_id == "R-MEM"
    assert normal.value == 50.0
    assert normal.statement == "Memory utilization below 90% (latest 50.0%)"


def test_fact_ids_are_sequential_and_unique():
    memory = _signal([50.0] * 110, "memory_used")
    [incident] = engine.evaluate(_snapshot(CPU_BREACH, memory), set(), NOW, _ids()).opened
    assert [f.id for f in incident.facts] == [f"F{i}" for i in range(1, len(incident.facts) + 1)]


def test_several_rules_on_one_resource_make_one_incident():
    memory = _signal([50.0] * 90 + [95.0] * 20, "memory_used")
    result = engine.evaluate(_snapshot(CPU_BREACH, memory), set(), NOW, _ids())
    [incident] = result.opened
    assert incident.rule_ids == ["R-CPU-SAT", "R-MEM"]
    assert [k.signal for k in incident.key_signals] == ["cpu_utilization", "memory_used"]
    breach_facts = [f for f in incident.facts if f.kind == "threshold_breach"]
    assert len(breach_facts) == 2
    # every breach has a timeline entry pointing to its fact
    linked = {e.fact_id for e in incident.timeline if e.kind == "breach_start"}
    assert linked == {f.id for f in breach_facts}


def test_latency_and_errors_together_raise_severity_and_name_the_incident():
    requests = _signal([120.0] * 110, "request_rate", "per_minute")
    errors = _signal([0.3] * 95 + [3.5] * 15, "error_rate_5xx")  # lower tier: medium
    latency = _signal([180.0] * 95 + [1400.0] * 15, "latency_p95", "ms")  # medium
    snapshot = _snapshot([40.0] * 110, requests, errors, latency)
    [incident] = engine.evaluate(snapshot, set(), NOW, _ids()).opened
    assert incident.rule_ids == ["R-5XX", "R-LAT", "C-USER-IMPACT"]
    assert incident.severity == "high"
    assert incident.title == "User-facing errors and latency on api-01"
    # the derived rule has no fact of its own; its parts do
    assert "C-USER-IMPACT" not in {f.rule_id for f in incident.facts}
    [lat_fact] = [f for f in incident.facts if f.rule_id == "R-LAT"]
    assert lat_fact.kind == "baseline_deviation"
    assert lat_fact.baseline == 180.0


def test_evidence_keeps_every_series_of_the_resource():
    memory = _signal([50.0] * 110, "memory_used")
    [incident] = engine.evaluate(_snapshot(CPU_BREACH, memory), set(), NOW, _ids()).opened
    assert {s.signal for s in incident.evidence.series} == {"cpu_utilization", "memory_used"}

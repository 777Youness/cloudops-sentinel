from datetime import timedelta
from itertools import count

from sentinel.detection import engine
from sentinel.domain.observations import ObservationSnapshot, Resource
from tests.conftest import NOW, make_series


def _snapshot(values):
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
        series=[series],
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

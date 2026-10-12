"""Resource health: ok, warn, crit, unknown; missing signals always reported."""

from datetime import timedelta

from sentinel.detection import engine
from sentinel.detection.health import V1_SIGNALS, expected_signals, resource_health
from sentinel.domain.observations import ObservationSnapshot, Resource
from tests.conftest import NOW, make_series


def _resource(instance_type="t3.micro"):
    return Resource(
        id="r-1",
        name="api-01",
        region="eu-west-3",
        state="running",
        instance_type=instance_type,
        credit_mode="standard",
        data_origin="simulated",
    )


def _all_signals(cpu_values=None):
    series = [make_series([1.0] * 30, signal=s) for s in V1_SIGNALS if s != "cpu_utilization"]
    return [make_series(cpu_values or [40.0] * 30), *series]


def _incident(severity_series):
    snapshot = ObservationSnapshot(
        collected_at=NOW,
        window_start=NOW - timedelta(hours=3),
        window_end=NOW,
        data_origin="simulated",
        resources=[_resource()],
        series=severity_series,
    )
    [incident] = engine.evaluate(snapshot, [], NOW, lambda: "INC-0001").opened
    return incident


def test_ok_with_every_signal_present():
    h = resource_health(_resource(), _all_signals(), None)
    assert h.health == "ok"
    assert h.signals_missing == []
    assert h.last_datapoint_at == NOW.replace(second=0)


def test_ok_still_lists_missing_signals():
    series = [s for s in _all_signals() if s.signal != "memory_used"]
    h = resource_health(_resource(), series, None)
    assert h.health == "ok"
    assert h.signals_missing == ["memory_used"]


def test_unknown_when_there_is_no_datapoint_at_all():
    h = resource_health(_resource(), [], None)
    assert h.health == "unknown"
    assert h.signals_missing == expected_signals(_resource())
    assert h.last_datapoint_at is None


def test_series_without_points_counts_as_missing():
    empty = make_series([], signal="memory_used")
    h = resource_health(_resource(), [*_all_signals(), empty], None)
    assert "memory_used" not in h.signals_missing  # the full series list has memory too
    h = resource_health(_resource(), [empty], None)
    assert h.health == "unknown"


def test_medium_open_incident_is_warn():
    incident = _incident([make_series([40.0] * 90 + [97.0] * 20)])
    assert incident.severity == "medium"
    h = resource_health(_resource(), _all_signals(), incident)
    assert h.health == "warn"
    assert h.open_incident_id == "INC-0001"
    assert h.open_incident_severity == "medium"


def test_critical_open_incident_is_crit():
    status = make_series([0.0] * 30 + [1.0] * 3, signal="status_check_failed", unit="count")
    incident = _incident([status])
    assert incident.severity == "critical"
    assert resource_health(_resource(), _all_signals(), incident).health == "crit"


def test_open_incident_wins_over_missing_data():
    # a resource with a known problem is not "unknown" just because its data stopped
    incident = _incident([make_series([40.0] * 90 + [97.0] * 20)])
    assert resource_health(_resource(), [], incident).health == "warn"


def test_credit_balance_is_only_expected_on_burstable_instances():
    assert "cpu_credit_balance" in expected_signals(_resource("t3.micro"))
    assert "cpu_credit_balance" not in expected_signals(_resource("m5.large"))

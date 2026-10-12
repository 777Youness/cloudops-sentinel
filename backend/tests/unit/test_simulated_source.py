from datetime import timedelta

import pytest

from sentinel.collectors.simulated import Scenario, SimulatedSource, load_scenarios
from sentinel.config import Settings


def _source(clock):
    return SimulatedSource(load_scenarios(Settings().scenarios_dir), clock, region="eu-west-3")


def test_same_clock_same_data(clock):
    now = clock.now()
    a = _source(clock).collect(now - timedelta(hours=3), now)
    b = _source(clock).collect(now - timedelta(hours=3), now)
    assert a == b


def test_series_ends_at_latest_complete_period(clock):
    # A datapoint timestamped T covers [T, T + period). At 14:05:30 the 14:05 period is
    # still running, so the latest complete one starts at 14:04 (as in CloudWatch).
    now = clock.now()  # 14:05:30
    snapshot = _source(clock).collect(now - timedelta(hours=3), now)
    last = snapshot.series[0].points[-1].t
    assert last == now.replace(minute=4, second=0)
    assert last + timedelta(seconds=snapshot.series[0].period_seconds) <= now
    assert all(p.t.tzinfo is not None for s in snapshot.series for p in s.points)


def test_every_entity_is_labelled_simulated(clock):
    now = clock.now()
    snapshot = _source(clock).collect(now - timedelta(hours=3), now)
    assert snapshot.data_origin == "simulated"
    assert all(r.data_origin == "simulated" for r in snapshot.resources)


def test_window_filters_points(clock):
    now = clock.now()
    snapshot = _source(clock).collect(now - timedelta(minutes=10), now)
    assert all(p.t >= now - timedelta(minutes=10) for p in snapshot.series[0].points)


def _phased(clock):
    [recovery] = [s for s in load_scenarios(Settings().scenarios_dir) if s.id == "recovery"]
    return SimulatedSource([recovery], clock, region="eu-west-3")


def _latest_cpu(snapshot):
    [cpu] = [s for s in snapshot.series if s.signal == "cpu_utilization"]
    return cpu.points[-1].v


def test_phases_advance_one_per_collection_and_the_last_repeats(clock):
    source = _phased(clock)
    now = clock.now()
    window = (now - timedelta(hours=3), now)
    latest = [_latest_cpu(source.collect(*window)) for _ in range(4)]
    assert latest[0] > 90  # phase 1: saturated now
    assert latest[1] < 90  # phase 2: recovered
    assert latest[2] > 90  # phase 3: saturated again
    assert latest[3] == latest[2]  # phase 3 repeats


def test_events_have_stable_ids_and_follow_the_window(clock):
    [escalation] = [s for s in load_scenarios(Settings().scenarios_dir) if s.id == "escalation"]
    source = SimulatedSource([escalation], clock, region="eu-west-3")
    now = clock.now()
    [event] = source.collect(now - timedelta(hours=3), now).events
    assert event.id == "escalation:deploy-v1-4-2"
    assert event.data_origin == "simulated"
    assert source.collect(now - timedelta(minutes=10), now).events == []  # 16 min ago


def test_a_scenario_needs_expected_or_phases():
    with pytest.raises(ValueError, match="either `expected` or `phases`"):
        Scenario.model_validate(
            {"id": "x", "title": "x", "resource": {"id": "r", "name": "r"}, "signals": {}}
        )

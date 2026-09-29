from datetime import timedelta

from sentinel.collectors.simulated import SimulatedSource, load_scenarios
from sentinel.config import Settings


def _source(clock):
    return SimulatedSource(load_scenarios(Settings().scenarios_dir), clock, region="eu-west-3")


def test_same_clock_same_data(clock):
    now = clock.now()
    a = _source(clock).collect(now - timedelta(hours=3), now)
    b = _source(clock).collect(now - timedelta(hours=3), now)
    assert a == b


def test_series_ends_at_latest_complete_period(clock):
    now = clock.now()  # 14:05:30
    snapshot = _source(clock).collect(now - timedelta(hours=3), now)
    last = snapshot.series[0].points[-1].t
    assert last == now.replace(second=0)
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

"""R-CPU-SAT: CPU >= 90% for at least 10 minutes, still ongoing at the latest datapoint."""

from datetime import timedelta

from sentinel.detection.rules import cpu_saturation
from tests.conftest import make_series

NORMAL = [40.0] * 30


def test_triggers_on_sustained_saturation():
    result = cpu_saturation(make_series(NORMAL + [97.0] * 20), "r-1")
    assert result.triggered
    assert result.duration == timedelta(minutes=20)
    assert result.peak == 97.0


def test_does_not_trigger_below_threshold():
    result = cpu_saturation(make_series(NORMAL + [85.0] * 20), "r-1")
    assert not result.triggered
    assert result.reason == "below_threshold"


def test_exactly_threshold_counts_as_breach():
    result = cpu_saturation(make_series(NORMAL + [90.0] * 10), "r-1")
    assert result.triggered


def test_just_below_threshold_does_not_count():
    result = cpu_saturation(make_series(NORMAL + [89.99] * 20), "r-1")
    assert not result.triggered


def test_exactly_minimum_duration_triggers():
    # 10 one-minute datapoints cover 10 minutes
    result = cpu_saturation(make_series(NORMAL + [97.0] * 10), "r-1")
    assert result.triggered
    assert result.duration == timedelta(minutes=10)


def test_too_short_breach_does_not_trigger():
    result = cpu_saturation(make_series(NORMAL + [97.0] * 6), "r-1")
    assert not result.triggered
    assert result.reason == "too_short"
    assert result.duration == timedelta(minutes=6)


def test_breach_that_already_ended_is_not_active():
    result = cpu_saturation(make_series(NORMAL + [97.0] * 20 + [40.0] * 5), "r-1")
    assert not result.triggered
    assert result.reason == "below_threshold"


def test_single_spike_does_not_trigger():
    result = cpu_saturation(make_series(NORMAL + [99.0]), "r-1")
    assert not result.triggered
    assert result.reason == "too_short"


def test_missing_series_is_insufficient_data_not_zero():
    assert cpu_saturation(None, "r-1").reason == "insufficient_data"


def test_gap_in_data_breaks_the_run():
    series = make_series(NORMAL + [97.0] * 20)
    # remove 3 datapoints in the middle of the breach: the run restarts after the gap
    del series.points[-12:-9]
    result = cpu_saturation(series, "r-1")
    assert not result.triggered
    assert result.reason == "too_short"


def test_five_minute_periods_use_period_length():
    # CloudWatch basic EC2 metrics: 5-minute periods. 2 datapoints = 10 minutes.
    result = cpu_saturation(make_series([40.0] * 10 + [95.0] * 2, period=300), "r-1")
    assert result.triggered
    assert result.duration == timedelta(minutes=10)

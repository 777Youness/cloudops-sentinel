"""R-LAT: p95 >= 3x baseline and >= 500 ms for 5 minutes, with >= 50 requests.

Baseline: median over [first breach - 70 min, first breach - 10 min), >= 30 min of data.
"""

from sentinel.detection.rules import latency_p95
from tests.conftest import make_series


def _lat(values):
    return make_series(values, signal="latency_p95", unit="ms")


def _requests(per_minute=120):
    return make_series([per_minute] * 120, signal="request_rate", unit="per_minute")


def test_triggers_far_above_baseline():
    result = latency_p95(_lat([180.0] * 70 + [1400.0] * 10), _requests(), "r-1")
    assert result.triggered
    assert result.baseline == 180.0
    assert result.threshold == 540.0  # 3 x 180


def test_above_floor_but_below_three_times_baseline_does_not_trigger():
    # baseline 300 -> threshold 900; 800 ms is slow, but not unusual for this service
    result = latency_p95(_lat([300.0] * 70 + [800.0] * 10), _requests(), "r-1")
    assert result.reason == "below_threshold"
    assert result.threshold == 900.0


def test_three_times_baseline_but_below_500_ms_floor_does_not_trigger():
    result = latency_p95(_lat([100.0] * 70 + [400.0] * 10), _requests(), "r-1")
    assert result.reason == "below_threshold"


def test_exactly_threshold_for_exactly_five_minutes_triggers():
    result = latency_p95(_lat([200.0] * 70 + [600.0] * 5), _requests(), "r-1")
    assert result.triggered


def test_too_short_breach_does_not_trigger():
    result = latency_p95(_lat([180.0] * 70 + [1400.0] * 4), _requests(), "r-1")
    assert result.reason == "too_short"


def test_exactly_thirty_minutes_of_baseline_is_enough():
    # points 11..40 minutes before the breach fall in the baseline window: 30 points
    assert latency_p95(_lat([180.0] * 40 + [1400.0] * 10), _requests(), "r-1").triggered


def test_less_than_thirty_minutes_of_baseline_is_insufficient_data():
    result = latency_p95(_lat([180.0] * 39 + [1400.0] * 10), _requests(), "r-1")
    assert not result.triggered
    assert result.reason == "insufficient_data"
    assert result.baseline is None


def test_low_traffic_is_insufficient_traffic():
    result = latency_p95(_lat([180.0] * 70 + [1400.0] * 10), _requests(per_minute=3), "r-1")
    assert result.reason == "insufficient_traffic"


def test_missing_series_is_insufficient_data():
    assert latency_p95(None, _requests(), "r-1").reason == "insufficient_data"

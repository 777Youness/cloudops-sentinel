"""R-5XX: 5xx rate >= 2% for 5 minutes with >= 50 requests. >= 5% is the full tier."""

from sentinel.detection.rules import error_rate_5xx
from tests.conftest import make_series

NORMAL = [0.3] * 30


def _errors(values):
    return make_series(values, signal="error_rate_5xx")


def _requests(per_minute, n=40):
    return make_series([per_minute] * n, signal="request_rate", unit="per_minute")


def test_full_tier_at_or_above_five_percent():
    result = error_rate_5xx(_errors(NORMAL + [8.0] * 6), _requests(120), "r-1")
    assert result.triggered
    assert not result.lower_tier
    assert result.threshold == 5.0


def test_lower_tier_between_two_and_five_percent():
    result = error_rate_5xx(_errors(NORMAL + [3.0] * 6), _requests(120), "r-1")
    assert result.triggered
    assert result.lower_tier
    assert result.threshold == 2.0


def test_exactly_two_percent_for_exactly_five_minutes_triggers_lower_tier():
    result = error_rate_5xx(_errors(NORMAL + [2.0] * 5), _requests(120), "r-1")
    assert result.triggered and result.lower_tier


def test_exactly_five_percent_for_five_minutes_is_full_tier():
    result = error_rate_5xx(_errors(NORMAL + [5.0] * 5), _requests(120), "r-1")
    assert result.triggered and not result.lower_tier


def test_short_spike_above_five_percent_stays_lower_tier():
    # >= 2% for 10 min, but >= 5% only for the last 3 min
    result = error_rate_5xx(_errors(NORMAL + [3.0] * 7 + [8.0] * 3), _requests(120), "r-1")
    assert result.triggered and result.lower_tier


def test_just_below_two_percent_does_not_count():
    result = error_rate_5xx(_errors(NORMAL + [1.99] * 10), _requests(120), "r-1")
    assert result.reason == "below_threshold"


def test_too_short_breach_does_not_trigger():
    result = error_rate_5xx(_errors(NORMAL + [8.0] * 4), _requests(120), "r-1")
    assert result.reason == "too_short"


def test_low_traffic_is_insufficient_traffic():
    result = error_rate_5xx(_errors(NORMAL + [25.0] * 10), _requests(2), "r-1")
    assert not result.triggered
    assert result.reason == "insufficient_traffic"


def test_exactly_fifty_requests_is_enough():
    # 10 requests/min over a 5-minute breach = 50 requests
    result = error_rate_5xx(_errors(NORMAL + [8.0] * 5), _requests(10), "r-1")
    assert result.triggered


def test_missing_error_series_is_insufficient_data():
    assert error_rate_5xx(None, _requests(120), "r-1").reason == "insufficient_data"


def test_missing_request_series_is_a_request_rate_gap():
    result = error_rate_5xx(_errors(NORMAL + [8.0] * 6), None, "r-1")
    assert result.reason == "insufficient_data"
    assert result.signal == "request_rate"


def test_request_series_without_points_in_breach_is_unknown_not_zero():
    old_requests = _requests(120, n=40)
    old_requests.points = old_requests.points[:20]  # stops well before the breach
    result = error_rate_5xx(_errors(NORMAL + [8.0] * 6), old_requests, "r-1")
    assert result.reason == "insufficient_data"

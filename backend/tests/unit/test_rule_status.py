"""R-STATUS: EC2 status check failed in at least 2 consecutive datapoints."""

from sentinel.detection.rules import status_check_failed
from tests.conftest import make_series

PASSING = [0.0] * 30


def _status(values):
    return make_series(values, signal="status_check_failed", unit="count")


def test_triggers_on_two_failed_datapoints():
    assert status_check_failed(_status(PASSING + [1.0, 1.0]), "r-1").triggered


def test_single_failed_datapoint_is_too_short():
    assert status_check_failed(_status(PASSING + [1.0]), "r-1").reason == "too_short"


def test_passing_checks_are_below_threshold():
    assert status_check_failed(_status(PASSING), "r-1").reason == "below_threshold"


def test_recovered_check_is_not_active():
    result = status_check_failed(_status(PASSING + [1.0, 1.0, 1.0, 0.0]), "r-1")
    assert result.reason == "below_threshold"


def test_missing_series_is_insufficient_data():
    assert status_check_failed(None, "r-1").reason == "insufficient_data"

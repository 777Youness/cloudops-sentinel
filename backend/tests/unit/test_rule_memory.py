"""R-MEM: memory used >= 90% for at least 10 minutes, still ongoing."""

from datetime import timedelta

from sentinel.detection.rules import memory_pressure
from tests.conftest import make_series

NORMAL = [50.0] * 30


def _mem(values):
    return make_series(values, signal="memory_used")


def test_triggers_on_sustained_pressure():
    result = memory_pressure(_mem(NORMAL + [94.0] * 15), "r-1")
    assert result.triggered
    assert result.duration == timedelta(minutes=15)


def test_does_not_trigger_below_threshold():
    assert memory_pressure(_mem(NORMAL + [85.0] * 15), "r-1").reason == "below_threshold"


def test_exactly_threshold_for_exactly_minimum_duration_triggers():
    assert memory_pressure(_mem(NORMAL + [90.0] * 10), "r-1").triggered


def test_too_short_breach_does_not_trigger():
    assert memory_pressure(_mem(NORMAL + [95.0] * 9), "r-1").reason == "too_short"


def test_missing_metric_is_insufficient_data_not_zero():
    # Memory needs the CloudWatch agent; without it there is no series at all.
    result = memory_pressure(None, "r-1")
    assert result.reason == "insufficient_data"
    assert result.latest is None

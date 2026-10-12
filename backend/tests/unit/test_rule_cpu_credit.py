"""R-CPU-CREDIT: credit balance <= 5 for 2 datapoints on a standard-mode T instance."""

from sentinel.detection.rules import cpu_credit_exhaustion
from sentinel.domain.observations import Resource
from tests.conftest import make_series

NORMAL = [60.0] * 30


def _resource(instance_type="t3.micro", credit_mode="standard"):
    return Resource(
        id="r-1",
        name="api-01",
        region="eu-west-3",
        state="running",
        instance_type=instance_type,
        credit_mode=credit_mode,
        data_origin="simulated",
    )


def _credits(values):
    return make_series(values, signal="cpu_credit_balance", unit="credits")


def test_triggers_when_credits_exhausted():
    result = cpu_credit_exhaustion(_credits(NORMAL + [3.0, 2.0]), _resource())
    assert result.triggered
    assert result.peak == 2.0  # for a "<=" rule the most extreme value is the lowest


def test_does_not_trigger_with_credits_left():
    result = cpu_credit_exhaustion(_credits(NORMAL + [20.0] * 5), _resource())
    assert result.reason == "below_threshold"


def test_exactly_threshold_counts_as_breach():
    assert cpu_credit_exhaustion(_credits(NORMAL + [5.0, 5.0]), _resource()).triggered


def test_just_above_threshold_does_not_count():
    result = cpu_credit_exhaustion(_credits(NORMAL + [5.01, 5.01]), _resource())
    assert not result.triggered


def test_single_datapoint_is_too_short():
    result = cpu_credit_exhaustion(_credits(NORMAL + [1.0]), _resource())
    assert result.reason == "too_short"


def test_missing_series_is_insufficient_data():
    assert cpu_credit_exhaustion(None, _resource()).reason == "insufficient_data"


def test_not_applicable_in_unlimited_mode():
    result = cpu_credit_exhaustion(_credits(NORMAL + [0.0] * 5), _resource(credit_mode="unlimited"))
    assert result.reason == "not_applicable"


def test_not_applicable_to_non_burstable_instance():
    result = cpu_credit_exhaustion(_credits(NORMAL + [0.0] * 5), _resource("m5.large", None))
    assert result.reason == "not_applicable"

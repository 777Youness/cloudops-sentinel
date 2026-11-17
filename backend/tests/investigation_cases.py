"""Investigation reliability cases, built through the real detection engine.

Case A has the shape of INC-0001, the first incident from real AWS data: a low CPU credit
balance and an elevated 5xx rate in the same incident, CPU utilization near zero, and no
deployment data (the AWS source does not collect it yet). The first real-provider run
joined the two breaches into a "high" confidence cause.

The ground truth of that demo (faults injected on purpose) is deliberately NOT encoded
here: the cases contain only what Sentinel's evidence would contain.

Used by tests/unit/test_investigation_reliability.py (no network) and by
evals/investigation_reliability.py (the same cases against a real provider, opt-in).
"""

from datetime import timedelta

from sentinel.detection import engine
from sentinel.domain.incidents import Incident
from sentinel.domain.observations import (
    DataOrigin,
    MetricSeries,
    ObservationSnapshot,
    OpsEvent,
    Resource,
)
from tests.conftest import NOW, make_series

MINUTES = 180  # the default 3-hour sync window, one point per minute
FIVE_MINUTE_POINTS = MINUTES // 5


def _series(**overrides: list[float] | None) -> list[MetricSeries]:
    """A healthy t3.micro serving ~60 requests per minute. An override replaces a signal's
    values; None removes the signal (CloudWatch returned nothing: a data gap)."""
    values: dict[str, list[float] | None] = {
        "cpu_utilization": [1.0] * FIVE_MINUTE_POINTS,
        "cpu_credit_balance": [40.0] * FIVE_MINUTE_POINTS,
        "memory_used": [24.0] * MINUTES,
        "status_check_failed": [0.0] * MINUTES,
        "latency_p95": [4.0] * MINUTES,
        "request_rate": [60.0] * MINUTES,
        "error_rate_5xx": [0.0] * MINUTES,
    }
    values.update(overrides)
    units = {
        "cpu_credit_balance": "credits",
        "status_check_failed": "count",
        "latency_p95": "ms",
        "request_rate": "per_minute",
    }
    five_minute = {"cpu_utilization", "cpu_credit_balance"}
    return [
        make_series(
            v,
            period=300 if name in five_minute else 60,
            signal=name,  # type: ignore[arg-type]
            unit=units.get(name, "percent"),  # type: ignore[arg-type]
        )
        for name, v in values.items()
        if v is not None
    ]


def _incident(
    series: list[MetricSeries], origin: DataOrigin, events: list[OpsEvent] | None = None
) -> Incident:
    resource = Resource(
        id="r-1",
        name="workload-01",
        region="eu-west-3",
        state="running",
        instance_type="t3.micro",
        credit_mode="standard",
        data_origin=origin,
    )
    snapshot = ObservationSnapshot(
        collected_at=NOW,
        window_start=NOW - timedelta(hours=3),
        window_end=NOW,
        data_origin=origin,
        resources=[resource],
        series=series,
        events=events or [],
    )
    [incident] = engine.evaluate(snapshot, [], NOW, lambda: "INC-0001").opened
    return incident


LOW_CREDITS = [0.0] * FIVE_MINUTE_POINTS
ERROR_SPIKE = [0.0] * (MINUTES - 11) + [21.0] * 11  # INC-0001: 11 minutes, peak 21.1%


def case_a_low_credits_and_5xx() -> Incident:
    """A. Low credits + high 5xx, CPU near zero, no deployment data. Nothing links them."""
    return _incident(_series(cpu_credit_balance=LOW_CREDITS, error_rate_5xx=ERROR_SPIKE), "aws")


def case_b_5xx_with_normal_cpu() -> Incident:
    """B. High 5xx; every CPU signal, credits included, is normal."""
    return _incident(_series(error_rate_5xx=ERROR_SPIKE), "aws")


def case_c_low_credits_only() -> Incident:
    """C. Low credits, no error-rate breach: no evidence of customer-facing impact."""
    return _incident(_series(cpu_credit_balance=LOW_CREDITS), "aws")


def case_d_status_check_failing() -> Incident:
    """D. Direct evidence: the EC2 status check is failing; every other signal is normal.
    A confident reading of that single fact must stay possible."""
    failing = [0.0] * (MINUTES - 10) + [1.0] * 10
    return _incident(_series(status_check_failed=failing), "simulated")


def case_e_gaps_and_no_deployment_data() -> Incident:
    """E. High 5xx, memory and status-check data missing, no deployment data, and a
    conflicting picture (fast responses while erroring)."""
    return _incident(
        _series(error_rate_5xx=ERROR_SPIKE, memory_used=None, status_check_failed=None), "aws"
    )


CASES = {
    "A": case_a_low_credits_and_5xx,
    "B": case_b_5xx_with_normal_cpu,
    "C": case_c_low_credits_only,
    "D": case_d_status_check_failing,
    "E": case_e_gaps_and_no_deployment_data,
}

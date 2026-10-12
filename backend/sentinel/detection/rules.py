"""Detection rules. Pure functions: series in, RuleResult out. No I/O, no clock.

A rule answers one question: "is this condition active right now, and since when?"
It only looks at the *trailing* run of breaching datapoints, i.e. the breach that is still
ongoing at the latest datapoint. A breach that already ended is not an active condition.

Every rule also says why it did NOT trigger, so the engine can record what was checked
(within_normal facts) and what could not be checked (data_gap facts).
"""

import statistics
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from sentinel.detection import thresholds as th
from sentinel.domain.observations import MetricPoint, MetricSeries, Resource, SignalName

NotTriggeredReason = Literal[
    "insufficient_data",  # signal missing, or too little history (e.g. no latency baseline)
    "insufficient_traffic",  # too few requests for a percentage or percentile to mean much
    "not_applicable",  # the rule does not apply to this resource (e.g. not a T instance)
    "below_threshold",  # the latest datapoint is not breaching
    "too_short",  # breaching now, but not for long enough yet
]


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    resource_id: str
    triggered: bool
    reason: NotTriggeredReason | None = None
    # The signal the rule looked at (or, for a data gap, the signal that was missing).
    # None only for the derived rule C-USER-IMPACT, which has no signal of its own.
    signal: SignalName | None = None
    breach_start: datetime | None = None
    breach_end: datetime | None = None  # end of the last breaching period
    duration: timedelta | None = None
    peak: float | None = None  # most extreme value in the breach (lowest for "<=" rules)
    latest: float | None = None
    threshold: float | None = None
    baseline: float | None = None  # R-LAT only
    lower_tier: bool = False  # R-5XX only: 2-5% band. severity.py decides what it means.


# Registry, in the order the engine evaluates and reports rules.
RULE_IDS = [
    "R-CPU-SAT",
    "R-CPU-CREDIT",
    "R-MEM",
    "R-STATUS",
    "R-5XX",
    "R-LAT",
    "C-USER-IMPACT",
]


def trailing_run(
    points: list[MetricPoint], is_breach: Callable[[float], bool], period_seconds: int
) -> list[MetricPoint]:
    """Return the consecutive breaching datapoints that end at the latest datapoint.

    A gap larger than one period breaks the run: missing data is never assumed to be a breach.
    """
    run: list[MetricPoint] = []
    for point in reversed(points):
        if not is_breach(point.v):
            break
        if run and (run[-1].t - point.t) > timedelta(seconds=period_seconds):
            break
        run.append(point)
    run.reverse()
    return run


def _threshold_rule(
    series: MetricSeries | None,
    rule_id: str,
    resource_id: str,
    signal: SignalName,
    threshold: float,
    *,
    below: bool = False,
    min_duration: timedelta | None = None,
    min_datapoints: int | None = None,
) -> RuleResult:
    """Shared logic: "signal >= threshold (or <= if below) for long enough, still ongoing"."""
    base = RuleResult(rule_id, resource_id, triggered=False, signal=signal, threshold=threshold)
    if series is None or not series.points:
        return replace(base, reason="insufficient_data")

    latest = series.points[-1].v

    def is_breach(v: float) -> bool:
        return v <= threshold if below else v >= threshold

    run = trailing_run(series.points, is_breach, series.period_seconds)
    if not run:
        return replace(base, reason="below_threshold", latest=latest)

    # Each datapoint represents one whole period, so N datapoints cover N periods.
    period = timedelta(seconds=series.period_seconds)
    values = [p.v for p in run]
    result = replace(
        base,
        breach_start=run[0].t,
        breach_end=run[-1].t + period,
        duration=(run[-1].t - run[0].t) + period,
        peak=min(values) if below else max(values),
        latest=latest,
    )
    assert result.duration is not None
    too_short = (min_duration is not None and result.duration < min_duration) or (
        min_datapoints is not None and len(run) < min_datapoints
    )
    if too_short:
        return replace(result, reason="too_short")
    return replace(result, triggered=True)


def _requests_during(requests: MetricSeries | None, start: datetime, end: datetime) -> float | None:
    """Total requests in [start, end), or None if there is no request data for that window.

    No datapoints means unknown traffic, not zero traffic.
    """
    if requests is None:
        return None
    in_window = [p for p in requests.points if start <= p.t < end]
    if not in_window:
        return None
    minutes_per_point = requests.period_seconds / 60
    return sum(p.v * minutes_per_point for p in in_window)


def _traffic_guard(result: RuleResult, requests: MetricSeries | None) -> RuleResult:
    """Applied to a triggered R-5XX / R-LAT result: too little traffic means no verdict."""
    assert result.breach_start and result.breach_end
    total = _requests_during(requests, result.breach_start, result.breach_end)
    if total is None:
        return replace(result, triggered=False, reason="insufficient_data", signal="request_rate")
    if total < th.MIN_REQUESTS:
        return replace(result, triggered=False, reason="insufficient_traffic")
    return result


def cpu_saturation(series: MetricSeries | None, resource_id: str) -> RuleResult:
    """R-CPU-SAT: CPU >= 90% for at least 10 minutes, still ongoing."""
    return _threshold_rule(
        series,
        "R-CPU-SAT",
        resource_id,
        "cpu_utilization",
        th.CPU_SAT_THRESHOLD_PERCENT,
        min_duration=th.CPU_SAT_MIN_DURATION,
    )


def is_burstable(instance_type: str) -> bool:
    """T-family instances (t2, t3, t3a, t4g) earn and spend CPU credits."""
    return instance_type.split(".")[0].startswith("t")


def cpu_credit_exhaustion(series: MetricSeries | None, resource: Resource) -> RuleResult:
    """R-CPU-CREDIT: credit balance <= 5 for 2 datapoints on a standard-mode T instance.

    In standard mode an instance with no credits is throttled to its baseline CPU.
    In unlimited mode it keeps bursting (and pays for it), so the rule does not apply.
    """
    rule_id = "R-CPU-CREDIT"
    if not is_burstable(resource.instance_type) or resource.credit_mode != "standard":
        return RuleResult(
            rule_id,
            resource.id,
            triggered=False,
            reason="not_applicable",
            signal="cpu_credit_balance",
        )
    return _threshold_rule(
        series,
        rule_id,
        resource.id,
        "cpu_credit_balance",
        th.CPU_CREDIT_THRESHOLD,
        below=True,
        min_datapoints=th.CPU_CREDIT_MIN_DATAPOINTS,
    )


def memory_pressure(series: MetricSeries | None, resource_id: str) -> RuleResult:
    """R-MEM: memory used >= 90% for at least 10 minutes, still ongoing.

    Memory is not a default EC2 metric: it needs the CloudWatch agent. Without it the
    rule reports insufficient_data, which becomes a data_gap fact, never a 0% reading.
    """
    return _threshold_rule(
        series,
        "R-MEM",
        resource_id,
        "memory_used",
        th.MEM_THRESHOLD_PERCENT,
        min_duration=th.MEM_MIN_DURATION,
    )


def status_check_failed(series: MetricSeries | None, resource_id: str) -> RuleResult:
    """R-STATUS: EC2 status check failed in at least 2 consecutive datapoints."""
    return _threshold_rule(
        series,
        "R-STATUS",
        resource_id,
        "status_check_failed",
        th.STATUS_FAILED_THRESHOLD,
        min_datapoints=th.STATUS_MIN_DATAPOINTS,
    )


def error_rate_5xx(
    errors: MetricSeries | None, requests: MetricSeries | None, resource_id: str
) -> RuleResult:
    """R-5XX: 5xx rate >= 2% for at least 5 minutes with >= 50 requests in that time.

    If >= 5% has itself lasted 5 minutes, the result is the full tier (severity high);
    otherwise it is the lower tier (severity medium).
    """
    rule_id = "R-5XX"
    lower = _threshold_rule(
        errors,
        rule_id,
        resource_id,
        "error_rate_5xx",
        th.ERR_5XX_MEDIUM_PERCENT,
        min_duration=th.ERR_5XX_MIN_DURATION,
    )
    if not lower.triggered:
        return lower
    lower = _traffic_guard(lower, requests)
    if not lower.triggered:
        return lower

    full = _threshold_rule(
        errors,
        rule_id,
        resource_id,
        "error_rate_5xx",
        th.ERR_5XX_HIGH_PERCENT,
        min_duration=th.ERR_5XX_MIN_DURATION,
    )
    # The >= 5% run is shorter than the >= 2% run, so the traffic guard is checked again
    # on its own window.
    if full.triggered and _traffic_guard(full, requests).triggered:
        return full
    return replace(lower, lower_tier=True)


def latency_p95(
    latency: MetricSeries | None, requests: MetricSeries | None, resource_id: str
) -> RuleResult:
    """R-LAT: p95 >= 3x its own baseline and >= 500 ms for at least 5 minutes.

    The baseline depends on when the breach started, and the breach depends on the
    baseline. To break the circle:
      1. find the trailing run at the absolute floor (>= 500 ms);
      2. baseline = median of [run start - 70 min, run start - 10 min), at least 30 min of data;
      3. the breach is the trailing run at max(500 ms, 3 x baseline).
    """
    rule_id = "R-LAT"
    candidate = _threshold_rule(
        latency,
        rule_id,
        resource_id,
        "latency_p95",
        th.LAT_MIN_MS,
        min_duration=th.LAT_MIN_DURATION,
    )
    if not candidate.triggered:
        return candidate  # the final run is a sub-run of this one, so it cannot trigger either

    assert latency is not None and candidate.breach_start is not None
    start = candidate.breach_start
    window = [
        p.v
        for p in latency.points
        if start - th.LAT_BASELINE_FROM <= p.t < start - th.LAT_BASELINE_TO
    ]
    covered = timedelta(seconds=len(window) * latency.period_seconds)
    if covered < th.LAT_MIN_BASELINE_DATA:
        # Without a baseline "3x normal" is unknowable: report a gap, not a verdict.
        return RuleResult(
            rule_id,
            resource_id,
            triggered=False,
            reason="insufficient_data",
            signal="latency_p95",
            latest=candidate.latest,
        )

    baseline = statistics.median(window)
    threshold = max(th.LAT_MIN_MS, th.LAT_BASELINE_MULTIPLIER * baseline)
    result = _threshold_rule(
        latency,
        rule_id,
        resource_id,
        "latency_p95",
        threshold,
        min_duration=th.LAT_MIN_DURATION,
    )
    result = replace(result, baseline=baseline)
    if not result.triggered:
        return result
    return _traffic_guard(result, requests)


def user_impact(results: list[RuleResult], resource_id: str) -> RuleResult:
    """C-USER-IMPACT: R-LAT and R-5XX both active on the same resource.

    Derived from other rules, not from a signal. When it does not trigger, its reason is
    below_threshold, meaning "its component rules are not both active".
    """
    active = {r.rule_id for r in results if r.triggered}
    triggered = {"R-LAT", "R-5XX"} <= active
    return RuleResult(
        "C-USER-IMPACT",
        resource_id,
        triggered=triggered,
        reason=None if triggered else "below_threshold",
    )


def evaluate_resource(
    resource: Resource, series: dict[SignalName, MetricSeries]
) -> list[RuleResult]:
    """Run every rule against one resource. The order matches RULE_IDS."""
    requests = series.get("request_rate")
    results = [
        cpu_saturation(series.get("cpu_utilization"), resource.id),
        cpu_credit_exhaustion(series.get("cpu_credit_balance"), resource),
        memory_pressure(series.get("memory_used"), resource.id),
        status_check_failed(series.get("status_check_failed"), resource.id),
        error_rate_5xx(series.get("error_rate_5xx"), requests, resource.id),
        latency_p95(series.get("latency_p95"), requests, resource.id),
    ]
    results.append(user_impact(results, resource.id))
    return results


# How each signal-based rule's condition is re-checked when deciding whether it has cleared:
# rule id -> (signal, threshold, breaches when value <= threshold).
# R-LAT's threshold depends on its baseline, so it comes from the incident's own fact.
# R-5XX clears below its lower tier (2%), not below 5%.
RULE_CONDITIONS: dict[str, tuple[SignalName, float | None, bool]] = {
    "R-CPU-SAT": ("cpu_utilization", th.CPU_SAT_THRESHOLD_PERCENT, False),
    "R-CPU-CREDIT": ("cpu_credit_balance", th.CPU_CREDIT_THRESHOLD, True),
    "R-MEM": ("memory_used", th.MEM_THRESHOLD_PERCENT, False),
    "R-STATUS": ("status_check_failed", th.STATUS_FAILED_THRESHOLD, False),
    "R-5XX": ("error_rate_5xx", th.ERR_5XX_MEDIUM_PERCENT, False),
    "R-LAT": ("latency_p95", None, False),
}


@dataclass(frozen=True)
class Clearance:
    """How long a rule's condition has been continuously clear, up to the latest datapoint."""

    rule_id: str
    signal: SignalName
    threshold: float
    clean_since: datetime | None  # None: not clean at the latest datapoint, or no data
    duration: timedelta
    latest: float | None

    @property
    def cleared(self) -> bool:
        return self.duration >= th.RESOLVE_CLEAN_DURATION


def clearance(series: MetricSeries | None, rule_id: str, threshold: float) -> Clearance:
    """Missing data is never clean: without datapoints the condition is not cleared.

    A gap breaks the clean run exactly like it breaks a breach run.
    """
    signal, _, below = RULE_CONDITIONS[rule_id]
    not_clear = Clearance(rule_id, signal, threshold, None, timedelta(0), None)
    if series is None or not series.points:
        return not_clear

    def is_clean(v: float) -> bool:
        return v > threshold if below else v < threshold

    run = trailing_run(series.points, is_clean, series.period_seconds)
    latest = series.points[-1].v
    if not run:
        return replace(not_clear, latest=latest)
    period = timedelta(seconds=series.period_seconds)
    return Clearance(
        rule_id,
        signal,
        threshold,
        clean_since=run[0].t,
        duration=(run[-1].t - run[0].t) + period,
        latest=latest,
    )

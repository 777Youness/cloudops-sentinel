"""Detection rules. Pure functions: series in, RuleResult out. No I/O, no clock.

A rule answers one question: "is this condition active right now, and since when?"
It only looks at the *trailing* run of breaching datapoints, i.e. the breach that is still
ongoing at the latest datapoint. A breach that already ended is not an active condition.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sentinel.detection import thresholds
from sentinel.domain.observations import MetricPoint, MetricSeries

NotTriggeredReason = Literal["insufficient_data", "below_threshold", "too_short"]


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    resource_id: str
    triggered: bool
    reason: NotTriggeredReason | None = None
    breach_start: datetime | None = None
    breach_end: datetime | None = None  # end of the last breaching period
    duration: timedelta | None = None
    peak: float | None = None
    latest: float | None = None


def trailing_breach(
    points: list[MetricPoint], threshold: float, period_seconds: int
) -> list[MetricPoint]:
    """Return the consecutive datapoints >= threshold that end at the latest datapoint.

    A gap larger than one period breaks the run: missing data is never assumed to be a breach.
    """
    run: list[MetricPoint] = []
    for point in reversed(points):
        if point.v < threshold:
            break
        if run and (run[-1].t - point.t) > timedelta(seconds=period_seconds):
            break
        run.append(point)
    run.reverse()
    return run


def cpu_saturation(series: MetricSeries | None, resource_id: str) -> RuleResult:
    """R-CPU-SAT: CPU >= 90% for at least 10 minutes, still ongoing."""
    rule_id = "R-CPU-SAT"
    if series is None or not series.points:
        return RuleResult(rule_id, resource_id, triggered=False, reason="insufficient_data")

    latest = series.points[-1].v
    run = trailing_breach(
        series.points, thresholds.CPU_SAT_THRESHOLD_PERCENT, series.period_seconds
    )
    if not run:
        return RuleResult(
            rule_id, resource_id, triggered=False, reason="below_threshold", latest=latest
        )

    # Each datapoint represents one whole period, so N datapoints cover N periods.
    period = timedelta(seconds=series.period_seconds)
    duration = (run[-1].t - run[0].t) + period
    peak = max(p.v for p in run)
    common = dict(
        breach_start=run[0].t,
        breach_end=run[-1].t + period,
        duration=duration,
        peak=peak,
        latest=latest,
    )
    if duration < thresholds.CPU_SAT_MIN_DURATION:
        return RuleResult(rule_id, resource_id, triggered=False, reason="too_short", **common)
    return RuleResult(rule_id, resource_id, triggered=True, **common)


# Registry used by the engine. Day 1 has one rule.
RULE_IDS = ["R-CPU-SAT"]

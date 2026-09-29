from datetime import UTC, datetime, timedelta

import pytest

from sentinel.clock import FixedClock
from sentinel.domain.observations import MetricPoint, MetricSeries

NOW = datetime(2026, 9, 23, 14, 5, 30, tzinfo=UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


def make_series(values: list[float], end: datetime | None = None, period: int = 60) -> MetricSeries:
    """Build a cpu_utilization series whose last point is at `end` (default: 14:05 UTC)."""
    end = end or NOW.replace(second=0)
    n = len(values)
    points = [
        MetricPoint(t=end - timedelta(seconds=(n - 1 - i) * period), v=v)
        for i, v in enumerate(values)
    ]
    return MetricSeries(
        resource_id="r-1",
        signal="cpu_utilization",
        unit="percent",
        statistic="Average",
        period_seconds=period,
        source="test",
        points=points,
    )

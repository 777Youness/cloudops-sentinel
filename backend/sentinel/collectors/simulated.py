"""Simulated telemetry: replays scenario files as if they were happening now.

Each scenario describes one fake resource and the shape of its signals relative to "now"
(minute offsets: -20 means "20 minutes ago", 0 means "the latest complete period").
Noise comes from a seeded random generator, so the same scenario and the same clock always
produce exactly the same data.
"""

import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from sentinel.clock import Clock
from sentinel.domain.observations import (
    MetricPoint,
    MetricSeries,
    ObservationSnapshot,
    Resource,
    SignalName,
    Statistic,
    Unit,
)
from sentinel.domain.system import CollectorName

SIGNAL_UNITS: dict[SignalName, Unit] = {
    "cpu_utilization": "percent",
    "cpu_credit_balance": "credits",
    "memory_used": "percent",
    "status_check_failed": "count",
    "latency_p95": "ms",
    "error_rate_5xx": "percent",
    "request_rate": "per_minute",
}

# The CloudWatch statistic AWS mode will request for each signal, so simulated series
# look like the real ones.
SIGNAL_STATISTICS: dict[SignalName, Statistic] = {
    "cpu_utilization": "Average",
    "cpu_credit_balance": "Average",
    "memory_used": "Average",
    "status_check_failed": "Maximum",
    "latency_p95": "p95",
    "error_rate_5xx": "Average",
    "request_rate": "Average",
}


class Segment(BaseModel):
    from_min: int = Field(le=0)
    to_min: int = Field(le=0)
    value: float


class SignalSpec(BaseModel):
    baseline: float
    noise: float = 0.0
    segments: list[Segment] = []


class ScenarioResource(BaseModel):
    id: str
    name: str
    instance_type: str = "t3.micro"
    credit_mode: Literal["standard", "unlimited"] | None = "standard"


class ScenarioExpectation(BaseModel):
    """What the scenario is designed to produce. Used only by tests."""

    incident: bool
    rules: list[str] = []
    severity: Literal["low", "medium", "high", "critical"] | None = None
    # Rules that must NOT trigger, with the reason they must report (rule id -> reason).
    reasons: dict[str, str] = {}


class Scenario(BaseModel):
    id: str
    title: str
    resource: ScenarioResource
    period_seconds: int = 60
    history_minutes: int = 90
    seed: int = 0
    signals: dict[SignalName, SignalSpec]
    expected: ScenarioExpectation


def load_scenarios(directory: Path) -> list[Scenario]:
    """Load and validate every *.yaml file. A malformed file fails loudly at startup."""
    scenarios = []
    for path in sorted(directory.glob("*.yaml")):
        with path.open() as f:
            raw = yaml.safe_load(f)
        try:
            scenarios.append(Scenario.model_validate(raw))
        except Exception as exc:  # re-raise with the file name, which pydantic doesn't know
            raise ValueError(f"Invalid scenario file {path.name}: {exc}") from exc
    return scenarios


def _latest_complete_period(now: datetime, period_seconds: int) -> datetime:
    """Floor 'now' to the period boundary, like CloudWatch's latest complete datapoint."""
    epoch = int(now.timestamp())
    floored = epoch - (epoch % period_seconds)
    return datetime.fromtimestamp(floored, tz=now.tzinfo)


def generate_series(scenario: Scenario, now: datetime) -> list[MetricSeries]:
    end = _latest_complete_period(now, scenario.period_seconds)
    steps = scenario.history_minutes * 60 // scenario.period_seconds
    rng = random.Random(scenario.seed)
    series = []
    for signal, spec in scenario.signals.items():
        points = []
        for i in range(steps, -1, -1):
            t = end - timedelta(seconds=i * scenario.period_seconds)
            offset_min = -(i * scenario.period_seconds) / 60
            value = spec.baseline
            for seg in spec.segments:
                if seg.from_min <= offset_min <= seg.to_min:
                    value = seg.value
            value += rng.uniform(-spec.noise, spec.noise)
            unit = SIGNAL_UNITS[signal]
            value = max(0.0, value)  # noise must not create impossible negative readings
            if unit == "percent":
                value = min(100.0, value)
            points.append(MetricPoint(t=t, v=round(value, 2)))
        series.append(
            MetricSeries(
                resource_id=scenario.resource.id,
                signal=signal,
                unit=SIGNAL_UNITS[signal],
                statistic=SIGNAL_STATISTICS[signal],
                period_seconds=scenario.period_seconds,
                source="simulator",
                points=points,
            )
        )
    return series


class SimulatedSource:
    name: CollectorName = "simulator"
    data_origin = "simulated"

    def __init__(
        self,
        scenarios: list[Scenario],
        clock: Clock,
        region: str,
        latency_seconds: float = 0.0,
    ) -> None:
        self._scenarios = scenarios
        self._clock = clock
        self._region = region
        self._latency_seconds = latency_seconds

    def collect(self, window_start: datetime, window_end: datetime) -> ObservationSnapshot:
        if self._latency_seconds:
            time.sleep(self._latency_seconds)  # dev aid, see config.simulated_latency_seconds
        now = self._clock.now()
        resources: list[Resource] = []
        all_series: list[MetricSeries] = []
        for scenario in self._scenarios:
            resources.append(
                Resource(
                    id=scenario.resource.id,
                    name=scenario.resource.name,
                    region=self._region,
                    state="running",
                    instance_type=scenario.resource.instance_type,
                    credit_mode=scenario.resource.credit_mode,
                    tags={"cloudops-sentinel:scenario": scenario.id},
                    data_origin="simulated",
                )
            )
            for s in generate_series(scenario, now):
                s.points = [p for p in s.points if window_start <= p.t <= window_end]
                all_series.append(s)
        return ObservationSnapshot(
            collected_at=now,
            window_start=window_start,
            window_end=window_end,
            data_origin="simulated",
            resources=resources,
            series=all_series,
        )

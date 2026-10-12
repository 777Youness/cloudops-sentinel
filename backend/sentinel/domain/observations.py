"""Observations: what collectors return. Normalized data, no judgement.

Both the simulator and (from Day 5) the AWS collector produce exactly these shapes,
so everything downstream is unaware of where the data came from.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

DataOrigin = Literal["simulated", "aws"]

# V1 signal vocabulary.
SignalName = Literal[
    "cpu_utilization",
    "cpu_credit_balance",
    "memory_used",
    "status_check_failed",
    "latency_p95",
    "error_rate_5xx",
    "request_rate",
]

Unit = Literal["percent", "credits", "count", "ms", "per_minute"]
Statistic = Literal["Average", "Maximum", "p95", "Sum"]
InstanceState = Literal["pending", "running", "stopping", "stopped", "terminated", "unknown"]


class Resource(BaseModel):
    id: str
    kind: Literal["ec2_instance"] = "ec2_instance"
    name: str
    region: str
    state: InstanceState
    instance_type: str
    credit_mode: Literal["standard", "unlimited"] | None = None
    tags: dict[str, str] = {}
    data_origin: DataOrigin


class MetricPoint(BaseModel):
    t: AwareDatetime
    v: float


class MetricSeries(BaseModel):
    """One signal for one resource.

    Points are ordered oldest to newest and contain complete periods only.
    A missing period stays missing: it is never filled with 0.
    """

    resource_id: str
    signal: SignalName
    unit: Unit
    statistic: Statistic
    period_seconds: int
    source: str
    points: list[MetricPoint]


EventKind = Literal["deployment"]


class OpsEvent(BaseModel):
    """Something a human or a pipeline did to a resource, e.g. a deployment.

    An event is an observation, not a judgement: code never claims an event caused an
    incident. `id` is stable across syncs, so the same event is never recorded twice.
    """

    id: str
    resource_id: str
    kind: EventKind
    at: AwareDatetime
    label: str
    source: str
    data_origin: DataOrigin


class ObservationSnapshot(BaseModel):
    collected_at: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    data_origin: DataOrigin
    resources: list[Resource]
    series: list[MetricSeries]
    events: list[OpsEvent] = []

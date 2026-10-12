"""Resource health: a judgement, so it lives in detection/ (pure: no I/O, no clock).

    crit     open incident of severity high or critical
    warn     open incident of severity medium or low
    unknown  no open incident and no datapoint at all for the resource
    ok       datapoints present and no open incident

An open incident decides first: a resource with a known problem is not "unknown" just
because its data stopped. Missing signals are always listed alongside the state.
"""

from sentinel.detection.rules import is_burstable
from sentinel.domain.incidents import Incident
from sentinel.domain.observations import MetricSeries, Resource, SignalName
from sentinel.domain.overview import HealthState, ResourceHealth

# The V1 signals every monitored instance should report, in display order.
V1_SIGNALS: list[SignalName] = [
    "cpu_utilization",
    "cpu_credit_balance",
    "memory_used",
    "status_check_failed",
    "request_rate",
    "error_rate_5xx",
    "latency_p95",
]


def expected_signals(resource: Resource) -> list[SignalName]:
    """CPU credits only exist on burstable (T-family) instances."""
    return [
        s for s in V1_SIGNALS if s != "cpu_credit_balance" or is_burstable(resource.instance_type)
    ]


def resource_health(
    resource: Resource, series: list[MetricSeries], open_incident: Incident | None
) -> ResourceHealth:
    with_data = {s.signal: s for s in series if s.resource_id == resource.id and s.points}
    expected = expected_signals(resource)
    missing = [s for s in expected if s not in with_data]
    last_points = [s.points[-1].t for s in with_data.values()]

    health: HealthState
    if open_incident is not None:
        health = "crit" if open_incident.severity in ("high", "critical") else "warn"
    elif not with_data:
        health = "unknown"
    else:
        health = "ok"

    return ResourceHealth(
        resource_id=resource.id,
        resource_name=resource.name,
        instance_type=resource.instance_type,
        state=resource.state,
        data_origin=resource.data_origin,
        health=health,
        open_incident_id=open_incident.id if open_incident else None,
        open_incident_severity=open_incident.severity if open_incident else None,
        signals_expected=expected,
        signals_missing=missing,
        last_datapoint_at=max(last_points) if last_points else None,
    )

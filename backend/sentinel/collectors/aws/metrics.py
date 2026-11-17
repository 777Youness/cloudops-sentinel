"""CloudWatch metrics for the monitored instances, in ONE batched GetMetricData call.

Call: cloudwatch:GetMetricData (allowed by sentinel-readonly.json, region-pinned). It is
billed per metric requested ($0.01 per 1,000 in eu-west-3, docs/cost.md): one sync asks
for at most 4 metrics per instance, only over the sync window.

The same semantics as the simulator (and as detection expects):
  - a datapoint timestamped T covers [T, T + period); only COMPLETE periods are kept;
  - a period CloudWatch has no value for stays missing (never 0, never interpolated);
  - anything other than StatusCode "Complete" makes the collector "degraded".
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sentinel.collectors.aws.ec2 import is_burstable
from sentinel.domain.observations import (
    MetricPoint,
    MetricSeries,
    Resource,
    SignalName,
    Statistic,
    Unit,
)

# GetMetricData accepts at most 500 queries per request.
MAX_QUERIES_PER_CALL = 500


@dataclass(frozen=True)
class MetricSpec:
    signal: SignalName
    namespace: str
    metric_name: str
    statistic: Statistic
    period_seconds: int
    unit: Unit
    burstable_only: bool = False


# EC2 basic monitoring (no detailed monitoring, CLAUDE.md) publishes CPUUtilization every
# 5 minutes, and CPU credit metrics "at a 5-minute frequency only"; StatusCheckFailed "is
# available at a 1-minute frequency at no charge" (EC2 user guide, "CloudWatch metrics that
# are available for your instances", checked 2026-11-17). Memory comes from the CloudWatch
# agent (templates/cloudwatch-agent.json.tftpl), every 60 s, InstanceId only.
METRICS = [
    MetricSpec("cpu_utilization", "AWS/EC2", "CPUUtilization", "Average", 300, "percent"),
    MetricSpec(
        "cpu_credit_balance", "AWS/EC2", "CPUCreditBalance", "Average", 300, "credits", True
    ),
    MetricSpec("status_check_failed", "AWS/EC2", "StatusCheckFailed", "Maximum", 60, "count"),
    MetricSpec("memory_used", "CWAgent", "mem_used_percent", "Average", 60, "percent"),
]


@dataclass
class MetricsResult:
    series: list[MetricSeries]
    problems: list[str]  # non-empty: the collector is degraded (partial data)


def _floor(t: datetime, seconds: int) -> datetime:
    epoch = int(t.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=t.tzinfo)


def build_queries(resources: list[Resource]) -> list[tuple[str, Resource, MetricSpec, dict]]:
    """(query id, resource, spec, MetricDataQuery) for every running/stopped instance."""
    queries = []
    for r_index, resource in enumerate(resources):
        for m_index, spec in enumerate(METRICS):
            if spec.burstable_only and not is_burstable(resource.instance_type):
                continue
            query_id = f"m{r_index}_{m_index}"  # ids: lowercase start, [a-zA-Z0-9_]
            queries.append(
                (
                    query_id,
                    resource,
                    spec,
                    {
                        "Id": query_id,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": spec.namespace,
                                "MetricName": spec.metric_name,
                                "Dimensions": [{"Name": "InstanceId", "Value": resource.id}],
                            },
                            "Period": spec.period_seconds,
                            "Stat": spec.statistic,
                        },
                        "ReturnData": True,
                    },
                )
            )
    return queries


def collect_metrics(
    cloudwatch: Any, resources: list[Resource], window_start: datetime, now: datetime
) -> MetricsResult:
    """Raises on an AWS error (the caller marks the collector failed)."""
    queries = build_queries(resources)
    if not queries:
        return MetricsResult(series=[], problems=[])
    # Aligned to the longest period so 5-minute buckets start on the hour boundaries.
    start = _floor(window_start, 300)
    end = _floor(now, 60)
    by_id = {q[0]: q for q in queries}
    points: dict[str, list[MetricPoint]] = {q[0]: [] for q in queries}
    problems: list[str] = []

    for offset in range(0, len(queries), MAX_QUERIES_PER_CALL):
        batch = [q[3] for q in queries[offset : offset + MAX_QUERIES_PER_CALL]]
        kwargs: dict[str, Any] = {
            "MetricDataQueries": batch,
            "StartTime": start,
            "EndTime": end,
            "ScanBy": "TimestampAscending",
        }
        while True:
            response = cloudwatch.get_metric_data(**kwargs)
            for result in response.get("MetricDataResults", []):
                query_id, resource, spec, _ = by_id[result["Id"]]
                status = result.get("StatusCode", "Complete")
                if status != "Complete":
                    problems.append(f"{resource.id} {spec.metric_name}: {status}")
                period = timedelta(seconds=spec.period_seconds)
                for t, v in zip(
                    result.get("Timestamps", []), result.get("Values", []), strict=True
                ):
                    if t + period <= now:  # the period still running is incomplete: drop it
                        points[query_id].append(MetricPoint(t=t, v=float(v)))
            problems += [m.get("Value", "") for m in response.get("Messages", [])]
            token = response.get("NextToken")
            if not token:
                break
            kwargs["NextToken"] = token

    series = []
    for query_id, resource, spec, _ in queries:
        found = sorted(points[query_id], key=lambda p: p.t)
        if not found:
            continue  # no data: the rules see a missing signal (data_gap), never 0
        series.append(
            MetricSeries(
                resource_id=resource.id,
                signal=spec.signal,
                unit=spec.unit,
                statistic=spec.statistic,
                period_seconds=spec.period_seconds,
                source=f"cloudwatch:{spec.namespace}/{spec.metric_name}",
                points=found,
            )
        )
    return MetricsResult(series=series, problems=[p for p in problems if p])

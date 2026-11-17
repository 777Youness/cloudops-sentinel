"""request_rate, error_rate_5xx and latency_p95 from the workload's access log.

The app (workload/app.py) writes one JSON line per request; the CloudWatch agent ships it
to the log group with the instance id as the log stream name. Two Logs Insights queries
aggregate it per instance and per minute:

    traffic: requests and p95 latency      errors: requests with status >= 500

Calls: logs:StartQuery, logs:GetQueryResults, logs:StopQuery (allowed by
sentinel-readonly.json on the workload log group; StartQuery/StopQuery are the two named
exceptions to the read-only verb rule, CLAUDE.md principle 4).

Cost control: Logs Insights is billed per GB scanned ($0.0059 in eu-west-3,
docs/cost.md). Each query covers exactly the sync window of one log group, returns at
most QUERY_LIMIT rows, and is stopped if it runs longer than the timeout.

Missing vs zero: a minute without any log line has no row, so it stays MISSING, never
"0 requests": Sentinel cannot tell "no traffic" from "the agent stopped shipping".
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sentinel.domain.observations import MetricPoint, MetricSeries, Resource

TRAFFIC_QUERY = "stats count(*) as requests, pct(duration_ms, 95) as p95 by @logStream, bin(1m)"
ERRORS_QUERY = "filter status >= 500 | stats count(*) as errors by @logStream, bin(1m)"
QUERY_LIMIT = 1000  # 3 h x 60 min = 180 rows per instance per query
BIN_FIELD = "bin(1m)"
# The agent and CloudWatch Logs need a moment to deliver the latest lines: the last
# minutes would be undercounted, so they are left out (they become complete next sync).
INGESTION_DELAY = timedelta(minutes=2)
POLL_SECONDS = 1.0
FINAL_STATES = {"Complete", "Failed", "Cancelled", "Timeout", "Unknown"}
SOURCE = "cloudwatch-logs-insights"


class LogsQueryError(Exception):
    """A Logs Insights query did not complete (failed, cancelled, or timed out)."""


@dataclass
class LogsResult:
    series: list[MetricSeries]
    problems: list[str]  # non-empty: the collector is degraded (e.g. truncated results)


def _epoch(t: datetime) -> int:
    return int(t.timestamp())


def _run_query(
    logs: Any,
    log_group: str,
    query: str,
    start: datetime,
    end: datetime,
    timeout_seconds: float,
    sleep: Callable[[float], None],
) -> list[dict[str, str]]:
    query_id = logs.start_query(
        logGroupName=log_group,
        startTime=_epoch(start),
        endTime=_epoch(end),
        queryString=query,
        limit=QUERY_LIMIT,
    )["queryId"]
    waited = 0.0
    while True:
        response = logs.get_query_results(queryId=query_id)
        status = response.get("status", "Unknown")
        if status in FINAL_STATES:
            break
        if waited >= timeout_seconds:
            # Stop scanning (and paying) instead of abandoning a running query.
            logs.stop_query(queryId=query_id)
            raise LogsQueryError(f"Logs Insights query still {status} after {timeout_seconds:g}s")
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    if status != "Complete":
        raise LogsQueryError(f"Logs Insights query ended with status {status}")
    return [{f["field"]: f["value"] for f in row} for row in response.get("results", [])]


def _bin_time(value: str) -> datetime:
    """Logs Insights bins look like '2026-11-17 10:05:00.000' (UTC)."""
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def collect_log_signals(
    logs: Any,
    log_group: str,
    resources: list[Resource],
    window_start: datetime,
    now: datetime,
    timeout_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> LogsResult:
    """Raises on an AWS error or LogsQueryError (the caller marks the collector failed)."""
    if not resources:
        return LogsResult(series=[], problems=[])
    end = now - INGESTION_DELAY
    problems: list[str] = []
    traffic = _run_query(logs, log_group, TRAFFIC_QUERY, window_start, end, timeout_seconds, sleep)
    errors = _run_query(logs, log_group, ERRORS_QUERY, window_start, end, timeout_seconds, sleep)
    for name, rows in (("traffic", traffic), ("errors", errors)):
        if len(rows) >= QUERY_LIMIT:
            problems.append(f"{name} query returned {QUERY_LIMIT} rows: results may be cut")

    known = {r.id for r in resources}
    error_counts = {
        (row["@logStream"], row[BIN_FIELD]): float(row["errors"])
        for row in errors
        if row.get("@logStream") in known
    }
    per_resource: dict[str, dict[str, list[MetricPoint]]] = {}
    for row in traffic:
        stream = row.get("@logStream")
        if stream not in known or BIN_FIELD not in row:
            continue
        t = _bin_time(row[BIN_FIELD])
        if t + timedelta(minutes=1) > end:
            continue  # incomplete minute
        requests = float(row["requests"])
        if requests <= 0:
            continue
        signals = per_resource.setdefault(stream, {"rate": [], "errors": [], "p95": []})
        signals["rate"].append(MetricPoint(t=t, v=requests))
        # A minute with requests but no error row has 0 errors: that IS a measurement.
        errors_in_minute = error_counts.get((stream, row[BIN_FIELD]), 0.0)
        signals["errors"].append(MetricPoint(t=t, v=round(100 * errors_in_minute / requests, 3)))
        if row.get("p95") not in (None, ""):
            signals["p95"].append(MetricPoint(t=t, v=float(row["p95"])))

    series = []
    for resource_id, signals in sorted(per_resource.items()):
        for signal, key, unit, statistic in (
            ("request_rate", "rate", "per_minute", "Sum"),
            ("error_rate_5xx", "errors", "percent", "Average"),
            ("latency_p95", "p95", "ms", "p95"),
        ):
            points = sorted(signals[key], key=lambda p: p.t)
            if points:
                series.append(
                    MetricSeries(
                        resource_id=resource_id,
                        signal=signal,  # type: ignore[arg-type]
                        unit=unit,  # type: ignore[arg-type]
                        statistic=statistic,  # type: ignore[arg-type]
                        period_seconds=60,
                        source=SOURCE,
                        points=points,
                    )
                )
    return LogsResult(series=series, problems=problems)

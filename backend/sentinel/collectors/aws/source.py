"""The AWS telemetry source (Day 5, ADR 0018). Same interface as the simulator.

    discover instances (ec2)  ->  metrics (cloudwatch_metrics)  ->  access log (cloudwatch_logs)
                                                  \\_______________________/
                                                 one ObservationSnapshot, data_origin "aws"

Runs only inside POST /api/v1/sync (ADR 0003), with the read-only role's credentials.

Failure policy (never silently healthy):
  - discovery fails  -> CollectionError: the sync fails, nothing is evaluated or resolved;
  - metrics or logs fail -> that collector is "failed" in the snapshot and its signals are
    absent: detection records data gaps and no incident can resolve on missing data;
  - partial data (credit modes unknown, StatusCode PartialData, truncated query) ->
    the collector is "degraded" and the sync "partial".
"""

import time
from collections.abc import Callable
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError

from sentinel.clock import Clock
from sentinel.collectors.aws.clients import AwsClients, ClientsFactory
from sentinel.collectors.aws.ec2 import add_credit_modes, discover_instances
from sentinel.collectors.aws.errors import mask_account_ids, translate
from sentinel.collectors.aws.logs import LogsQueryError, collect_log_signals
from sentinel.collectors.aws.metrics import collect_metrics
from sentinel.collectors.base import CollectionError
from sentinel.domain.observations import MetricSeries, ObservationSnapshot
from sentinel.domain.system import CollectorError, CollectorName, CollectorStatus

AWS_ERRORS = (ClientError, BotoCoreError)


def _status(name: CollectorName, problems: list[str]) -> CollectorStatus:
    if not problems:
        return CollectorStatus(name=name, state="ok")
    message = mask_account_ids("; ".join(problems))[:300]
    return CollectorStatus(
        name=name,
        state="degraded",
        error=CollectorError(code="partial_data", message=message),
    )


class AwsSource:
    name: CollectorName = "ec2"
    data_origin = "aws"

    def __init__(
        self,
        clients_factory: ClientsFactory,
        clock: Clock,
        region: str,
        log_group: str,
        logs_timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clients_factory = clients_factory
        self._clock = clock
        self._region = region
        self._log_group = log_group
        self._logs_timeout_seconds = logs_timeout_seconds
        self._sleep = sleep

    def collect(self, window_start: datetime, window_end: datetime) -> ObservationSnapshot:
        try:
            clients: AwsClients = self._clients_factory()
            resources = discover_instances(clients.ec2, self._region)
        except AWS_ERRORS as exc:
            raise CollectionError("ec2", translate(exc, what="ec2:DescribeInstances")) from exc

        statuses: list[CollectorStatus] = []
        credit_error = add_credit_modes(clients.ec2, resources)
        if credit_error is None:
            statuses.append(CollectorStatus(name="ec2", state="ok"))
        else:
            statuses.append(CollectorStatus(name="ec2", state="degraded", error=credit_error))

        series: list[MetricSeries] = []
        now = self._clock.now()
        try:
            metrics = collect_metrics(clients.cloudwatch, resources, window_start, now)
            series += metrics.series
            statuses.append(_status("cloudwatch_metrics", metrics.problems))
        except AWS_ERRORS as exc:
            error = translate(exc, what="cloudwatch:GetMetricData")
            statuses.append(CollectorStatus(name="cloudwatch_metrics", state="failed", error=error))

        try:
            logs = collect_log_signals(
                clients.logs,
                self._log_group,
                resources,
                window_start,
                now,
                self._logs_timeout_seconds,
                self._sleep,
            )
            series += logs.series
            statuses.append(_status("cloudwatch_logs", logs.problems))
        except AWS_ERRORS as exc:
            error = translate(exc, what="logs:StartQuery/GetQueryResults")
            statuses.append(CollectorStatus(name="cloudwatch_logs", state="failed", error=error))
        except LogsQueryError as exc:
            error = CollectorError(
                code="query_incomplete",
                message=str(exc),
                hint="Logs Insights did not finish in time; it was stopped to bound cost. "
                "Sync again, or raise SENTINEL_AWS_LOGS_QUERY_TIMEOUT_SECONDS.",
            )
            statuses.append(CollectorStatus(name="cloudwatch_logs", state="failed", error=error))

        return ObservationSnapshot(
            collected_at=now,
            window_start=window_start,
            window_end=window_end,
            data_origin="aws",
            resources=resources,
            series=series,
            # Deployment events from ssm:ListCommands: next step (Day 4c/5b). When added, set
            # DEPLOYMENT_EVENTS_COLLECTED["aws"] in investigation/bundle.py.
            events=[],
            collector_statuses=statuses,
        )

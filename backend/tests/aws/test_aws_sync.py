"""End to end with mocked AWS: AwsSource -> SyncService -> detection -> SQLite.

The same engine, lifecycle and store as the simulator; only the source differs. Every AWS
response is a botocore Stubber response (no network, no credentials).
"""

from datetime import timedelta

from botocore.exceptions import NoCredentialsError

from sentinel.collectors.aws.source import AwsSource
from sentinel.services.sync import SyncService
from sentinel.store.sqlite import SqliteStore
from tests.aws.conftest import (
    INSTANCE_ID,
    REGION,
    credit_specs,
    describe_instances,
    five_minute_points,
    instance,
    metric_result,
)

LOG_GROUP = "/cloudops-sentinel/dev/access"


def _sync(stubs, clock, factory=None):
    source = AwsSource(
        factory or (lambda: stubs.clients),
        clock=clock,
        region=REGION,
        log_group=LOG_GROUP,
        sleep=lambda s: None,
    )
    store = SqliteStore(":memory:")
    return SyncService(source, store, clock, window=timedelta(hours=3)), store


def _discovery(stubs):
    stubs.ec2.add_response("describe_instances", describe_instances(instance()))
    stubs.ec2.add_response("describe_instance_credit_specifications", credit_specs())


def _saturated_cpu(stubs, now):
    # 40% for two hours, then the last four 5-minute periods at 97% (20 minutes).
    stamps, values = five_minute_points(now, [40.0] * 24 + [97.0] * 4)
    stubs.cloudwatch.add_response(
        "get_metric_data", {"MetricDataResults": [metric_result("m0_0", stamps, values)]}
    )


def _empty_logs(stubs):
    for query_id in ("q-traffic", "q-errors"):
        stubs.logs.add_response("start_query", {"queryId": query_id})
        stubs.logs.add_response("get_query_results", {"status": "Complete", "results": []})


def test_aws_cpu_saturation_becomes_an_incident_through_the_same_pipeline(stubs, clock):
    _discovery(stubs)
    _saturated_cpu(stubs, clock.now())
    _empty_logs(stubs)
    sync, store = _sync(stubs, clock)

    run = sync.run()

    assert run.status == "success"
    assert [(c.name, c.state) for c in run.collectors] == [
        ("ec2", "ok"),
        ("cloudwatch_metrics", "ok"),
        ("cloudwatch_logs", "ok"),
    ]
    [incident] = store.open_incidents()
    assert incident.data_origin == "aws"
    assert incident.fingerprint == INSTANCE_ID
    assert incident.rule_ids == ["R-CPU-SAT"]
    assert incident.severity == "medium"
    kinds = {f.kind for f in incident.facts}
    # Memory, traffic and latency were not available: recorded as gaps, not as healthy.
    assert "data_gap" in kinds
    assert store.latest_snapshot().data_origin == "aws"


def test_failed_metrics_make_a_partial_sync_with_a_hint_and_no_incident(stubs, clock):
    _discovery(stubs)
    stubs.cloudwatch.add_client_error(
        "get_metric_data",
        service_error_code="AccessDenied",
        service_message="User: arn:aws:sts::123456789012:assumed-role/x is not authorized",
    )
    _empty_logs(stubs)
    sync, store = _sync(stubs, clock)

    run = sync.run()

    assert run.status == "partial"
    metrics = next(c for c in run.collectors if c.name == "cloudwatch_metrics")
    assert metrics.state == "failed"
    assert metrics.error.code == "access_denied"
    assert "123456789012" not in metrics.error.message
    assert metrics.error.hint
    assert store.open_incidents() == []  # no data is not "healthy", it is no verdict


def test_missing_data_never_resolves_an_open_aws_incident(stubs, clock):
    _discovery(stubs)
    _saturated_cpu(stubs, clock.now())
    _empty_logs(stubs)
    sync, store = _sync(stubs, clock)
    assert sync.run().incidents_opened == 1

    clock.advance(timedelta(minutes=30))
    _discovery(stubs)
    stubs.cloudwatch.add_client_error("get_metric_data", service_error_code="ThrottlingException")
    _empty_logs(stubs)
    run = sync.run()

    assert run.status == "partial"
    assert run.incidents_resolved == 0
    assert len(store.open_incidents()) == 1


def test_failed_discovery_fails_the_sync_with_the_login_hint(stubs, clock):
    stubs.ec2.add_client_error("describe_instances", service_error_code="ExpiredToken")
    sync, store = _sync(stubs, clock)

    run = sync.run()

    assert run.status == "failed"
    [collector] = run.collectors
    assert collector.name == "ec2" and collector.state == "failed"
    assert collector.error.code == "credentials_expired"
    assert "aws login --profile sentinel-login" in collector.error.hint
    assert store.latest_snapshot() is None  # nothing stored, nothing evaluated


def test_no_credentials_at_all_is_a_failed_sync_not_a_crash(stubs, clock):
    def no_credentials():
        raise NoCredentialsError()

    sync, _ = _sync(stubs, clock, factory=no_credentials)
    run = sync.run()
    assert run.status == "failed"
    assert run.collectors[0].error.code == "credentials_unavailable"


def test_no_monitored_instance_makes_no_metric_or_log_calls(stubs, clock):
    stubs.ec2.add_response("describe_instances", describe_instances())
    sync, store = _sync(stubs, clock)
    run = sync.run()
    assert run.status == "success"
    assert run.resources_evaluated == 0
    # The stubs would fail on any GetMetricData or StartQuery call (none were queued).


def test_degraded_credit_lookup_is_visible_in_the_sync(stubs, clock):
    stubs.ec2.add_response("describe_instances", describe_instances(instance()))
    stubs.ec2.add_client_error(
        "describe_instance_credit_specifications", service_error_code="UnauthorizedOperation"
    )
    _saturated_cpu(stubs, clock.now())
    _empty_logs(stubs)
    sync, _ = _sync(stubs, clock)
    run = sync.run()
    assert run.status == "partial"
    assert next(c for c in run.collectors if c.name == "ec2").state == "degraded"


def test_logs_query_timeout_is_reported_and_metrics_still_count(stubs, clock):
    _discovery(stubs)
    _saturated_cpu(stubs, clock.now())
    stubs.logs.add_response("start_query", {"queryId": "q1"})
    for _ in range(31):  # 30 s timeout, polled every second
        stubs.logs.add_response("get_query_results", {"status": "Running", "results": []})
    stubs.logs.add_response("stop_query", {"success": True})
    sync, store = _sync(stubs, clock)

    run = sync.run()

    logs = next(c for c in run.collectors if c.name == "cloudwatch_logs")
    assert run.status == "partial"
    assert logs.state == "failed" and logs.error.code == "query_incomplete"
    assert len(store.open_incidents()) == 1  # the CPU breach is still detected

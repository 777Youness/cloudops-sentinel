"""The real-AWS demo, end to end with mocked AWS (ADR 0019).

Logs Insights rows shaped exactly like the demo traffic (scripts/demo_traffic.py defaults:
60 requests per minute, every 5th one a fault) go through the real AwsSource,
SyncService, detection engine and SQLite store. The thresholds are the production ones.
"""

from datetime import timedelta

from sentinel.collectors.aws.logs import INGESTION_DELAY
from sentinel.collectors.aws.source import AwsSource
from sentinel.detection import thresholds as th
from sentinel.services.sync import SyncService
from sentinel.store.sqlite import SqliteStore
from tests.aws.conftest import (
    INSTANCE_ID,
    REGION,
    credit_specs,
    describe_instances,
    instance,
    log_row,
)

LOG_GROUP = "/cloudops-sentinel/dev/access"


def _last_complete_minute(now):
    end = now - INGESTION_DELAY
    return end.replace(second=0, microsecond=0) - timedelta(minutes=1)


def _minutes(now, count):
    last = _last_complete_minute(now)
    return [last - timedelta(minutes=count - 1 - i) for i in range(count)]


def _stub_sync(stubs, traffic_rows, error_rows):
    stubs.ec2.add_response("describe_instances", describe_instances(instance()))
    stubs.ec2.add_response("describe_instance_credit_specifications", credit_specs())
    stubs.cloudwatch.add_response("get_metric_data", {"MetricDataResults": []})
    stubs.logs.add_response("start_query", {"queryId": "q-traffic"})
    stubs.logs.add_response("get_query_results", {"status": "Complete", "results": traffic_rows})
    stubs.logs.add_response("start_query", {"queryId": "q-errors"})
    stubs.logs.add_response("get_query_results", {"status": "Complete", "results": error_rows})


def _demo_rows(minutes, requests=60, errors=12, p95=4.0):
    traffic = [log_row(INSTANCE_ID, m, requests=requests, p95=p95) for m in minutes]
    faults = [log_row(INSTANCE_ID, m, errors=errors) for m in minutes if errors]
    return traffic, faults


def _service(stubs, clock):
    source = AwsSource(
        lambda: stubs.clients, clock=clock, region=REGION, log_group=LOG_GROUP, sleep=lambda s: 0
    )
    store = SqliteStore(":memory:")
    return SyncService(source, store, clock, window=timedelta(hours=3)), store


def test_demo_traffic_opens_a_high_severity_5xx_incident(stubs, clock):
    sync, store = _service(stubs, clock)
    _stub_sync(stubs, *_demo_rows(_minutes(clock.now(), 6)))  # 6 complete minutes at 20 %

    run = sync.run()

    assert run.status == "success"
    assert run.incidents_opened == 1
    [incident] = store.open_incidents()
    assert incident.data_origin == "aws"
    assert incident.rule_ids == ["R-5XX"]
    assert incident.severity == "high"  # >= 5 % for 5 minutes: the full tier
    breach = next(
        f for f in incident.facts if f.rule_id == "R-5XX" and f.kind == "threshold_breach"
    )
    assert breach.value == 20.0 and breach.unit == "percent"
    # Latency stayed far below R-LAT's 500 ms floor: checked and normal (no baseline needed).
    assert any(f.kind == "within_normal" and f.signal == "latency_p95" for f in incident.facts)
    # No memory or CPU metrics were returned in this test: recorded as gaps, never as 0.
    assert any(f.kind == "data_gap" and f.signal == "memory_used" for f in incident.facts)


def test_four_minutes_of_errors_are_not_yet_an_incident(stubs, clock):
    # The rule needs 5 minutes: syncing too early is the most likely demo mistake.
    sync, store = _service(stubs, clock)
    _stub_sync(stubs, *_demo_rows(_minutes(clock.now(), 4)))
    assert sync.run().incidents_opened == 0
    assert timedelta(minutes=5) == th.ERR_5XX_MIN_DURATION


def test_a_missing_minute_breaks_the_breach(stubs, clock):
    sync, _ = _service(stubs, clock)
    minutes = _minutes(clock.now(), 8)
    del minutes[5]  # the generator paused for a minute: the run restarts after the gap
    _stub_sync(stubs, *_demo_rows(minutes))
    assert sync.run().incidents_opened == 0


def test_low_traffic_with_the_same_error_rate_does_not_alert(stubs, clock):
    # 5 requests per minute = 25 in 5 minutes, below the 50-request guard: no incident,
    # and the threshold is NOT lowered to make a demo pass.
    sync, store = _service(stubs, clock)
    _stub_sync(stubs, *_demo_rows(_minutes(clock.now(), 6), requests=5, errors=1))
    assert sync.run().incidents_opened == 0
    assert th.MIN_REQUESTS == 50


def test_healthy_traffic_for_ten_minutes_resolves_the_incident(stubs, clock):
    sync, store = _service(stubs, clock)
    error_minutes = _minutes(clock.now(), 6)
    _stub_sync(stubs, *_demo_rows(error_minutes))
    assert sync.run().incidents_opened == 1

    clock.advance(timedelta(minutes=13))
    healthy_minutes = [m for m in _minutes(clock.now(), 19) if m > error_minutes[-1]]
    assert len(healthy_minutes) >= 10
    traffic, faults = _demo_rows(error_minutes)
    healthy, _ = _demo_rows(healthy_minutes, errors=0)
    _stub_sync(stubs, traffic + healthy, faults)

    run = sync.run()

    assert run.incidents_resolved == 1
    assert store.open_incidents() == []


def test_errors_that_continue_keep_the_incident_open(stubs, clock):
    sync, store = _service(stubs, clock)
    _stub_sync(stubs, *_demo_rows(_minutes(clock.now(), 6)))
    sync.run()
    clock.advance(timedelta(minutes=3))
    _stub_sync(stubs, *_demo_rows(_minutes(clock.now(), 9)))
    run = sync.run()
    assert run.incidents_opened == 0 and run.incidents_resolved == 0
    assert len(store.open_incidents()) == 1

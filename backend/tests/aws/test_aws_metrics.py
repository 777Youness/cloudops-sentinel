"""CloudWatch metrics: one batched GetMetricData, complete periods only, gaps stay gaps."""

from datetime import UTC, timedelta, timezone

from botocore.stub import ANY

from sentinel.collectors.aws.metrics import build_queries, collect_metrics
from sentinel.domain.observations import Resource
from tests.aws.conftest import INSTANCE_ID, five_minute_points, metric_result
from tests.conftest import NOW

WINDOW_START = NOW - timedelta(hours=3)


def _resource(instance_type="t3.micro"):
    return Resource(
        id=INSTANCE_ID,
        name="cloudops-dev",
        region="eu-west-3",
        state="running",
        instance_type=instance_type,
        credit_mode="standard",
        data_origin="aws",
    )


def _expected_params(resource):
    return {
        "MetricDataQueries": [q[3] for q in build_queries([resource])],
        "StartTime": ANY,
        "EndTime": ANY,
        "ScanBy": "TimestampAscending",
    }


def test_queries_cover_the_v1_signals_with_instance_id_only():
    queries = build_queries([_resource()])
    metrics = {q[3]["MetricStat"]["Metric"]["MetricName"]: q[3] for q in queries}
    assert set(metrics) == {
        "CPUUtilization",
        "CPUCreditBalance",
        "StatusCheckFailed",
        "mem_used_percent",
    }
    for query in metrics.values():
        dims = query["MetricStat"]["Metric"]["Dimensions"]
        assert dims == [{"Name": "InstanceId", "Value": INSTANCE_ID}]
    assert metrics["mem_used_percent"]["MetricStat"]["Metric"]["Namespace"] == "CWAgent"
    assert metrics["StatusCheckFailed"]["MetricStat"]["Stat"] == "Maximum"


def test_credit_balance_is_only_requested_for_burstable_instances():
    names = [q[2].metric_name for q in build_queries([_resource("m5.large")])]
    assert "CPUCreditBalance" not in names


def test_results_become_series_with_units_and_sources(stubs):
    resource = _resource()
    stamps, values = five_minute_points(NOW, [40.0, 41.0, 97.0])
    stubs.cloudwatch.add_response(
        "get_metric_data",
        {"MetricDataResults": [metric_result("m0_0", stamps, values)]},
        _expected_params(resource),
    )
    result = collect_metrics(stubs.clients.cloudwatch, [resource], WINDOW_START, NOW)
    assert result.problems == []
    [series] = result.series
    assert series.signal == "cpu_utilization"
    assert series.unit == "percent"
    assert series.period_seconds == 300
    assert series.source == "cloudwatch:AWS/EC2/CPUUtilization"
    assert [p.v for p in series.points] == [40.0, 41.0, 97.0]


def test_timestamps_become_utc_whatever_zone_botocore_returns(stubs):
    # botocore parses CloudWatch's epoch timestamps into the machine's local zone (seen on a
    # real sync: "+01:00"). Facts and statements say "UTC", so the boundary converts.
    resource = _resource()
    stamps, values = five_minute_points(NOW, [40.0, 41.0])
    paris = timezone(timedelta(hours=1))
    stubs.cloudwatch.add_response(
        "get_metric_data",
        {
            "MetricDataResults": [
                metric_result("m0_0", [t.astimezone(paris) for t in stamps], values)
            ]
        },
        _expected_params(resource),
    )
    [series] = collect_metrics(stubs.clients.cloudwatch, [resource], WINDOW_START, NOW).series
    assert [p.t for p in series.points] == stamps
    assert all(p.t.utcoffset() == timedelta(0) and p.t.tzinfo is UTC for p in series.points)


def test_the_period_still_running_is_dropped(stubs):
    resource = _resource()
    stamps, values = five_minute_points(NOW, [40.0, 41.0])
    running = stamps[-1] + timedelta(minutes=5)  # 14:05 at 14:05:30: incomplete
    stubs.cloudwatch.add_response(
        "get_metric_data",
        {"MetricDataResults": [metric_result("m0_0", [*stamps, running], [*values, 99.0])]},
        _expected_params(resource),
    )
    [series] = collect_metrics(stubs.clients.cloudwatch, [resource], WINDOW_START, NOW).series
    assert all(p.t + timedelta(seconds=300) <= NOW for p in series.points)
    assert 99.0 not in [p.v for p in series.points]


def test_a_metric_without_data_produces_no_series_never_zeros(stubs):
    resource = _resource()
    stubs.cloudwatch.add_response(
        "get_metric_data",
        {"MetricDataResults": [metric_result("m0_3", [], [])]},  # no memory: agent not running
        _expected_params(resource),
    )
    assert collect_metrics(stubs.clients.cloudwatch, [resource], WINDOW_START, NOW).series == []


def test_partial_data_is_reported_as_a_problem(stubs):
    resource = _resource()
    stamps, values = five_minute_points(NOW, [40.0])
    stubs.cloudwatch.add_response(
        "get_metric_data",
        {"MetricDataResults": [metric_result("m0_0", stamps, values, status="PartialData")]},
        _expected_params(resource),
    )
    result = collect_metrics(stubs.clients.cloudwatch, [resource], WINDOW_START, NOW)
    assert result.problems == [f"{INSTANCE_ID} CPUUtilization: PartialData"]


def test_pages_are_followed(stubs):
    resource = _resource()
    first, values = five_minute_points(NOW, [40.0, 41.0])
    stubs.cloudwatch.add_response(
        "get_metric_data",
        {"MetricDataResults": [metric_result("m0_0", first[:1], values[:1])], "NextToken": "t1"},
        _expected_params(resource),
    )
    stubs.cloudwatch.add_response(
        "get_metric_data",
        {"MetricDataResults": [metric_result("m0_0", first[1:], values[1:])]},
        {**_expected_params(resource), "NextToken": "t1"},
    )
    [series] = collect_metrics(stubs.clients.cloudwatch, [resource], WINDOW_START, NOW).series
    assert [p.v for p in series.points] == [40.0, 41.0]

"""Logs Insights: bounded queries, per-instance minutes, missing minutes stay missing."""

from datetime import timedelta

import pytest

from sentinel.collectors.aws.logs import (
    ERRORS_QUERY,
    QUERY_LIMIT,
    TRAFFIC_QUERY,
    LogsQueryError,
    collect_log_signals,
)
from sentinel.domain.observations import Resource
from tests.aws.conftest import INSTANCE_ID, log_row
from tests.conftest import NOW

LOG_GROUP = "/cloudops-sentinel/dev/access"
WINDOW_START = NOW - timedelta(hours=3)
END = NOW - timedelta(minutes=2)  # ingestion delay
MINUTE = END.replace(second=0) - timedelta(minutes=10)
RESOURCE = Resource(
    id=INSTANCE_ID,
    name="cloudops-dev",
    region="eu-west-3",
    state="running",
    instance_type="t3.micro",
    data_origin="aws",
)


def _start(stubs, query, query_id):
    stubs.logs.add_response(
        "start_query",
        {"queryId": query_id},
        {
            "logGroupName": LOG_GROUP,
            "startTime": int(WINDOW_START.timestamp()),
            "endTime": int(END.timestamp()),
            "queryString": query,
            "limit": QUERY_LIMIT,
        },
    )


def _results(stubs, query_id, rows, status="Complete"):
    stubs.logs.add_response(
        "get_query_results", {"status": status, "results": rows}, {"queryId": query_id}
    )


def _collect(stubs, timeout=30.0):
    return collect_log_signals(
        stubs.clients.logs, LOG_GROUP, [RESOURCE], WINDOW_START, NOW, timeout, sleep=lambda s: None
    )


def test_queries_are_bounded_to_the_sync_window_and_build_three_signals(stubs):
    _start(stubs, TRAFFIC_QUERY, "q-traffic")
    _results(stubs, "q-traffic", [], status="Running")  # polled until complete
    _results(
        stubs,
        "q-traffic",
        [
            log_row(INSTANCE_ID, MINUTE, requests=200, p95=12.5),
            log_row(INSTANCE_ID, MINUTE + timedelta(minutes=1), requests=100, p95=900),
        ],
    )
    _start(stubs, ERRORS_QUERY, "q-errors")
    _results(stubs, "q-errors", [log_row(INSTANCE_ID, MINUTE + timedelta(minutes=1), errors=8)])

    result = _collect(stubs)
    by_signal = {s.signal: s for s in result.series}
    assert set(by_signal) == {"request_rate", "error_rate_5xx", "latency_p95"}
    assert [p.v for p in by_signal["request_rate"].points] == [200.0, 100.0]
    # 0 errors in a minute WITH requests is a measurement; 8 of 100 is 8%.
    assert [p.v for p in by_signal["error_rate_5xx"].points] == [0.0, 8.0]
    assert [p.v for p in by_signal["latency_p95"].points] == [12.5, 900.0]
    assert all(s.period_seconds == 60 and s.resource_id == INSTANCE_ID for s in result.series)
    assert by_signal["request_rate"].unit == "per_minute"
    assert result.problems == []


def test_a_minute_without_log_lines_stays_missing(stubs):
    _start(stubs, TRAFFIC_QUERY, "q1")
    _results(
        stubs,
        "q1",
        [
            log_row(INSTANCE_ID, MINUTE, requests=10, p95=5),
            log_row(INSTANCE_ID, MINUTE + timedelta(minutes=3), requests=10, p95=5),
        ],
    )
    _start(stubs, ERRORS_QUERY, "q2")
    _results(stubs, "q2", [])
    rate = next(s for s in _collect(stubs).series if s.signal == "request_rate")
    assert [p.t for p in rate.points] == [MINUTE, MINUTE + timedelta(minutes=3)]  # no zeros


def test_no_log_lines_at_all_gives_no_series(stubs):
    _start(stubs, TRAFFIC_QUERY, "q1")
    _results(stubs, "q1", [])
    _start(stubs, ERRORS_QUERY, "q2")
    _results(stubs, "q2", [])
    assert _collect(stubs).series == []


def test_streams_of_unknown_instances_are_ignored(stubs):
    _start(stubs, TRAFFIC_QUERY, "q1")
    _results(stubs, "q1", [log_row("i-someone-else", MINUTE, requests=10, p95=5)])
    _start(stubs, ERRORS_QUERY, "q2")
    _results(stubs, "q2", [])
    assert _collect(stubs).series == []


def test_a_query_that_does_not_finish_is_stopped_and_reported(stubs):
    _start(stubs, TRAFFIC_QUERY, "q1")
    _results(stubs, "q1", [], status="Running")
    _results(stubs, "q1", [], status="Running")
    stubs.logs.add_response("stop_query", {"success": True}, {"queryId": "q1"})
    with pytest.raises(LogsQueryError, match="still Running"):
        _collect(stubs, timeout=1.0)


def test_a_failed_query_is_an_error_not_empty_data(stubs):
    _start(stubs, TRAFFIC_QUERY, "q1")
    _results(stubs, "q1", [], status="Failed")
    with pytest.raises(LogsQueryError, match="Failed"):
        _collect(stubs)


def test_results_at_the_row_limit_are_flagged_as_possibly_cut(stubs):
    rows = [
        log_row(INSTANCE_ID, MINUTE - timedelta(minutes=i), requests=1, p95=1)
        for i in range(QUERY_LIMIT)
    ]
    _start(stubs, TRAFFIC_QUERY, "q1")
    _results(stubs, "q1", rows)
    _start(stubs, ERRORS_QUERY, "q2")
    _results(stubs, "q2", [])
    assert _collect(stubs).problems == [
        f"traffic query returned {QUERY_LIMIT} rows: results may be cut"
    ]

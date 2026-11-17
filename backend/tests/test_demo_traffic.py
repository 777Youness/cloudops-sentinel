"""scripts/demo_traffic.py: controlled traffic that meets R-5XX without lowering thresholds.

No AWS: the generator is exercised against the real workload app on 127.0.0.1.
"""

import importlib.util
import json
import threading
from pathlib import Path

import pytest

from sentinel.detection import thresholds as th

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


traffic = _load("demo_traffic", ROOT / "scripts" / "demo_traffic.py")
app = _load("workload_app_for_demo", ROOT / "workload" / "app.py")


def test_the_script_mirrors_the_real_r5xx_thresholds():
    # If someone lowers a threshold (or the script drifts), the demo claim must be re-checked.
    assert traffic.R5XX_HIGH_PERCENT == th.ERR_5XX_HIGH_PERCENT == 5.0
    assert traffic.R5XX_MIN_REQUESTS == th.MIN_REQUESTS == 50
    assert th.ERR_5XX_MIN_DURATION.total_seconds() == traffic.R5XX_MIN_MINUTES * 60
    assert traffic.FAULT_PATH == app.FAULT_PATH


def test_default_errors_profile_can_trigger_the_high_tier():
    shape = traffic.profile(rps=1.0, error_every=5)
    assert shape == {
        "requests_per_minute": 60.0,
        "error_percent": 20.0,
        "requests_in_5_minutes": 300.0,
        "can_trigger_r5xx_high": True,
    }


def test_too_little_traffic_cannot_trigger_it():
    # 1 request every 10 s = 30 requests in 5 minutes: below the 50-request guard.
    assert traffic.profile(rps=0.1, error_every=5)["can_trigger_r5xx_high"] is False
    assert traffic.profile(rps=1.0, error_every=0)["can_trigger_r5xx_high"] is False


def test_sync_advice_covers_the_rule_duration_and_the_collector_delays():
    # 5 complete minutes + the running minute + 2 minutes ingestion delay (logs.py).
    assert traffic.SYNC_AFTER_MINUTES >= traffic.R5XX_MIN_MINUTES + 1 + 2


def test_every_nth_request_is_a_fault():
    paths = [traffic.path_for(i, 5) for i in range(10)]
    assert paths.count(traffic.FAULT_PATH) == 2
    assert paths[4] == paths[9] == traffic.FAULT_PATH
    assert all(traffic.path_for(i, 0) == "/" for i in range(10))  # healthy mode


@pytest.mark.parametrize(
    "url",
    [
        "https://203.0.113.10:8080",
        "http://203.0.113.10:8080/fault/500",
        "http://203.0.113.10:8080/?x=1",
        "http://user:pass@203.0.113.10:8080",
        "ftp://203.0.113.10",
        "203.0.113.10:8080",
    ],
)
def test_only_a_plain_app_url_is_accepted(url):
    with pytest.raises(ValueError):
        traffic.validate_url(url)


def test_the_app_url_output_is_accepted():
    assert traffic.validate_url("http://203.0.113.10:8080/") == "http://203.0.113.10:8080"


def test_cli_refuses_unbounded_runs(monkeypatch):
    # If a bound ever broke, main() must fail here instead of sending real traffic.
    def no_traffic(*args, **kwargs):
        raise AssertionError("main() tried to send traffic: a bound did not stop it")

    monkeypatch.setattr(traffic, "run", no_traffic)
    for args in (["--minutes", "31"], ["--rps", "6"], ["--error-every", "1"]):
        with pytest.raises(SystemExit):
            traffic.main(["--url", "http://203.0.113.10:8080", *args])


def test_run_counts_answers_without_any_network():
    statuses = {"/": 200, traffic.FAULT_PATH: 500}
    counts = traffic.run(
        "http://x",
        10,
        rps=5,
        error_every=5,
        sender=lambda url: statuses[url.removeprefix("http://x")],
        sleep=lambda s: None,
        report=lambda line: None,
    )
    assert counts == {"ok": 8, "fault_500": 2, "other": 0, "unreachable": 0}


def test_unreachable_app_is_counted_not_hidden():
    counts = traffic.run(
        "http://x", 3, rps=5, error_every=0, sender=lambda url: None, sleep=lambda s: None
    )
    assert counts["unreachable"] == 3


def test_generator_against_the_real_app_writes_one_log_line_per_request(tmp_path):
    log_path = tmp_path / "access.log"
    server = app.build_server(0, str(log_path), app.make_route(True), host="127.0.0.1")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        counts = traffic.run(base, 25, rps=1000, error_every=5, report=lambda line: None)
    finally:
        server.shutdown()
        server.server_close()
    assert counts == {"ok": 20, "fault_500": 5, "other": 0, "unreachable": 0}
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 25
    assert sum(line["status"] == 500 for line in lines) == 5
    assert {line["path"] for line in lines} == {"/", "/fault/500"}


def test_with_faults_disabled_the_generator_sees_404_not_500(tmp_path):
    log_path = tmp_path / "access.log"
    server = app.build_server(0, str(log_path), host="127.0.0.1")  # default: faults off
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        counts = traffic.run(base, 10, rps=1000, error_every=5, report=lambda line: None)
    finally:
        server.shutdown()
        server.server_close()
    assert counts == {"ok": 8, "fault_500": 0, "other": 2, "unreachable": 0}

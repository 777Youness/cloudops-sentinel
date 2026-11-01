"""The workload app (workload/app.py) and its access-log contract with Sentinel.

The app runs on the EC2 instance with the AL2023 system Python 3.9; these tests run it
locally on 3.12 against a real socket (127.0.0.1, an ephemeral port), with no AWS. Python
3.9 compatibility is checked separately with `ruff check --target-version py39`
(infra/README.md); it is not proven by this suite.
"""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

APP_PATH = Path(__file__).resolve().parents[3] / "workload" / "app.py"

_spec = importlib.util.spec_from_file_location("workload_app", APP_PATH)
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)


@pytest.fixture
def serve(tmp_path):
    """Start the app on 127.0.0.1 with an ephemeral port; yield (base_url, log_path)."""
    servers = []

    def start(route=app.handle):
        log_path = tmp_path / "access.log"
        # Loopback only in tests; the instance binds 0.0.0.0 (the default).
        server = app.build_server(0, str(log_path), route, host="127.0.0.1")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}", log_path

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def _log_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_root_and_health_answer_200(serve):
    base, _ = serve()
    assert _get(base + "/") == (200, "ok\n")
    assert _get(base + "/health") == (200, "ok\n")


def test_unknown_path_is_404(serve):
    base, _ = serve()
    assert _get(base + "/nope")[0] == 404


def test_one_json_line_per_request_with_the_contract_fields(serve):
    base, log_path = serve()
    _get(base + "/")
    _get(base + "/nope")
    lines = _log_lines(log_path)
    assert [(line["method"], line["path"], line["status"]) for line in lines] == [
        ("GET", "/", 200),
        ("GET", "/nope", 404),
    ]
    for line in lines:
        assert set(line) == {"time", "method", "path", "status", "duration_ms"}
        assert line["time"].endswith("Z") and "T" in line["time"]
        assert isinstance(line["duration_ms"], float) and line["duration_ms"] >= 0


def test_query_strings_are_never_logged(serve):
    base, log_path = serve()
    _get(base + "/health?token=should-not-appear")
    text = log_path.read_text(encoding="utf-8")
    assert "should-not-appear" not in text and "token" not in text
    assert _log_lines(log_path)[0]["path"] == "/health"


def test_long_paths_are_clipped_in_the_log(serve):
    base, log_path = serve()
    _get(base + "/" + "a" * 500)
    assert len(_log_lines(log_path)[0]["path"]) == app.MAX_LOGGED_PATH


def test_an_unexpected_error_is_a_logged_500_not_a_crash(serve):
    def broken(path):
        raise RuntimeError("boom")

    base, log_path = serve(route=broken)
    assert _get(base + "/")[0] == 500
    assert _log_lines(log_path)[0]["status"] == 500
    # The server keeps serving after the failure.
    assert _get(base + "/")[0] == 500


def test_concurrent_requests_write_whole_lines(serve):
    base, log_path = serve()
    threads = [threading.Thread(target=_get, args=(base + "/",)) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    lines = _log_lines(log_path)  # every line parses as JSON: no interleaving
    assert len(lines) == 20


def test_defaults_match_the_terraform_configuration():
    assert app.DEFAULT_PORT == 8080
    assert app.DEFAULT_ACCESS_LOG == "/var/log/cloudops-workload/access.log"


def test_the_app_uses_only_the_standard_library():
    import ast
    import sys

    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots - {"__future__"} <= set(sys.stdlib_module_names), roots

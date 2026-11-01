"""CloudOps Sentinel demo workload: a tiny HTTP service that writes one JSON line per request.

It runs on the disposable EC2 instance (infra/envs/dev), started by systemd from user_data.
Standard library only, and compatible with Python 3.9, the AL2023 system python3.

The access log is the workload's contract with Sentinel. The CloudWatch agent ships it to
the log group /cloudops-sentinel/<env>/access; from Day 5 Sentinel derives request_rate,
error_rate_5xx and latency_p95 from it with Logs Insights. One line per request:

    {"time": "2026-11-01T10:00:00.123Z", "method": "GET", "path": "/",
     "status": 200, "duration_ms": 0.42}

Only the path is logged, never the query string or headers: log lines become evidence that
is sent to an LLM (CLAUDE.md section 7), so they must not carry anything a client typed.

Configuration (environment variables):
    WORKLOAD_PORT        TCP port, default 8080
    WORKLOAD_ACCESS_LOG  access log file, default /var/log/cloudops-workload/access.log
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DEFAULT_PORT = 8080
DEFAULT_ACCESS_LOG = "/var/log/cloudops-workload/access.log"
MAX_LOGGED_PATH = 200


def _utc_now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class AccessLog:
    """Appends one JSON object per line. Thread-safe: the server handles requests in threads."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()

    def write(self, method: str, path: str, status: int, duration_ms: float) -> None:
        line = json.dumps(
            {
                "time": _utc_now_iso(),
                "method": method,
                "path": path[:MAX_LOGGED_PATH],
                "status": status,
                "duration_ms": round(duration_ms, 3),
            },
            separators=(",", ":"),
        )
        with self._lock, open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def handle(path: str) -> tuple[int, str]:
    """The routes. Returns (status, body). Fault injection arrives with Day 4c scripts."""
    if path in ("/", "/health"):
        return 200, "ok\n"
    return 404, "not found\n"


def make_handler(access_log: AccessLog, route=handle):
    class Handler(BaseHTTPRequestHandler):
        server_version = "cloudops-workload/1"

        def do_GET(self) -> None:  # noqa: N802 (name required by BaseHTTPRequestHandler)
            started = time.perf_counter()
            path = urlsplit(self.path).path or "/"
            try:
                status, body = route(path)
            except Exception:
                # An unexpected failure is a real 5xx: answered, logged, never hidden.
                status, body = 500, "internal error\n"
            # Logged before the response is sent, so a request the client saw answered is
            # always in the log. duration_ms is the server's handling time.
            access_log.write("GET", path, status, (time.perf_counter() - started) * 1000)
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # The JSON access log replaces the default stderr line (which includes the query).
            return

    return Handler


def build_server(
    port: int, access_log_path: str, route=handle, host: str = "0.0.0.0"
) -> ThreadingHTTPServer:
    # 0.0.0.0 on the instance: the security group, not the app, restricts who can connect
    # (the operator's /32). Tests pass 127.0.0.1.
    return ThreadingHTTPServer((host, port), make_handler(AccessLog(access_log_path), route))


def main() -> None:
    port = int(os.environ.get("WORKLOAD_PORT", str(DEFAULT_PORT)))
    access_log_path = os.environ.get("WORKLOAD_ACCESS_LOG", DEFAULT_ACCESS_LOG)
    server = build_server(port, access_log_path)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

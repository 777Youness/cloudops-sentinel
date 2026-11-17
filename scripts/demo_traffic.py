"""Controlled demo traffic for the real-AWS 5xx incident (ADR 0019, infra/README.md section 8).

    python scripts/demo_traffic.py --url http://<public_ip>:8080 --mode errors
    python scripts/demo_traffic.py --url http://<public_ip>:8080 --mode healthy

Runs on Windows, macOS and Linux with any Python 3.9+ (standard library only). It sends
plain GET requests to two fixed paths of the workload you deployed, nothing else:

    /           -> 200 (normal traffic)
    /fault/500  -> 500 (the dev-only fault route; 404 if faults are disabled)

Why these defaults satisfy R-5XX WITHOUT lowering any threshold (detection/thresholds.py):
  - 1 request per second = 60 requests per minute, every minute (no gap breaks the run);
  - every 5th request is a fault = 20 % errors, above the 5 % "high" tier;
  - 5 minutes of breach = 300 requests, above the 50-request traffic guard.
And why you sync after about 9 minutes: R-5XX needs 5 complete one-minute periods; the
collector leaves out the minute in progress and the last 2 minutes (log ingestion delay),
so 5 + 1 + 2 minutes plus a margin. Keep the traffic running while you sync.

Cost: about 60 log lines per minute (a few kB); nothing else is created or changed.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlsplit

FAULT_PATH = "/fault/500"
MAX_MINUTES = 30
MAX_RPS = 5.0
SYNC_AFTER_MINUTES = 9  # 5 complete minutes + the running minute + 2 min ingestion + margin

# Mirrors detection/thresholds.py (R-5XX); test_demo_traffic.py fails if they ever differ.
R5XX_HIGH_PERCENT = 5.0
R5XX_MIN_REQUESTS = 50
R5XX_MIN_MINUTES = 5


def path_for(index: int, error_every: int) -> str:
    """The deterministic pattern: request n (0-based) is a fault if (n + 1) % error_every == 0."""
    if error_every and (index + 1) % error_every == 0:
        return FAULT_PATH
    return "/"


def profile(rps: float, error_every: int) -> dict:
    """What one minute of this traffic looks like, and whether it can trigger R-5XX."""
    per_minute = rps * 60
    error_percent = 100.0 / error_every if error_every else 0.0
    in_breach = per_minute * R5XX_MIN_MINUTES
    return {
        "requests_per_minute": per_minute,
        "error_percent": error_percent,
        "requests_in_5_minutes": in_breach,
        "can_trigger_r5xx_high": error_percent >= R5XX_HIGH_PERCENT
        and in_breach >= R5XX_MIN_REQUESTS,
    }


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "http" or not parts.hostname or parts.path not in ("", "/"):
        raise ValueError("--url must look like http://<public_ip>:8080 (the app_url output)")
    if parts.query or parts.fragment or parts.username:
        raise ValueError("--url must not contain a query, a fragment or credentials")
    return f"http://{parts.netloc}"


def send(url: str, timeout: float = 5.0) -> int | None:
    """GET once; the HTTP status, or None if the app could not be reached."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (http only)
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def run(
    base_url: str,
    total_requests: int,
    rps: float,
    error_every: int,
    sender: Callable[[str], int | None] = send,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    report: Callable[[str], None] = print,
) -> dict:
    """Send `total_requests` paced at `rps`; count the answers by status."""
    counts: dict = {"ok": 0, "fault_500": 0, "other": 0, "unreachable": 0}
    start = clock()
    per_minute = max(1, int(rps * 60))
    for index in range(total_requests):
        delay = start + index / rps - clock()
        if delay > 0:
            sleep(delay)
        path = path_for(index, error_every)
        status = sender(base_url + path)
        if status is None:
            counts["unreachable"] += 1
        elif status == 200 and path == "/":
            counts["ok"] += 1
        elif status == 500 and path == FAULT_PATH:
            counts["fault_500"] += 1
        else:
            counts["other"] += 1
        if (index + 1) % per_minute == 0:
            minute = (index + 1) // per_minute
            hint = "  <- sync now (keep this running)" if minute == SYNC_AFTER_MINUTES else ""
            report(f"minute {minute:>2}: {counts}{hint}")
    return counts


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controlled demo traffic (ADR 0019).")
    parser.add_argument("--url", required=True, help="the Terraform app_url output")
    parser.add_argument("--mode", choices=["errors", "healthy"], default="errors")
    parser.add_argument("--minutes", type=float, default=12.0)
    parser.add_argument("--rps", type=float, default=1.0, help="requests per second")
    parser.add_argument("--error-every", type=int, default=5, help="every Nth request faults")
    args = parser.parse_args(argv)

    try:
        base_url = validate_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    if not 0 < args.minutes <= MAX_MINUTES:
        parser.error(f"--minutes must be between 0 and {MAX_MINUTES}")
    if not 0 < args.rps <= MAX_RPS:
        parser.error(f"--rps must be between 0 and {MAX_RPS:g}")
    if args.error_every < 2:
        parser.error("--error-every must be 2 or more")
    error_every = args.error_every if args.mode == "errors" else 0

    shape = profile(args.rps, error_every)
    total = int(args.minutes * 60 * args.rps)
    print(f"{args.mode}: {total} requests to {base_url}, {shape}")
    if args.mode == "errors":
        print(f"Sync in Sentinel after minute {SYNC_AFTER_MINUTES}, while this keeps running.")
    else:
        print("Sync after at least 12 minutes of healthy traffic to see the incident resolve.")
    counts = run(base_url, total, args.rps, error_every)
    print(f"done: {counts}")
    if counts["unreachable"]:
        print("Some requests could not reach the app: check operator_cidr (your IP may have")
        print("changed), the security group, and that the instance is running.")
    if args.mode == "errors" and counts["fault_500"] == 0 and counts["other"]:
        print("No HTTP 500 at all: is fault_injection_enabled true (ADR 0019)?")
    return 0 if not counts["unreachable"] else 1


if __name__ == "__main__":
    sys.exit(main())

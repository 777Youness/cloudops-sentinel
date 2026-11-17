"""Smoke and persistence test for the Docker Compose deployment. Run by a human.

    python scripts/docker_smoke.py

From the repository root, with Docker running. Standard library only. If port 8080 is
taken, set SENTINEL_HTTP_PORT (for example 8081) for both compose and this script. It:
  1. starts the stack (docker compose up --build -d --wait);
  2. checks the console, a deep link (SPA routing) and the API, all through Nginx on
     127.0.0.1:8080;
  3. refuses to continue unless the backend reports simulated mode and the mock provider,
     so it never calls AWS or a real LLM;
  4. runs one simulated sync and one mock investigation;
  5. stops the stack WITHOUT deleting volumes (docker compose down), starts it again, and
     checks that the incidents, the investigation and the last sync are still there.

It uses the compose project's own volume, never the host's backend/data/ databases.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# The host port compose publishes (compose.yaml: SENTINEL_HTTP_PORT, default 8080).
BASE = f"http://127.0.0.1:{os.environ.get('SENTINEL_HTTP_PORT', '8080')}"


def compose(*args: str) -> None:
    print(f"$ docker compose {' '.join(args)}", flush=True)
    subprocess.run(["docker", "compose", *args], check=True)


def request(method: str, path: str) -> tuple[int, str, str]:
    req = urllib.request.Request(BASE + path, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8")
            return response.status, response.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")


def api(method: str, path: str) -> dict:
    status, _, body = request(method, "/api/v1" + path)
    check(status == 200, f"{method} /api/v1{path} answered {status}: {body[:200]}")
    return json.loads(body)


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL {message}")
        sys.exit(1)
    print(f"ok   {message}")


def main() -> None:
    compose("up", "--build", "-d", "--wait")

    for path in ("/", "/incidents/INC-0001", "/system"):
        status, ctype, body = request("GET", path)
        check(
            status == 200 and "text/html" in ctype and 'id="root"' in body,
            f"GET {path} serves the console (SPA routing)",
        )
    check(api("GET", "/health") == {"status": "ok"}, "GET /api/v1/health through the proxy")

    system = api("GET", "/system")
    check(system["mode"] == "local", "the backend is in simulated mode (no AWS calls)")
    check(
        system["llm"]["provider"] == "mock",
        "the mock investigation provider is selected (no LLM calls); unset .env.docker",
    )

    sync = api("POST", "/sync")
    check(sync["status"] == "success", f"simulated sync {sync['id']} succeeded")
    incidents = api("GET", "/incidents?status=all")["items"]
    check(len(incidents) > 0, f"{len(incidents)} incident(s) stored")
    target = incidents[0]["id"]
    result = api("POST", f"/incidents/{target}/investigation")
    inv = result["investigation"]
    check(inv["status"] == "completed", f"mock investigation {inv['id']} of {target} completed")

    before_ids = sorted(i["id"] for i in incidents)
    compose("down")  # no --volumes: the SQLite volume is kept
    compose("up", "-d", "--wait")

    after_ids = sorted(i["id"] for i in api("GET", "/incidents?status=all")["items"])
    check(after_ids == before_ids, f"the same {len(after_ids)} incident(s) after down/up")
    saved = api("GET", f"/incidents/{target}/investigation")["investigation"]
    check(saved["id"] == inv["id"], f"investigation {saved['id']} still stored")
    last = api("GET", "/system")["last_sync"]
    check(last is not None and last["id"] == sync["id"], f"last sync {sync['id']} still stored")
    print(f"All checks passed. The stack is running: {BASE}")


if __name__ == "__main__":
    main()

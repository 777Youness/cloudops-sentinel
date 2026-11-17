# ADR 0019 — A dev-only HTTP fault route to demonstrate a real 5xx incident

- Status: accepted (Day 5b). Implemented and tested locally; **run once on AWS by the owner
  (2026-11-17)**: detection confirmed, resolution not observed (see "Verification on AWS").
- Date: 2026-11-17

## Context
Day 5 was validated on AWS by the owner: 19 resources applied, the read-only role worked,
all three collectors succeeded, 7/7 signals were available, and no incident opened because
the workload was healthy. To show the whole chain (EC2 → CloudWatch Logs → collector →
deterministic rule → SQLite incident → UI → investigation) Sentinel needs a real,
reproducible incident, cheaply and safely, without lowering any threshold.

The original plan was SSM fault scripts (Day 4c). For a 5xx incident an HTTP route is
smaller: no `ssm:SendCommand`, no script on the instance, no new IAM permission.

## Decision
1. **One fixed route** in `workload/app.py`: `GET /fault/500` answers HTTP 500 with a fixed
   body and is logged like every other request (path, status, duration). It reads no
   input (query strings are ignored and never logged), runs no command, reads no file or
   secret, and changes nothing. Any other path under `/fault` is a 404.
2. **Disabled by default.** The app enables it only when `WORKLOAD_FAULTS_ENABLED` is
   exactly `"1"`. Locally, in tests and anywhere else it is off. Terraform sets it through
   the systemd unit from `var.fault_injection_enabled` (default `true`), and a validation
   allows `true` only when `environment = "dev"`. The route is reachable only from the
   operator's /32 (the security group is unchanged).
3. **Controlled traffic** from `scripts/demo_traffic.py` (standard library, Windows
   compatible): 1 request per second to `/`, every 5th to `/fault/500` (20 % errors),
   capped at 5 requests per second and 30 minutes.
4. **No threshold changes.** The script's assumptions are pinned to
   `detection/thresholds.py` by a test (`test_demo_traffic.py`); lowering a threshold, or
   advising an earlier sync, fails the tests.

## Why the defaults trigger R-5XX (and when)
- R-5XX needs the trailing run of 1-minute error rates ≥ 2 % to last 5 minutes, with at
  least 50 requests in it; ≥ 5 % for 5 minutes is the high tier. 20 % of 60 requests per
  minute gives the high tier with 300 requests in 5 minutes.
- A missing minute breaks the run, so traffic must be continuous.
- The collector drops the minute in progress and the last 2 minutes (ingestion delay), so
  the first sync that can see 5 complete minutes is about 8 minutes after the start; the
  script says "sync now" at minute 9 and keeps sending.
- Recovery: R-5XX resolves after 10 clean minutes (below 2 %) with data present, so the
  `healthy` mode must run at least about 13 minutes before the resolving sync.

## Alternatives considered
- **Lower thresholds or a "demo mode" in detection:** would prove nothing about the real
  rules. Rejected.
- **SSM Run Command scripts:** more moving parts (send-command permissions, a script on the
  instance) for the same 500s; kept for later fault types (CPU, memory).
- **Crash the app (stop the service):** produces missing data, not 5xx, so no R-5XX
  incident (by design, missing data is never an error rate).
- **A load generator in AWS (Lambda, another instance):** new services and cost.

## Consequences
- The demo costs about 60 log lines per minute (a few kB) plus the usual instance hours.
- Changing `fault_injection_enabled` changes user_data and replaces the instance.
- The demo shows one rule (R-5XX). CPU, memory and status-check incidents still need their
  own fault mechanisms.

## Verification on AWS
The steps in `infra/README.md` section 8. Run once by the owner on 2026-11-17:
- Confirmed: the sync opened one incident, severity **high**, `data_origin = aws`: the 5xx
  rate stayed at or above 5% for 11 minutes, peak 21.1%. The same incident also recorded
  R-CPU-CREDIT (low credit balance) with CPU utilization near 1%.
- Not observed: resolution by the healthy phase. The workload was destroyed while the
  incident was still open, so automatic resolution on AWS remains unvalidated (it is tested
  locally and with mocked AWS).
- Found: CloudWatch timestamps arrived in local time, so a fact printed the wrong UTC hour;
  fixed in the collector with a regression test. Record:
  `docs/examples/2026-11-17-gpt-oss-20b-INC-0001.json`.

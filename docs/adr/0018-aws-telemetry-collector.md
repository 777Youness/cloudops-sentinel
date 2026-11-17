# ADR 0018 — AWS telemetry collector: polling on sync, boto3, explicit partial failures

- Status: accepted (Day 5). Implemented and tested with mocked AWS (botocore Stubber).
  **Run once against the real account by the owner (2026-11-17)**: the role was assumed,
  ec2, cloudwatch_metrics and cloudwatch_logs were all `ok`, 7/7 signals, 1 resource, 7
  rules, no incident (healthy workload). See "Verification" for what that run settled.
- Date: 2026-11-17

## Context
The workload has been deployed once by the operator (17 resources in eu-west-3, the app
answered HTTP 200 on `/health`, `terraform destroy` ended with an empty state). Sentinel
still only read simulated data. Day 5 must feed real telemetry into the existing detection
engine, lifecycle and SQLite store without a second incident system, without new AWS
services, and with Sentinel's own read-only identity (CLAUDE.md principle 4, ADR 0016).

## Decisions

### 1. A second TelemetrySource, nothing else changes
`collectors/aws/AwsSource` implements the same `collect(window_start, window_end)` as
`SimulatedSource` and returns the same `ObservationSnapshot` with `data_origin = "aws"`.
Detection, lifecycle, health, investigations and the API are unchanged. `SENTINEL_MODE=aws`
selects it (`main.build_source`); aws mode has its own database file (`sentinel-aws.db`,
ADR 0013), so simulated and real incidents never meet.

### 2. Pull on demand (polling), only in POST /api/v1/sync
Sentinel asks AWS when the operator clicks Sync now (ADR 0003). Every GET reads SQLite.
Rejected: CloudWatch alarms → SNS → a webhook (push needs a public endpoint and SNS, both
out of scope); a background scheduler (auto-sync is V4).

### 3. What is collected, and how
| Signal | Source | Call |
|---|---|---|
| instances | tag `cloudops-sentinel:monitor=true`, not terminated | `ec2:DescribeInstances` |
| credit mode | T-family instances | `ec2:DescribeInstanceCreditSpecifications` |
| cpu_utilization (Average, 300 s), cpu_credit_balance (Average, 300 s), status_check_failed (Maximum, 60 s) | `AWS/EC2`, basic monitoring | one batched `cloudwatch:GetMetricData` |
| memory_used (Average, 60 s) | `CWAgent/mem_used_percent`, `InstanceId` | same call |
| request_rate, error_rate_5xx, latency_p95 (60 s) | the workload access log | two `logs:StartQuery` + `GetQueryResults` (`StopQuery` on timeout) |

All six actions are on the approved list of `infra/policies/sentinel-readonly.json`. The
policy also grants `logs:DescribeLogGroups` on `"*"` (region-pinned) because the Service
Authorization Reference lists it for the `StartQuery` operation and it supports no resource
ARN; Sentinel's code never calls it directly. A test
(`tests/aws/test_aws_policy_alignment.py`) fails if the code calls anything else.

Same data semantics as the simulator: only complete periods, a missing period stays
missing, never 0. For the log signals, a minute without any log line is missing (Sentinel
cannot tell "no traffic" from "the agent stopped"); a minute with requests and no 5xx is
0 % (a measurement). The last 2 minutes of logs are left out (ingestion delay).

### 4. Failures are explicit, never healthy
| What failed | Result |
|---|---|
| credentials, profile, or discovery (`DescribeInstances`) | `CollectionError` → SyncRun `failed`, nothing evaluated or resolved |
| metrics or logs | that collector `failed` in `snapshot.collector_statuses`, its signals absent → SyncRun `partial` |
| partial data (credit mode unknown, `PartialData`, truncated query) | collector `degraded` → SyncRun `partial` |

Absent signals become `data_gap` facts; an open incident never resolves on missing data
(existing lifecycle rule). Errors are translated in one place
(`collectors/aws/errors.py`): stable codes (`access_denied`, `credentials_expired`,
`throttled`, `not_found`, `credentials_unavailable`, `profile_not_configured`,
`unreachable`), a hint, account ids masked to the last 4 digits, messages ≤ 300 chars.
Throttling is retried by botocore's `standard` retry mode (3 attempts) before it is
reported. A partial sync counts for `data_as_of` (it stored data); the console shows
"Last sync partial" and the failed collectors on the System page.

### 5. Cost bounds
`GetMetricData`: ≤ 4 metrics per instance per sync ($0.01 per 1,000 metrics in Paris).
Logs Insights: 2 queries per sync, over exactly the sync window (3 h) of one log group,
≤ 1,000 rows each, stopped after `SENTINEL_AWS_LOGS_QUERY_TIMEOUT_SECONDS` (30)
($0.0059 per GB scanned in Paris). No calls at all when no instance is monitored.

### 6. Sentinel's identity: a separate read-only role
Terraform now defines `cloudops-sentinel-<env>-readonly` (iam.tf, **not applied yet**): the
inline policy is `sentinel-readonly.json`; the trust policy names exactly one principal,
`var.sentinel_reader_arn` (the operator's IAM user). That user also needs the small
identity policy `infra/policies/operator-assume-sentinel.json` (`sts:AssumeRole` on that role
only), attached by hand, separate from the Terraform policy. The backend uses the profile
`sentinel` (`role_arn` + `source_profile = sentinel-terraform`): its source credentials come
from the operator's sign-in, but every AWS call runs with the role's read-only permissions.
botocore supports a `credential_process` profile as an assume-role source (checked in the
botocore source: the profile provider chain includes `ProcessProvider`); not yet run.

Rejected: reusing the operator profile (it can create and delete infrastructure); access
keys for a dedicated IAM user (long-lived secrets); trusting the account root (any IAM
principal with `sts:AssumeRole` could use the role).

## Not in this step
Deployment events from `ssm:ListCommands` (no deploy scripts exist yet: Day 4c), alarm
states (`cloudwatch:DescribeAlarms`), log samples (`logs:FilterLogEvents`) and the Resources
pages. The policy already allows the first three reads.

## Verification
**Settled by the owner's run (2026-11-17):** items 1, 2 and 3 below, and, because the
logs collector returned all three log signals, the Logs Insights permissions (item 4) and
field names (item 6) work as written. Still open: item 5 against real series, and item 7
(an incident from real AWS data: ADR 0019 provides the 5xx demo).

Original checklist:
1. `terraform apply` creates 19 resources (17 + the role and its inline policy).
2. `aws sts get-caller-identity --profile sentinel` returns the assumed role.
3. A sync in aws mode returns `success` with three `ok` collectors; the System page lists them.
4. Open question from ADR 0016: whether `logs:StartQuery`/`GetQueryResults` work with the
   bare log-group ARN (the SAR format; if not: `access_denied` on `cloudwatch_logs`, a
   partial sync). `DescribeLogGroups` is now granted on `"*"` (see decision 3).
5. Status check metrics at 1 minute and CPU metrics at 5 minutes are documented in the EC2
   user guide (checked 2026-11-17); the real series should match.
6. The Logs Insights field names (`@logStream`, `bin(1m)`) and timestamp format match the
   parser (`collectors/aws/logs.py`).
7. A load test on the workload (for example many requests to `/`) produces a non-zero
   request rate; CPU stress produces R-CPU-SAT end to end.

## Consequences
- Real and simulated data share all detection code and tests: a rule tested with the
  simulator behaves the same on AWS data.
- Failures are visible at three levels: the SyncRun status, the collector state, and data
  gaps on incidents.
- Collection is manual and bounded: data is only as fresh as the last sync.

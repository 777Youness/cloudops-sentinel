# ADR 0016 — Dev workload: public subnet, SSM-only access, local Terraform state, read-only role

- Status: accepted (Day 4a: decided and documented; resources are created in Day 4b)
- Date: 2026-10-12 (facts checked on this date; sources below)

## Context
Day 4 creates a small, disposable AWS workload for Sentinel to monitor. Sentinel itself stays
local (ADR 0001). CLAUDE.md forbids NAT gateways, load balancers, interface VPC endpoints,
Elastic IPs, customer-managed KMS keys, Secrets Manager, CloudTrail trails and detailed
monitoring, forbids port 22, and requires that Sentinel never modifies AWS. One person
operates the project, from one machine, and destroys the environment after each session.

## Decisions

### 1. Network: one public subnet, a public IPv4 address, an internet gateway
The instance must reach Systems Manager, CloudWatch and its package repositories. Without a
NAT gateway or interface endpoints, the only route is an internet gateway, which requires
a public IPv4 address on the instance.
- Inbound: nothing, except the workload's app port from `var.operator_cidr` (a single /32).
  No port 22 anywhere. Outbound: HTTPS (443) only.
- Cost of the address (verified): $0.005 per hour, the same whether in use or idle, billed
  per second with a 60-second minimum ([Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/)).
  It is billed only while the instance runs with the address; the safety timer below stops it.
- Rejected: NAT gateway or interface endpoints (forbidden, and billed per hour each);
  IPv6-only (not verified to work for every service the agents call).

### 2. Access: Systems Manager only, no SSH
- Session Manager needs no inbound port: the agent opens outbound HTTPS connections. The
  instance needs the AWS-managed policy `AmazonSSMManagedInstanceCore`; Amazon Linux 2023
  AMIs ship with the SSM Agent (its status should still be checked once)
  ([prerequisites](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html),
  [instance permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html),
  [preinstalled agent](https://docs.aws.amazon.com/systems-manager/latest/userguide/ami-preinstalled-agent.html)).
- No EC2 key pair is created, so there is no private key to leak.
- Shells (`ssm start-session`) and fault scripts (`ssm send-command`) run under the
  operator's own profile. Sentinel's role is explicitly denied both.

### 3. Terraform state: local first, S3 later
| | Local state (chosen) | S3 backend + bootstrap |
|---|---|---|
| Moving parts | None | A bucket created by a separate config, whose own state is local anyway |
| Locking | Not needed: one operator | Native S3 lock file (`use_lockfile`, Terraform >= 1.10) ([docs](https://developer.hashicorp.com/terraform/language/backend/s3)) |
| Durability | One file on one machine; losing it orphans resources | Versioned bucket |
| Cost | Zero | Small but non-zero, and the bucket outlives every destroy |
| Needed for CI plans | Yes, eventually | `terraform plan` in CI is "Later" in CLAUDE.md |

Chosen: **local state** in `infra/envs/dev` (gitignored). The risk of a lost state file is
reduced by the workflow: plan, apply, demo, **destroy in the same session**, then
`scripts/cost-check.sh` (Day 4d) lists anything tagged `Project=cloudops-sentinel` that
still exists. "Terraform bootstrap" (CLAUDE.md scope) is therefore a documented one-time
procedure (`infra/README.md`), not a set of resources.
Migration path, when CI plans or a second machine arrive: create a versioned, encrypted S3
bucket, add an `s3` backend block with `use_lockfile = true`, run
`terraform init -migrate-state`.

### 4. Sentinel's read-only role
`infra/policies/sentinel-readonly.json` (a `templatefile()` template: `region`,
`account_id`, `log_group_name`) is the only permission Sentinel has in AWS:
- Allow, by exact action name, with the narrowest scope the Service Authorization Reference
  supports for each:
  - `ec2:DescribeInstances`, `ec2:DescribeInstanceCreditSpecifications`,
    `cloudwatch:GetMetricData`, `ssm:ListCommands`, `logs:StopQuery`: `Resource: "*"`
    (they have no required resource type), pinned to the region with `aws:RequestedRegion`;
  - `cloudwatch:DescribeAlarms`: alarms named `cloudops-sentinel-*` only;
  - `logs:StartQuery`, `logs:GetQueryResults`, `logs:FilterLogEvents`: the workload log
    group only.
- An explicit Deny covers EC2 start/stop/terminate/run/modify/create/delete and network
  changes, SSM commands and sessions, CloudWatch and Logs writes, all of IAM,
  `sts:AssumeRole`, and `logs:Unmask` (a Read-level action that would reveal data a Logs
  data protection policy masks). A Deny wins over any Allow attached later.
- **Exception to the verb rule**: `logs:StartQuery` and `logs:StopQuery` are Logs Insights
  query control. AWS classifies both at access level Read; they change no resource and no
  log data. StartQuery is billed per GB scanned, so it runs only during sync over a bounded
  window. CLAUDE.md principle 4 names this exception explicitly; the test
  `backend/tests/test_readonly_policy.py` fails on any other non-read action and pins the
  scope of every allowed action.
- Trust (Day 4b): only the operator's own sign-in role may assume it.

### 5. Safety timer
The instance schedules its own shutdown at boot, with shutdown behaviour **stop**: no
compute charge while stopped, and an auto-assigned public IPv4 address is released.

## Policy review against the Service Authorization Reference (2026-10-12)
Each allowed action was checked, by expanding the reference tables in a browser, on
[list_ec2](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html),
[list_cloudwatch](https://docs.aws.amazon.com/service-authorization/latest/reference/list_cloudwatch.html),
[list_logs](https://docs.aws.amazon.com/service-authorization/latest/reference/list_logs.html) and
[list_ssm](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ssm.html):

| Action | Access level | Resource types (`*` = required) | Condition keys | Scope in the policy |
|---|---|---|---|---|
| `ec2:DescribeInstances` | List | none | `ec2:Region` | `*` + region |
| `ec2:DescribeInstanceCreditSpecifications` | List | none | `ec2:Region` | `*` + region |
| `cloudwatch:GetMetricData` | Read | `dataset` (optional) | `aws:ResourceTag/${TagKey}`, `cloudwatch:HasAccessGrant` | `*` + region |
| `cloudwatch:DescribeAlarms` | Read | `alarm*` | `aws:ResourceTag/${TagKey}` | `arn:aws:cloudwatch:${region}:${account_id}:alarm:cloudops-sentinel-*` |
| `logs:StartQuery` | Read | `log-group*` | `aws:ResourceTag/${TagKey}` | log group ARN |
| `logs:GetQueryResults` | Read | `log-group*` | `aws:ResourceTag/${TagKey}` | log group ARN |
| `logs:FilterLogEvents` | Read | `log-group*` | `aws:ResourceTag/${TagKey}` | log group ARN |
| `logs:StopQuery` | Read | none | none | `*` + region |
| `ssm:ListCommands` | List | none | none | `*` + region |

ARN formats from the same pages: alarm
`arn:${Partition}:cloudwatch:${Region}:${Account}:alarm:${AlarmName}`; log group
`arn:${Partition}:logs:${Region}:${Account}:log-group:${LogGroupName}` (the policy uses this
exact form; the `:*` suffix seen in many AWS examples is not added).
`aws:RequestedRegion` is a global condition key "always included in the request context"
([IAM global condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html));
global services such as IAM resolve to us-east-1, which does not affect this policy (the
IAM Deny has no region condition). `ssm:SendCommand` and `ssm:StartSession` are Write
actions (denied).

**Still open** (cannot be settled from documentation; the first read-only test in Day 4b
settles them, and any failure is a denied call, never extra access):
- The reference's operations table lists, for the `StartQuery` operation, the actions
  `logs:DescribeLogGroups`, `logs:DescribeQueryDefinitions`, `logs:FilterLogEvents`,
  `logs:StartQuery` and `logs:Unmask`, and `logs:FilterLogEvents` for `GetQueryResults` and
  `StopQuery`, without saying which are conditional. `logs:FilterLogEvents` is already
  granted on the log group; `logs:DescribeQueryDefinitions` is documented as needed only
  for saved queries (not used); `logs:Unmask` is deliberately denied. Whether a plain
  query also needs `logs:DescribeLogGroups` is unknown: add it (a List action) only if the
  test shows it is required.
- Whether `GetQueryResults` and `FilterLogEvents` are evaluated against the bare log-group
  ARN or the `:*` form in practice.

## State backup and recovery limitations
- The state file is **not versioned and not backed up** by this setup. It contains resource
  ids and attributes (for example IPs and user data), so treat it as sensitive: never commit
  it, never paste it.
- If it is lost or corrupted while resources exist: do not re-apply blindly. Find the
  resources by tag `Project=cloudops-sentinel` and delete them in the console, or bring
  them back under management with `terraform import` before destroying.
- Optional manual backup after `apply`: copy `terraform.tfstate` to a private location
  outside the repository; delete the copy after `destroy`.

## Consequences
- No standing cost when destroyed; no inbound attack surface besides one port from one IP.
- The operator must keep the state file until destroy; a lost file means manual cleanup
  guided by tags.
- Every new AWS permission for Sentinel is a reviewed change to one JSON file and one test.

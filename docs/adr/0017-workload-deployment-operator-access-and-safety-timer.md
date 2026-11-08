# ADR 0017 — Workload deployment: operator access without Identity Center, scoped roles, terminate-on-timer

- Status: accepted (Day 4b). Amends ADR 0016 (operator sign-in, safety timer behaviour).
  **The safety timer is UNTESTED on a real EC2 instance**; see "Verification".
- Date: 2026-11-01 (documentation checked on this date; sources below)

## Context
Day 4b turns the Day 4a skeleton into a small workload: VPC, public subnet, internet
gateway, one t3.micro, an instance role, a log group with the CloudWatch agent, and one CPU
alarm. Three facts changed since ADR 0016:
- The account is standalone. AWS warned that creating an organization would immediately
  expire the account's active credits, so **AWS Organizations and IAM Identity Center are
  never enabled**. ADR 0016 and `infra/README.md` assumed Identity Center sign-in.
- The safety timer must remove the instance, not leave a stopped one: a stopped instance
  still pays for its EBS volume.
- The owner wants every permission scoped: the operator's, the instance's and Sentinel's.

## Decisions

### 1. Operator credentials: IAM user, console sign-in, `aws login`, no access keys
- One IAM user for the operator, with a console password and MFA, and **no access keys**.
  It gets two policies by hand: `SignInLocalDevelopmentAccess` (AWS managed) and the
  project policy `infra/policies/operator-terraform.json` (rendered with
  `scripts/render_policy.py`). Neither is created by Terraform.
- `aws login --profile sentinel-login` turns the console session into short-lived
  credentials (AWS CLI ≥ 2.32.0, refreshed every 15 minutes, for up to the principal's
  session duration, at most 12 hours; cached under `%USERPROFILE%\.aws\login\cache`)
  ([AWS CLI user guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)).
- Terraform's AWS provider is built on the AWS SDK for Go v2, which the
  [SDK compatibility table](https://docs.aws.amazon.com/sdkref/latest/guide/feature-login-credentials.html)
  lists as not supporting this credential type, and the provider changelog has no entry for
  it. So Terraform uses a second profile, `sentinel-admin`, with
  `credential_process = aws configure export-credentials --profile sentinel-login --format process`,
  the bridge AWS documents for tools without native support. Nobody runs
  `export-credentials` by hand (it would print credentials).
- Rejected: an access key (long-lived, stored on disk); root credentials (never for daily
  work); Identity Center (would expire the credits).

### 2. Three separate permissions, never mixed
| Who | Policy | Created by |
|---|---|---|
| Operator (Terraform, sessions, leftover check) | `infra/policies/operator-terraform.json` | You, by hand |
| Workload instance | `AmazonSSMManagedInstanceCore` + inline `cloudwatch-agent-scoped` (`iam.tf`) | Terraform |
| Sentinel collector (Day 5) | `infra/policies/sentinel-readonly.json` | Terraform, in a later PR (D10) |

**Operator policy** (tested by `backend/tests/test_operator_policy.py`):
- `ec2:Describe*` only as a wildcard, pinned to `eu-west-3` (Terraform reads many EC2
  attributes; Describe calls change nothing and have no resource-level permissions).
- Network actions by exact name on `arn:aws:ec2:eu-west-3:<account>:*`.
- `ec2:RunInstances` split by resource type, as the
  [Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html)
  lists for the "EC2-VPC-EBS-Subnet" scenario (image, instance, network-interface,
  security-group, subnet, volume required; snapshot optional), with conditions the
  reference documents per resource type: instance `ec2:InstanceType = t3.micro` and
  `ec2:MetadataHttpTokens = required`; volume `ec2:Encrypted = true` and
  `ec2:VolumeType = gp3`; image and snapshot `ec2:Owner = amazon`. AWS then refuses any
  other shape, whatever the Terraform code says.
- Terminate/modify instances, and Session Manager shells, only on instances tagged
  `Project=cloudops-sentinel`.
- KMS use for EBS encryption only through EC2 (`kms:ViaService`), grants only for AWS
  resources (`kms:GrantIsForAWSResource`), as the
  [EBS encryption requirements](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-encryption-requirements.html)
  recommend.
- IAM only on `role/cloudops-sentinel-*` and `instance-profile/cloudops-sentinel-*`;
  `iam:PassRole` only to `ec2.amazonaws.com`; `iam:AttachRolePolicy` only for
  `AmazonSSMManagedInstanceCore`.
- Logs on `/cloudops-sentinel/*`, alarms on `cloudops-sentinel-*`, the public AL2023 AMI
  parameter, and the reads `scripts/cost-check.sh` needs.
- An explicit Deny on creating IAM users, access keys and login profiles, on
  Organizations, Identity Center (`sso:*`, `identitystore:*`), key pairs, Elastic IPs, NAT
  gateways, VPC endpoints, detailed monitoring, KMS keys, dashboards, trails and secrets.

**Instance role:** the managed `CloudWatchAgentServerPolicy` allows `logs:CreateLogGroup`
and `logs:PutRetentionPolicy` on `"*"`
([policy document](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/CloudWatchAgentServerPolicy.html)),
and an agent-created log group without `retention_in_days` "never expires"
([agent configuration](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Agent-Configuration-File-Details.html)).
The inline policy instead allows `cloudwatch:PutMetricData` only in namespace `CWAgent`,
and `logs:CreateLogStream`, `logs:PutLogEvents`, `logs:DescribeLogStreams` only on the one
log group Terraform creates.

### 3. CloudWatch agent: exactly one custom metric
The agent publishes the hostname as a dimension "unless you are using the
`append_dimensions` field"; `omit_hostname` also removes it; `aggregation_dimensions` adds
rolled-up copies; each unique dimension combination is a separate metric. The config
(`templates/cloudwatch-agent.json.tftpl`) collects only `mem_used_percent`, with
`append_dimensions = {"InstanceId": "${aws:InstanceId}"}`, `omit_hostname: true`, no
aggregation and `usage_data: false`. It ships one file, the access log, to the Terraform
log group, without `retention_in_days` (Terraform owns retention).

### 4. Safety timer: terminate, not stop (amends ADR 0016 decision 5)
- `instance_initiated_shutdown_behavior = "terminate"`. AWS documents that a shutdown from
  the OS ("shutdown or poweroff") then terminates the instance, and that "The halt command
  doesn't initiate a shutdown"
  ([shutdown behaviour](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_ChangingInstanceInitiatedShutdownBehavior.html)).
- user_data installs a systemd timer **first**, before anything that can fail:
  `OnBootSec=<safety_timer_minutes>min` starts a oneshot service running
  `/usr/bin/systemctl poweroff`. systemd documents that an `OnBootSec=` timer already in the
  past when it is activated "will immediately elapse"
  ([systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)),
  so a slow boot fails safe. If enabling the timer fails, `shutdown -P +<minutes>` is the
  fallback (one-shot, not reboot-proof).
- Default 240 minutes; 15 only for the controlled termination test; bounds 15–480.
- Expected effects (documented): charges stop at `shutting-down`/`terminated`
  ([terminate](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/terminating-instances.html));
  the root volume is deleted because `delete_on_termination = true`
  ([termination](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-termination-works.html));
  the auto-assigned public IPv4 address is released
  ([addressing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-instance-addressing.html)).
- Not a second timer: Lambda and EventBridge are "Later" (V4). The budget alert and
  `terraform destroy` plus `scripts/cost-check.sh` remain the backstops; a hung OS never
  runs the timer.

### 5. The workload app
`workload/app.py`: standard library only, Python 3.9 compatible (the AL2023 system
`python3` "will remain as Python 3.9 for the life of AL2023",
[AL2023 Python](https://docs.aws.amazon.com/linux/al2023/ug/python.html)), runs as an
unprivileged user on port 8080, writes one JSON line per request (time, method, path,
status, duration_ms) and never logs query strings. It is the source of request_rate,
error_rate_5xx and latency_p95 for Day 5. Fault injection waits for Day 4c.

## Verification (what is NOT yet known)
**UNTESTED on AWS**, to be run by the operator (infra/README.md, "Verification on AWS"):
1. Termination test (15 minutes): the instance reaches `terminated` by itself; no volume,
   no network interface and no public IPv4 address remain (the network interface deletion
   is expected but was not found stated on a documentation page).
2. Functional run (240 minutes): SSM session works over HTTPS-only egress; `dnf` reaches the
   repositories; the app answers from the operator's /32; the access log reaches the log
   group; `list-metrics --namespace CWAgent` shows one metric with only `InstanceId`.
3. Permissions: the operator policy is sufficient for plan/apply/destroy (AccessDenied loop);
   whether the KMS statements are needed with the AWS-managed `aws/ebs` key; the exact ARN
   IAM accepts for the public AMI parameter; whether the agent needs
   `logs:DescribeLogGroups`.
Until 1 has passed and is recorded here, the timer is documented as UNTESTED.

## Consequences
- No long-lived credential exists anywhere; the credits are protected from Organizations.
- AWS itself refuses a wrong instance type, IMDSv1, an unencrypted or non-gp3 volume, or a
  non-Amazon image for the operator, even if the Terraform code is changed.
- Every new permission is a reviewed edit of one JSON file and one test.
- The operator policy must fit a customer managed policy (6,144 characters, whitespace not
  counted). Its `Sid`s are therefore short; their meaning is recorded in
  `SID_PURPOSES` in `backend/tests/test_operator_policy.py`, which also fails above 6,000
  characters. If it outgrows that, split it into two managed policies rather than widen
  actions to wildcards.
- The operator policy may be incomplete at first: AccessDenied errors are expected and are
  fixed one action at a time, never by widening to a wildcard.

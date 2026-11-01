# Cost

What the AWS side of CloudOps Sentinel can cost. **Verified** prices come from the official
AWS Price List bulk files for eu-west-3 (`pricing.us-east-1.amazonaws.com/offers/v1.0/aws/
<service>/<version>/eu-west-3/index.json`), read on 2026-11-01, with the file's publication
date. Anything not found there is marked **unverified**.

Status: Day 4b (2026-11-01). **No AWS resource exists yet**: the Terraform in
`infra/envs/dev` has never been applied. Update this page in the same change as any
billable resource (CLAUDE.md).

## Prices (eu-west-3, USD)

| Item | Used for | Price | Status | Price List file (published) |
|---|---|---|---|---|
| EC2 t3.micro, Linux, On-Demand | The workload instance | $0.0118 per hour | Verified | AmazonEC2 (2026-10-29), usage type `EUW3-BoxUsage:t3.micro` |
| T3 CPU credits beyond baseline | Only in `unlimited` mode; V1 uses `standard` | $0.05 per vCPU-hour | Verified (not used) | AmazonEC2 (2026-10-29) |
| Public IPv4 address, in use or idle | The instance's auto-assigned address | $0.005 per hour | Verified | AmazonVPC (2026-10-16) |
| EBS gp3 storage | The root volume | $0.0928 per GB-month | Verified | AmazonEC2 (2026-10-29), `EUW3-EBS:VolumeUsage.gp3` |
| EBS gp3 IOPS / throughput above the included baseline | Not provisioned (defaults kept) | $0.0058 per IOPS-month / $0.0464 per MiBps-month | Verified; the size of the included baseline is not in the file | AmazonEC2 (2026-10-29) |
| CloudWatch custom metric | `mem_used_percent` (exactly one) | $0.30 per metric-month (first 10,000), prorated by the hour, charged only in hours when data is sent | Verified (price list; proration from the CloudWatch pricing page) | AmazonCloudWatch (2026-10-07) |
| CloudWatch alarm, standard resolution | `cloudops-sentinel-dev-cpu-high` | $0.10 per alarm metric-month, prorated by the hours the alarm exists | Verified | AmazonCloudWatch (2026-10-07) |
| CloudWatch Logs ingestion, Standard class | The access log | $0.5985 per GB | Verified | AmazonCloudWatch (2026-10-07) |
| CloudWatch Logs storage | The access log, 3-day retention | $0.0315 per GB-month | Verified | AmazonCloudWatch (2026-10-07) |
| CloudWatch Logs Insights | Sentinel sync, Day 5 | $0.0059 per GB scanned | Verified | AmazonCloudWatch (2026-10-07) |
| CloudWatch `GetMetricData` | Sentinel sync, Day 5 | $0.01 per 1,000 metrics requested | Verified | AmazonCloudWatch (2026-10-07) |
| Data transfer out to the internet | Agent, SSM and app traffic (small) | $0.09 per GB, first 10 TB, "beyond the global free tier" | Verified (the free-tier amount is not in the file) | AWSDataTransfer (2026-09-16) |
| KMS requests (AWS-managed `aws/ebs` key) | EBS encryption at launch | $0.03 per 10,000; storing AWS-managed keys is free | Verified | awskms (2026-10-26); [KMS pricing](https://aws.amazon.com/kms/pricing/) |
| Session Manager, Run Command on EC2 | Shells, fault scripts (Day 4c) | No price entry found for EC2 use (only hybrid sessions) | **Unverified** (believed free) | AWSSystemsManager (2026-10-08) |
| VPC, subnet, internet gateway, route table, security groups | Network | No price entry in the file | **Unverified** (believed free) | AmazonVPC (2026-10-16) |
| IAM roles and policies | Access | Not checked | **Unverified** (believed free) | — |
| AWS Budgets | The operator's budget alert | Not checked | **Unverified** | — |
| Terraform state | Local file (ADR 0016) | $0 | n/a | — |

**Free tier rows** in the same price list files: 10 custom metrics, 10 alarms, 5 GB logs
ingestion, 5 GB logs storage, 5 GB Logs Insights scanned, 1,000,000 CloudWatch API
requests, 20,000 KMS requests per month. **Whether they apply to this account is
unverified** (see "Free tier and credits").

## Estimate for one session (verified unit prices only)
Assumptions: an 8 GiB root volume (the AL2023 AMI size is not stated on its documentation
page; check it after the first apply), **no free tier**, negligible log and transfer volume.

| Item | Per running hour |
|---|---|
| t3.micro | $0.0118 |
| Public IPv4 | $0.0050 |
| EBS gp3, 8 GiB | about $0.0010 |
| One custom metric, while publishing | about $0.0004 |
| One alarm, while it exists | about $0.0001 |
| **Total** | **about $0.018** |

So about **$0.07 for a 4-hour session**. After the timer terminates the instance, only the
alarm (about $0.0001 per hour) and the stored logs keep costing until `terraform destroy`.

## What survives what

| Resource | After the timer terminates the instance | After `terraform destroy` |
|---|---|---|
| Instance | `terminated`, no charge, visible for a short while | gone |
| Root volume | deleted (`delete_on_termination = true`) | gone |
| Network interface | expected deleted (**unverified**, termination test) | gone |
| Public IPv4 address | released | — |
| Log group and up to 3 days of logs | **remain** (storage billed) | deleted with the logs |
| CPU alarm | **remains, billed hourly** | deleted |
| `mem_used_percent` metric | no charge without data; data kept | data cannot be deleted; expires after 15 months, no charge |
| VPC, subnet, IGW, route table, security groups, IAM role and profile | remain (believed free) | deleted |
| Budget, operator IAM user | untouched | untouched (not managed by Terraform) |

Sources: [terminate](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/terminating-instances.html),
[how termination works](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-termination-works.html),
[public IPv4 release](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-instance-addressing.html),
[metric retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html),
[CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/).

## Free tier and credits
- AWS announced on 2025-07-15 that accounts created from that date get credits and a
  6-month free plan; older accounts keep the legacy Free Tier
  ([2025 announcement](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/)).
  Which one applies to this account is **unverified** until checked in the Billing console.
- The account has active credits (about $155.91, estimated remaining $152.57 when checked
  by the owner). Whether they cover every item above is **unverified**.
- **Never enable AWS Organizations or IAM Identity Center**: AWS warned that creating an
  organization would immediately expire these credits (ADR 0017).

## The budget
- The Budgets API documents `IncludeCredit` with "default value is true"
  ([CostTypes](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_budgets_CostTypes.html)).
  With credits included, usage paid by credits nets to about $0 and a $10 alert may never
  fire while credits last. **Exclude credits** in the budget's charge types so it tracks
  gross usage.
- Suggested alerts on the $10 monthly budget: actual $1 (early warning), actual $5, actual
  $8, forecasted $10. A budget is not real time: it is a backstop, not the cleanup.

## Cost controls (by design)
- **Destroy after each session**, then `scripts/cost-check.sh` (read-only; exit 0 means
  nothing billable was found in the region).
- **Safety timer** (UNTESTED): the instance powers itself off after
  `safety_timer_minutes` (default 240) and, with shutdown behaviour terminate, is terminated.
- **AWS refuses other shapes**: the operator policy only allows t3.micro, IMDSv2, encrypted
  gp3 volumes and Amazon images (ADR 0017).
- **No forbidden resources**: no NAT gateway, load balancer, RDS, ECS/EKS, interface
  endpoints, Elastic IP, customer-managed KMS key, Secrets Manager, CloudTrail trail,
  dashboards or detailed monitoring (tested in `backend/tests/test_infra_guardrails.py`).
- **One custom metric** (limit 5), InstanceId only; **3-day log retention**; the instance
  role cannot create log groups.
- **Sentinel's paid reads** (Logs Insights, `GetMetricData`) happen only during a sync, over
  a bounded window (default 3 hours). Never on page loads.

## How prices were checked (2026-11-01)
The Price List bulk files above were downloaded (public files, no AWS account involved) and
filtered by usage type for eu-west-3. The EC2 file was read as CSV (`index.csv`, 170 MB).
Earlier values from 2026-10-12 (t3.micro, public IPv4) are unchanged.

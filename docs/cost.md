# Cost

What the AWS side of CloudOps Sentinel can cost, with **verified prices only**. Anything not
checked against an official AWS pricing page is marked **unknown**. No total is given:
too many prices are unknown for a total to be honest.

Status: Day 4a (reviewed 2026-10-12). **No AWS resource exists yet.** Update this page in the same change as any
billable resource (CLAUDE.md).

## Prices (region eu-west-3 unless stated)

| Item | Used for | Price | Status | Source (checked 2026-10-12) |
|---|---|---|---|---|
| Public IPv4 address | The workload instance (ADR 0016) | $0.005 per hour, in use or idle; per-second billing, 60 s minimum | **Verified** | [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/) |
| EC2 t3.micro (On-Demand, Linux, EU (Paris)) | The workload instance | $0.0118 per hour (USD) | **Verified** | Data file of the official [EC2 On-Demand pricing page](https://aws.amazon.com/ec2/pricing/on-demand/) (`b0.p.awsstatic.com/.../ec2-ondemand-without-sec-sel/EU (Paris)/Linux/index.json`, published 2026-10-09), read in a browser |
| t3.micro CPU credits beyond baseline | Only in `unlimited` mode, which V1 never uses (`standard`) | not applicable | — | — |
| EBS gp3 storage, 8 GB root volume | The workload instance | unknown | Not verified | Amazon EBS pricing page, Europe (Paris) |
| CloudWatch custom metric (`mem_used_percent`, 1 metric) | Memory signal | unknown | Not verified | Amazon CloudWatch pricing page |
| CloudWatch Logs ingestion and storage (3-day retention) | Workload access log | unknown | Not verified | Amazon CloudWatch pricing page |
| CloudWatch Logs Insights (per GB scanned) | Sentinel sync, Day 5 | unknown | Not verified | Amazon CloudWatch pricing page |
| CloudWatch `GetMetricData` (per metrics requested) | Sentinel sync, Day 5 | unknown | Not verified | Amazon CloudWatch pricing page |
| CloudWatch alarms (standard resolution) | Optional, decision pending | unknown | Not verified | Amazon CloudWatch pricing page |
| Session Manager, Run Command on EC2 | Shell access, fault scripts | unknown | Not verified | AWS Systems Manager pricing page |
| VPC, subnet, route table, internet gateway, security groups, IAM roles | Network and access | unknown | Not verified | Amazon VPC and IAM pricing pages |
| Data transfer out | Agents and SSM traffic | unknown | Not verified | EC2 data transfer pricing |
| Terraform state | Local file (ADR 0016), no S3 bucket | $0 | n/a | — |

## Free tier: depends on the account
AWS announced on 2025-07-15 that accounts created from that date get credits and a 6-month
free plan; older accounts keep the legacy Free Tier, which included 750 hours per month of
public IPv4 for 12 months
([2025 announcement](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/),
[2024 announcement](https://aws.amazon.com/about-aws/whats-new/2024/02/aws-free-tier-750-hours-free-public-ipv4-addresses/)).
Which one applies to the account used here is **unknown** until checked in the Billing
console. Do not assume anything is free.

## Cost controls (by design, not by estimate)
- **Destroy after each session.** Nothing is meant to run between demos; `terraform destroy`
  then `scripts/cost-check.sh` (Day 4d) lists anything left that could bill.
- **Safety timer**: the instance stops itself after a fixed time (ADR 0016).
- **No forbidden resources**: no NAT gateway, load balancer, RDS, ECS/EKS, interface
  endpoints, Elastic IP, customer-managed KMS key, Secrets Manager, CloudTrail trail,
  dashboards or detailed monitoring.
- **One custom metric** (limit: 5); **3-day log retention**.
- **Sentinel's paid reads** (Logs Insights, `GetMetricData`) happen only during a sync, over
  a bounded window (default 3 hours). Never on page loads.
- **A budget alert**, set by the operator in the AWS console before the first apply.

## How prices were checked (2026-10-12)
- Verified rows come from official AWS pages only, read on the date shown. The EC2 price is
  the value the official On-Demand page loads for "EU (Paris)", Linux; billing granularity
  for EC2 was not checked and is not assumed.
- **Why the other rows stay unknown:** the EBS and CloudWatch pricing pages did not render
  a Europe (Paris) table in the browser used for the review, and the AWS Price List bulk
  files (`pricing.us-east-1.amazonaws.com`) could not be opened from it. The CloudWatch page
  shows worked examples with prices (for instance per custom metric and per standard alarm
  metric), but they do not name a region, so they are not used here.

## To verify before Day 4b apply
Fill in every "unknown" row above from the official pricing page or the AWS Price List bulk
file for `eu-west-3` (for example in the AWS Pricing Calculator), with the date checked,
then decide on alarms.

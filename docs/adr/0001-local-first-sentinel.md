# ADR 0001 — For V1, Sentinel runs locally and monitors a disposable AWS workload

- Status: accepted
- Date: 2026-09-23

## Context
Sentinel needs real AWS telemetry to be credible, but hosting the console itself on AWS
(compute, registry, networking, TLS, authentication) adds cost and complexity before the
product's core (detection, evidence, investigation) is validated.

## Decision
For V1, Sentinel runs locally and monitors a small disposable AWS workload. Deployment of
Sentinel itself is intentionally deferred until the core product is validated.

After V1–V3, a separate deployment phase will be evaluated (for example containerized with
ECR, a compute service, Terraform and CI/CD). That phase is neither designed nor
implemented now.

## Alternatives considered
- Host Sentinel on EC2 next to the workload: the monitor would fail with the host it monitors.
- Host Sentinel on ECS Fargate behind an ALB: always-on cost and an authentication problem
  before there is a validated product.

## Consequences
- The Boto3 → IAM → CloudWatch path is fully real; only the console's location is local.
- Recruiters see the product through screenshots, video and (later) a static demo build.
- The API has no authentication and binds to 127.0.0.1; this must change before any hosting.
